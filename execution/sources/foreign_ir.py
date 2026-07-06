"""해외 기업 IR/뉴스룸 폴링 어댑터 (foreign_ir).

Universe 비-KRW 회사들의 IR/Newsroom 페이지를 폴링해서 신규 보도자료를
한국어 제목 번역과 함께 텔레그램으로 알린다 (KNA/SemiAnalysis 와 같은
Generic Source Pipeline 위에서 동작).

설계:
- 대상 회사 목록: foreign_ir_sources.json (enabled=true 만)
- 수집 방식 분기:
    _CUSTOM_FETCHERS 등록 → 회사 전용 수집기 최우선 (예: ETN Coveo API)
    rss_url 보유  → feedparser 로 RSS/Atom 파싱 (가장 견고, 우선)
    rss 0건/없음  → ir_url HTML 을 날짜-블록 기준 범용 추출
- 회사별 독립 state: sources_state/foreign_ir.json
    {"companies": {"<TICKER>": {"seen": ["<url>", ...]}}}
- per-company try/except: 한 회사 실패해도 나머지 계속
- 최초 등록 회사: 현재 보도자료를 baseline 으로 적재만 (알림 없음, 즉시 영속)
- 이미 추적 중인 회사: 신규만 → 제목 배치 번역 → post 반환.
    실제 last_seen 갱신은 텔레그램 발송 성공 후 commit_state 에서 (at-least-once).

Phase 2 범위: 제목 레벨 알림 (제목 한국어 번역 + 날짜 + 링크 + RSS 요약 발췌).
본문 풀 번역은 Phase 3+ (페이지마다 레이아웃이 달라 별도 작업).
"""
from __future__ import annotations

import argparse
import html as _html
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone as _tz
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

# curl_cffi: 브라우저 TLS 핑거프린트를 흉내내 IR 사이트의 봇 차단(Cloudflare/TLS
# fingerprinting)을 우회한다. 일반 requests 대비 차단 회피 + 빠른 실패로 커버리지·속도
# 모두 크게 개선됨. 미설치 환경에서는 requests 로 폴백.
try:
    from curl_cffi import requests as _curl_requests
    _HAS_CURL_CFFI = True
except Exception:  # pragma: no cover
    _curl_requests = None
    _HAS_CURL_CFFI = False

from . import DASHBOARD_DIR
from .base import load_state, save_state, state_path

logger = logging.getLogger(__name__)

LABEL = '해외 기업 뉴스룸'
ICON = '🌐'
STATE_NAME = 'foreign_ir'
HEALTH_NAME = 'foreign_ir_health'   # sources_state/foreign_ir_health.json — 회사별 수집 건강(사각지대 점검용)

SOURCES_FILE = os.path.join(DASHBOARD_DIR, 'foreign_ir_sources.json')

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
HTTP_HEADERS = {
    'User-Agent': UA,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

FETCH_TIMEOUT = 15          # 회사 1건 HTTP 타임아웃(초)
MAX_WORKERS = 8             # 동시 fetch 수 (예의상 제한)
MAX_LIST_PER_COMPANY = 25   # 비교용으로 가져올 최신 N건
MAX_NEW_PER_COMPANY = 5     # 1회 실행당 회사별 신규 알림 상한 (URL 일괄 변경 시 폭주 방지)
MAX_REMEMBERED_PER_COMPANY = 40  # seen 목록 보관 상한
FAIL_RATIO_ABORT = 0.6      # 이 비율 이상 회사 fetch 실패 시 systemic 오류로 raise


# ── 날짜 파싱 ──────────────────────────────────────────────────────────
_MONTHS = ('January|February|March|April|May|June|July|August|September'
           '|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec')
_HTML_DATE_RE = re.compile(
    rf'\b(?:{_MONTHS})\.?\s+\d{{1,2}},?\s+\d{{4}}\b'   # May 13, 2026 / Apr 8 2026
    r'|\b\d{4}-\d{2}-\d{2}\b'                          # 2026-05-13
    r'|\b\d{4}/\d{1,2}/\d{1,2}\b'                      # 2026/05/13 (아시아권 IR)
    r'|\b\d{4}\.\s?\d{1,2}\.\s?\d{1,2}\.?'             # 2026.06.02 / 2026. 06. 01 (한국식 점)
    r'|\b\d{1,2}/\d{1,2}/\d{4}\b'                      # 05/13/2026
    rf'|\b\d{{1,2}}\s+(?:{_MONTHS})\.?\s+\d{{4}}\b',   # 13 May 2026
    re.IGNORECASE,
)

_DATE_FORMATS = (
    '%B %d, %Y', '%b %d, %Y', '%B %d %Y', '%b %d %Y',
    '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d %B %Y', '%d %b %Y',
)


def _parse_date_iso(s: str) -> str:
    """다양한 영문 날짜 문자열 → 'YYYY-MM-DD'. 실패 시 ''."""
    if not s:
        return ''
    s = s.replace('Sept', 'Sep').strip().rstrip(',')
    # 한국식 점 날짜: '2026.06.02' / '2026. 06. 01' (가변 공백, 끝점 옵션)
    m = re.match(r'^(\d{4})\.\s?(\d{1,2})\.\s?(\d{1,2})\.?$', s)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        try:
            return datetime(y, mo, d).strftime('%Y-%m-%d')
        except ValueError:
            return ''
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return ''


# ── HTTP ──────────────────────────────────────────────────────────────
def _http_get(url: str, timeout: int = FETCH_TIMEOUT) -> str:
    """IR 페이지/피드 GET. curl_cffi(브라우저 TLS 흉내) 우선, 없으면 requests 폴백.

    SSL 인증서 오류 시 verify=False 로 1회 재시도 (일부 IR CDN 인증서 체인 불완전).
    """
    if _HAS_CURL_CFFI:
        # 봇 차단(403/406/429) 시 브라우저 핑거프린트를 바꿔가며 재시도.
        # 1순위 'chrome'(최신 별칭)으로 빠르게 성공시키고, 차단 응답일 때만 대체
        # 핑거프린트 + Referer/Accept-Language 보강 (HD/ERIC 같은 봇 차단 IR 회피).
        _origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}/"
        _alt_headers = {'Referer': _origin, 'Accept-Language': 'en-US,en;q=0.9'}
        attempts = (
            {'impersonate': 'chrome'},
            {'impersonate': 'safari180', 'headers': _alt_headers},
            {'impersonate': 'chrome131', 'headers': _alt_headers},
            {'impersonate': 'firefox144', 'headers': _alt_headers},
        )
        last_exc: Exception | None = None
        for i, kw in enumerate(attempts):
            try:
                r = _curl_requests.get(url, timeout=timeout, **kw)
            except Exception as e:
                msg = str(e).lower()
                if 'certificate' in msg or 'ssl' in msg:
                    try:
                        r = _curl_requests.get(url, timeout=timeout, verify=False, **kw)
                    except Exception as e2:
                        last_exc = e2
                        continue
                else:
                    last_exc = e
                    continue
            # 봇 차단 코드면 다음 핑거프린트로 (마지막 시도면 그대로 raise_for_status)
            if r.status_code in (403, 406, 429) and i < len(attempts) - 1:
                last_exc = RuntimeError(f"HTTP {r.status_code} bot-block ({kw['impersonate']})")
                continue
            r.raise_for_status()
            return r.text
        raise last_exc if last_exc else RuntimeError('unknown fetch error')

    # ── requests 폴백 ──
    last_err: Exception | None = None
    for _ in range(2):
        try:
            try:
                r = requests.get(url, headers=HTTP_HEADERS, timeout=timeout)
            except requests.exceptions.SSLError:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                r = requests.get(url, headers=HTTP_HEADERS, timeout=timeout, verify=False)
            r.raise_for_status()
            r.encoding = r.encoding or 'utf-8'
            return r.text
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_err = e
            continue
    raise last_err if last_err else RuntimeError('unknown fetch error')


# ── RSS/Atom 파싱 ──────────────────────────────────────────────────────
def _parse_rss(text: str) -> list[dict]:
    """feedparser 로 RSS/Atom 파싱. 최신순 리스트 반환."""
    fp = feedparser.parse(text)
    out: list[dict] = []
    for e in fp.entries[:MAX_LIST_PER_COMPANY]:
        url = (e.get('link') or '').strip()
        eid = (e.get('id') or url).strip()
        title = (e.get('title') or '').strip()
        if not title or not (eid or url):
            continue
        date_iso = ''
        if e.get('published_parsed'):
            date_iso = time.strftime('%Y-%m-%d', e.published_parsed)
        elif e.get('updated_parsed'):
            date_iso = time.strftime('%Y-%m-%d', e.updated_parsed)
        summary = _strip_html(e.get('summary') or '')
        out.append({
            'id': eid or url,
            'url': url,
            'title': _clean_text(title),
            'date': date_iso,
            'summary': summary[:300],
        })
    return out


# ── HTML 범용 추출 (날짜 블록 기준) ─────────────────────────────────────
_SOCIAL_HOSTS = ('twitter.com', 'x.com', 'facebook.com', 'linkedin.com',
                 'youtube.com', 'instagram.com', 't.me')


def _is_article_href(href: str, base_url: str) -> bool:
    if not href or href.startswith(('#', 'mailto:', 'javascript:', 'tel:')):
        return False
    if 'email-protection' in href:
        return False
    try:
        host = urlparse(urljoin(base_url, href)).netloc.lower()
    except Exception:
        return False
    return not any(s in host for s in _SOCIAL_HOSTS)


def _extract_html(base_url: str, html: str) -> list[dict]:
    """IR 보도자료 리스트 페이지 HTML → 항목 추출.

    전략: 날짜처럼 보이는 짧은 텍스트 노드를 찾고, 그 조상(최대 5단계)에서
    제목(heading 또는 anchor 텍스트) + 기사 링크가 함께 있는 '카드'를 잡는다.
    (FormFactor 등 카드형 레이아웃 검증 완료)
    """
    soup = BeautifulSoup(html, 'lxml')
    items: list[dict] = []
    seen: set[str] = set()

    for el in soup.find_all(string=_HTML_DATE_RE):
        raw = (el or '').strip()
        if not raw or len(raw) > 60:   # 날짜 '라벨' 만 (긴 본문 문장 제외)
            continue
        m = _HTML_DATE_RE.search(raw)
        if not m:
            continue
        date_iso = _parse_date_iso(m.group(0))

        node = el.parent
        title = None
        link = None
        for _ in range(7):
            if node is None:
                break
            # 카드 링크: 조상 노드 자신이 <a>(카드 전체를 감싼 래퍼)거나, 자손 <a>
            cand_a = None
            if node.name == 'a' and node.get('href') and _is_article_href(node['href'], base_url):
                cand_a = node
            else:
                da = node.find('a', href=True)
                if da and _is_article_href(da['href'], base_url):
                    cand_a = da
            # 제목: heading 우선 → 앵커 텍스트(날짜 제거) 폴백
            heading = node.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            cand_title = None
            if heading:
                ht = _clean_text(heading.get_text(' ', strip=True))
                if 15 <= len(ht) <= 220:
                    cand_title = ht
            if not cand_title and cand_a:
                at = _clean_text(_HTML_DATE_RE.sub('', cand_a.get_text(' ', strip=True)))
                at = at.strip(' -·|··')
                if 15 <= len(at) <= 220:
                    cand_title = at
            if cand_title and cand_a:
                title = cand_title
                link = urljoin(base_url, cand_a['href'])
                break
            node = node.parent

        if title and link and link not in seen:
            seen.add(link)
            items.append({'id': link, 'url': link, 'title': title,
                          'date': date_iso, 'summary': ''})
        if len(items) >= MAX_LIST_PER_COMPANY:
            break
    return items


# ── 텍스트 정리 ────────────────────────────────────────────────────────
def _strip_html(s: str) -> str:
    if not s:
        return ''
    return _clean_text(BeautifulSoup(s, 'lxml').get_text(' ', strip=True))


def _clean_text(s: str) -> str:
    return ' '.join(_html.unescape(s or '').split())


# ── 커스텀 fetcher (표준 rss/html 로 수집 불가한 회사 전용) ─────────────
def _api_request(method: str, url: str, headers: dict | None = None,
                 json_body: dict | None = None, timeout: int = FETCH_TIMEOUT):
    """JSON API 호출용 (POST/헤더 지원). curl_cffi 우선, requests 폴백."""
    if _HAS_CURL_CFFI:
        r = _curl_requests.request(method, url, headers=headers, json=json_body,
                                   timeout=timeout, impersonate='chrome')
    else:
        r = requests.request(method, url, headers=headers, json=json_body, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _fetch_eaton_coveo(company: dict) -> list[dict]:
    """ETN(Eaton) 전용: 뉴스 리스트가 Coveo 검색 JS 컴포넌트로 전환(2026-06)되어
    정적 HTML 에 기사가 0건. 페이지에 공개 임베드된 apigee/Coveo 설정을 매 실행
    긁어서(키 회전에 자가치유, 저장소에 시크릿 하드코딩 없음) 토큰 체인 후
    Coveo Search API 로 미국 뉴스릴리스를 최신순 조회한다.

    체인: 뉴스페이지 HTML(설정 추출) → apigee OAuth 토큰 → Coveo 검색 토큰
          → POST https://{org}.org.coveo.com/rest/search/v2
    """
    ir_url = company['ir_url']
    page = _http_get(ir_url)

    def _attr(name: str) -> str:
        m = re.search(rf'{name}="([^"]+)"', page)
        if not m:
            raise RuntimeError(f'Eaton page config missing: {name}')
        return _html.unescape(m.group(1))

    apigee_url = _attr('data-coveo-apigee-url')
    apigee_auth = _attr('data-apigee-auth')
    api_key = _attr('data-api-key')
    token_url = _attr('data-coveo-token-url')
    org = _attr('data-coveo-org-id')
    hub = 'EATON_NEWSANDINSIGHTS'
    if hub not in page:  # 컴포넌트 개편 대비: 페이지의 뉴스용 search-hub 폴백
        hubs = [h for h in re.findall(r'search-hub="([^"]+)"', page) if 'SITESEARCH' not in h]
        if hubs:
            hub = hubs[0]

    access = _api_request('POST', apigee_url,
                          headers={'Authorization': 'Basic ' + apigee_auth})['access_token']
    coveo_token = _api_request('GET', token_url,
                               headers={'Authorization': f'Bearer {access}',
                                        'x-api-key': api_key})['token']

    search_ep = f'https://{org}.org.coveo.com/rest/search/v2'
    payload = {
        'searchHub': hub,
        'locale': 'en-US',
        'numberOfResults': 60,
        'sortCriteria': '@p_publish_date descending',
        # 미국 사이트 소스만 (같은 릴리스가 지역 사이트별로 중복 색인됨).
        # 소스명이 개편되면 0건 → 아래에서 aq 없이 1회 재시도(자가치유).
        'aq': '@syssource=="NORTHAMERICA_SITEMAP_SOURCE"',
    }
    hdr = {'Authorization': f'Bearer {coveo_token}'}
    data = _api_request('POST', search_ep, headers=hdr, json_body=payload)
    if not data.get('results'):
        payload.pop('aq')
        data = _api_request('POST', search_ep, headers=hdr, json_body=payload)

    prefix = 'https://www.eaton.com/us/en-us/company/news-insights/news-releases/'
    items: list[dict] = []
    seen: set[str] = set()
    for res in data.get('results', []):
        url = (res.get('clickUri') or '').split('?')[0]
        title = _clean_text(res.get('title') or '')
        if not url.startswith(prefix) or not title or url in seen:
            continue
        seen.add(url)
        ms = (res.get('raw') or {}).get('p_publish_date')
        date_iso = ''
        if isinstance(ms, (int, float)) and ms > 0:
            date_iso = datetime.fromtimestamp(ms / 1000, tz=_tz.utc).strftime('%Y-%m-%d')
        items.append({'id': url, 'url': url, 'title': title,
                      'date': date_iso, 'summary': _clean_text(res.get('excerpt') or '')[:300]})
        if len(items) >= MAX_LIST_PER_COMPANY:
            break
    return items


# 표준 rss/html 파이프라인으로 못 잡는 회사의 전용 수집기 레지스트리.
# 커스텀 실패 시 _fetch_company 가 rss/html 경로로 폴백한다.
_CUSTOM_FETCHERS = {
    'ETN': _fetch_eaton_coveo,
}


# ── 회사 1건 수집 (state I/O 없음, 순수 함수) ──────────────────────────
def _fetch_company(company: dict) -> dict:
    """회사 1건의 최신 보도자료 리스트 수집. state 를 건드리지 않는다.

    Returns: {ticker, name, exchange, method, releases:[...], error}
    releases 는 최신순. 실패 시 error 채워지고 releases=[].
    """
    ticker = company.get('ticker') or company.get('name_en', '?')
    name = company.get('name_en', ticker)
    exchange = company.get('exchange', '')
    rss_url = company.get('rss_url')
    ir_url = company.get('ir_url')

    result = {'ticker': ticker, 'name': name, 'exchange': exchange,
              'method': None, 'releases': [], 'error': None}

    try:
        releases: list[dict] = []
        custom = _CUSTOM_FETCHERS.get(ticker)
        if custom:
            try:
                releases = custom(company)
                result['method'] = 'custom'
            except Exception as e:
                logger.warning(f'[{ticker}] custom fetcher 실패: {e}')
                releases = []
        if not releases and rss_url:
            try:
                releases = _parse_rss(_http_get(rss_url))
                result['method'] = 'rss' if result['method'] is None else f'{result["method"]}->rss'
            except Exception as e:
                logger.warning(f'[{ticker}] RSS 실패 ({rss_url}): {e}')
                releases = []
        # 앞 단계 0건이거나 rss_url 없음 → HTML 폴백
        if not releases and ir_url:
            releases = _extract_html(ir_url, _http_get(ir_url))
            result['method'] = 'html' if result['method'] is None else f'{result["method"]}->html'
        result['releases'] = releases
        if not releases:
            result['error'] = 'no releases extracted'
    except Exception as e:
        result['error'] = f'{type(e).__name__}: {e}'
    return result


# ── 공개 API ───────────────────────────────────────────────────────────
def _load_companies() -> list[dict]:
    """foreign_ir_sources.json 에서 enabled=true 회사만."""
    if not os.path.exists(SOURCES_FILE):
        raise RuntimeError(f'foreign_ir_sources.json 없음: {SOURCES_FILE}')
    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return [c for c in data.get('companies', []) if c.get('enabled')]


def _fetch_all(companies: list[dict]) -> list[dict]:
    """ThreadPool 로 전 회사 병렬 수집. 결과 리스트 (입력 순서 무관)."""
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_fetch_company, c): c for c in companies}
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as e:  # _fetch_company 는 자체 try/except 라 사실상 안 옴
                c = futures[fut]
                results.append({'ticker': c.get('ticker'), 'name': c.get('name_en'),
                                'exchange': c.get('exchange', ''), 'method': None,
                                'releases': [], 'error': f'executor: {e}'})
    return results


def _update_health(results: list[dict]) -> None:
    """회사별 수집 성공/실패 이력 기록 (사각지대 점검용 foreign_ir_health 상태).

    success = 보도자료 1건 이상 추출. 정상 회사는 항상 과거 목록을 반환하므로
    releases 가 0이면 사실상 fetch/parse 실패로 간주(진짜 '뉴스 없음'이 아님).
    완전 방어적: 절대 본 작업을 깨지 않는다 (모든 예외 흡수).
    """
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        state = load_state(HEALTH_NAME)
        comps: dict = state.get('companies') or {}
        for r in results:
            tk = r.get('ticker')
            if not tk:
                continue
            entry = comps.get(tk) or {}
            entry['name'] = r.get('name') or entry.get('name') or tk
            if r.get('releases'):
                entry['last_ok'] = today
                entry['fail_streak'] = 0
                entry.pop('last_error', None)
            else:
                entry['fail_streak'] = int(entry.get('fail_streak', 0)) + 1
                entry['last_fail'] = today
                entry['last_error'] = (r.get('error') or 'no releases')[:200]
                entry.setdefault('last_ok', None)
            comps[tk] = entry
        save_state(HEALTH_NAME, {'companies': comps, 'updated': today})
    except Exception as e:
        logger.warning(f'foreign_ir health 기록 실패 (무시): {e}')


def fetch_new_posts(update_state: bool = False, translate: bool = True) -> list[dict]:
    """enabled 회사 순회 → 신규 보도자료 수집 → 제목 번역 → post 리스트.

    최초 추적 회사는 baseline 만 적재(알림 없음)하고 즉시 영속한다
    (파이프라인이 posts 빈 경우 commit_state 를 호출하지 않으므로).
    이미 추적 중인 회사의 신규 항목은 여기서 영속하지 않고 commit_state 에 맡긴다
    (텔레그램 발송 실패 시 재시도에서 다시 잡히도록 — at-least-once).
    """
    companies = _load_companies()
    state = load_state(STATE_NAME)
    comp_state: dict = state.get('companies') or {}

    results = _fetch_all(companies)
    _update_health(results)   # 회사별 건강 기록 (사각지대 주간 점검용)

    fail_count = sum(1 for r in results if r.get('error'))
    total = len(results) or 1

    pending: list[dict] = []          # 번역/발송 대상 신규 항목
    baseline_dirty = False

    for r in results:
        ticker = r['ticker']
        releases = r.get('releases') or []
        if r.get('error') and not releases:
            logger.warning(f'[{ticker}] 수집 실패: {r["error"]}')
            continue

        entry = comp_state.get(ticker)
        current_ids = [rel['id'] for rel in releases if rel.get('id')]

        if entry is None:
            # 최초 추적 회사 → baseline 적재만 (알림 없음), 즉시 영속
            comp_state[ticker] = {'seen': current_ids[:MAX_REMEMBERED_PER_COMPANY]}
            baseline_dirty = True
            logger.info(f'[{ticker}] baseline 초기화 ({len(current_ids)}건, 알림 없음)')
            continue

        seen = set(entry.get('seen') or [])
        new_rel = [rel for rel in releases if rel.get('id') and rel['id'] not in seen]
        if not new_rel:
            continue
        # 페이지/피드는 최신순 → 오래된 순으로 발송, 회사별 상한
        new_rel = list(reversed(new_rel))[-MAX_NEW_PER_COMPANY:]
        for rel in new_rel:
            pending.append({
                'id': rel['id'],
                'ticker': ticker,
                'name': r['name'],
                'exchange': r['exchange'],
                'title_en': rel['title'],
                'date': rel.get('date', ''),
                'url': rel.get('url', ''),
                'summary': rel.get('summary', ''),
            })

    # baseline 영속 (update_state 무관 — 알림 폭주 방지용 필수 쓰기).
    # 파이프라인은 posts 가 비면 commit_state 를 호출하지 않으므로 여기서 직접 저장한다.
    if baseline_dirty:
        save_state(STATE_NAME, {'companies': comp_state})

    # 제목 배치 번역
    if pending and translate:
        from ._translator import translate_titles
        tr = translate_titles([p['title_en'] for p in pending])
        for p, kr in zip(pending, tr['titles_kr']):
            p['title_kr'] = kr
        logger.info(
            f'foreign_ir 제목 번역: {len(pending)}건 '
            f'in={tr["input_tokens"]} out={tr["output_tokens"]}'
        )
    else:
        for p in pending:
            p['title_kr'] = p['title_en']

    logger.info(
        f'foreign_ir fetch 완료: 회사 {total}개, 실패 {fail_count}, 신규 {len(pending)}건'
    )

    # 절반 이상 실패면 systemic 문제로 간주 (파이프라인 오류 알림 + 재시도 유도)
    if fail_count / total >= FAIL_RATIO_ABORT:
        raise RuntimeError(
            f'foreign_ir 회사 fetch 실패율 {fail_count}/{total} '
            f'(>= {FAIL_RATIO_ABORT:.0%}) — 네트워크/구조 변경 의심'
        )

    return pending


def commit_state(posts: list[dict]) -> None:
    """발송 성공 후 회사별 seen 갱신."""
    if not posts:
        return
    state = load_state(STATE_NAME)
    comp_state: dict = state.get('companies') or {}
    for p in posts:
        ticker = p.get('ticker')
        if not ticker or not p.get('id'):
            continue
        entry = comp_state.setdefault(ticker, {'seen': []})
        seen = entry.get('seen') or []
        if p['id'] not in seen:
            seen.append(p['id'])
        entry['seen'] = seen[-MAX_REMEMBERED_PER_COMPANY:]
    save_state(STATE_NAME, {'companies': comp_state})


def format_message(post: dict, label: str, icon: str) -> str:
    """텔레그램 HTML 메시지 1건."""
    name = _html.escape(post.get('name', ''))
    ticker = _html.escape(post.get('ticker', ''))
    title_kr = _html.escape(post.get('title_kr') or post.get('title_en', ''))
    title_en = _html.escape(post.get('title_en', ''))
    date = post.get('date', '')
    exchange = _html.escape(post.get('exchange', ''))
    url = post.get('url', '')
    summary = post.get('summary', '')

    meta_bits = [b for b in (date, exchange) if b]
    meta_line = ' · '.join(meta_bits)

    out = f"{icon} <b>[{name} · {ticker}] {title_kr}</b>\n"
    if title_en and title_en != title_kr:
        out += f"<i>{title_en}</i>\n"
    if meta_line:
        out += f"{meta_line}\n"
    if url:
        out += f"{url}\n"
    if summary:
        out += f"\n{_html.escape(summary)}"
    return out


# ── CLI dry-run (state 미변경, 커버리지 측정) ───────────────────────────
def _cli():
    parser = argparse.ArgumentParser(description='foreign_ir 어댑터 dry-run / 커버리지 측정')
    parser.add_argument('--tickers', type=str, default='',
                        help='쉼표구분 티커만 테스트 (기본: enabled 전체)')
    parser.add_argument('--limit', type=int, default=0,
                        help='앞에서 N개 회사만 (0=전체)')
    parser.add_argument('--show', type=int, default=0,
                        help='회사별 추출 release 상위 N건 출력')
    parser.add_argument('--translate', action='store_true',
                        help='제목 번역도 테스트 (Haiku 호출, 비용 발생)')
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(message)s')

    companies = _load_companies()
    if args.tickers:
        wanted = {t.strip() for t in args.tickers.split(',') if t.strip()}
        companies = [c for c in companies if c.get('ticker') in wanted]
    if args.limit > 0:
        companies = companies[:args.limit]

    print(f'\n대상 회사: {len(companies)}개\n')
    t0 = time.time()
    results = _fetch_all(companies)
    elapsed = time.time() - t0

    ok = [r for r in results if r.get('releases')]
    fail = [r for r in results if not r.get('releases')]
    by_method: dict[str, int] = {}
    dated = 0
    total_rel = 0
    for r in ok:
        by_method[r.get('method') or '?'] = by_method.get(r.get('method') or '?', 0) + 1
        total_rel += len(r['releases'])
        dated += sum(1 for rel in r['releases'] if rel.get('date'))

    print('=' * 70)
    print(f'성공(>=1건): {len(ok)}/{len(results)}  ·  실패: {len(fail)}  ·  {elapsed:.1f}s')
    print(f'method 분포: {by_method}')
    print(f'총 release: {total_rel}건, 날짜 파싱 성공: {dated}건 '
          f'({dated / total_rel:.0%})' if total_rel else '총 release: 0')
    print('=' * 70)

    if args.show:
        for r in ok:
            print(f'\n[{r["ticker"]}] {r["name"]} ({r["method"]}) — {len(r["releases"])}건')
            for rel in r['releases'][:args.show]:
                print(f'   [{rel.get("date") or "?":10}] {rel["title"][:70]}')

    if fail:
        print('\n── 실패/0건 회사 ──')
        for r in fail:
            print(f'   {r["ticker"]:10} {(r.get("error") or "")[:80]}')

    if args.translate and ok:
        from ._translator import translate_titles
        sample = [rel['title'] for r in ok for rel in r['releases'][:1]][:10]
        tr = translate_titles(sample)
        print('\n── 제목 번역 샘플 (10건) ──')
        for en, kr in zip(sample, tr['titles_kr']):
            print(f'   EN: {en[:65]}')
            print(f'   KR: {kr[:65]}')


if __name__ == '__main__':
    _cli()
