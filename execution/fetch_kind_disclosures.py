"""KIND 거래소 안내공시 수집 → disclosures.json에 누적 (source='KIND').

DART와의 중복 없이 거래소 고유 안내공시(매매거래정지/관리종목/단기과열/조회공시/
상장폐지/공시번복·불이행 등)만 수집해서 fetch_disclosures.py가 만든 disclosures.json에
KIND 항목을 append. 보유 종목 (portfolio_data.json) 매칭으로 필터.

KIND endpoint: POST https://kind.krx.co.kr/disclosure/todaydisclosure.do
- selDate=YYYY-MM-DD로 일별 모든 공시
- 종목명 기반 매칭 (KIND 응답에 종목코드 직접 포함 안 됨, companysummary_open의
  내부 ID는 KIND 자체 corp_code라 KRX 종목코드와 다름)

워크플로:
  1. portfolio_data.json → 보유 종목명 집합
  2. KIND 일별 공시 fetch (어제, 오늘)
  3. 거래소 안내공시 키워드 매칭 + 보유 종목명 매칭
  4. acptNo 기준 dedup (기존 disclosures.json items 검사)
  5. disclosures.json에 source='KIND' 항목 append

출력 disclosures.json items 스키마 (DART/KIND 공통, source로만 구분):
  {"rcept_no" or "acpt_no": "20260526000917", "code": "", "name": "코리아써키트",
   "date": "2026-05-26", "title": "매매거래정지 예고", "summary": "...",
   "url": "https://kind.krx.co.kr/common/disclsviewer.do?...", "source": "KIND"}

소스 구분 필드 'source'를 disclosures.json에 추가 (기존 DART는 source 누락 = 'DART'로 fallback).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
PORTFOLIO_FILE = ROOT / 'portfolio_data.json'
DISCLOSURES_FILE = ROOT / 'disclosures.json'

# 포트폴리오 매니저에게 유관한 거래소 공시 키워드.
# 안2(2026-06-16): 사고성 거래소 안내공시(거래정지/관리종목 등)에 더해 자기주식/IR/계약/
# 증자/CB·BW/양수도/배당 등 투자판단 유관 유형을 추가. DART와 제목이 겹칠 수 있으나
# cross-source dedup(_norm_title + name + date)으로 KIND 쪽 중복을 버려 정합성 유지.
EXCHANGE_KW = (
    # ── 거래소 사고성 안내공시 (DART에 잘 안 뜨는 거래소 고유 발표) ──
    '매매거래정지', '매매거래 정지', '매매거래재개', '매매거래 재개',
    '관리종목 지정', '관리종목지정', '관리종목 해제', '관리종목해제',
    '단기과열', '상장폐지', '주권매매거래정지',
    '조회공시 요구', '조회공시요구',
    '공시번복', '공시불이행', '불성실공시법인',
    '주식분할', '주식병합',
    '투자위험종목 지정해제', '투자위험종목 최초지정',  # 시장감시위원회
    # ── 자기주식 (취득/처분/신탁/소각) ──
    '자기주식취득', '자기주식 취득',
    '자기주식처분', '자기주식 처분',
    '자기주식소각', '자기주식 소각',
    '자기주식취득신탁계약', '자기주식 취득 신탁계약',  # 체결/해지 모두 포함(부분문자열)
    # ── IR / 기업설명회 ──
    '기업설명회', '기업설명회(IR)',
    # ── 주요사항보고서 (증자/사채/양수도 등 핵심 의사결정 묶음) ──
    '주요사항보고서',
    # ── 단일판매ㆍ공급계약 (수주) ──
    '단일판매', '공급계약체결', '공급계약 체결',
    # ── 증자 결정 ──
    '유상증자결정', '유상증자 결정',
    '무상증자결정', '무상증자 결정',
    # ── 사채 발행 (CB / BW) ──
    '전환사채', '신주인수권부사채',
    # ── 양수도 ──
    '자산양수도', '영업양수도',
    '타법인주식및출자증권양수', '타법인주식및출자증권처분',
    # ── 배당 ──
    '주식배당', '현금배당', '현물배당', '현금ㆍ현물배당', '현금·현물배당', '배당결정',
)

SUMMARY_CHARS = 300


def _portfolio_index() -> tuple[set[str], dict[str, str]]:
    """portfolio_data.json에서 (보유 종목명 set, 종목명→6자리코드 dict).

    같은 종목명이 여러 그룹에 중복될 수 있으나 code는 동일하므로 마지막 값으로 덮어써도 무방.
    code가 6자리 숫자가 아니면 매핑에서 제외(KIND 항목 code='' 유지).
    """
    if not PORTFOLIO_FILE.exists():
        return set(), {}
    with open(PORTFOLIO_FILE, encoding='utf-8') as f:
        d = json.load(f)
    names: set[str] = set()
    name_to_code: dict[str, str] = {}
    for pf, stocks in d.items():
        if pf.startswith('_'):
            continue
        for s in stocks:
            n = (s.get('name') or '').strip()
            if not n:
                continue
            names.add(n)
            code = str(s.get('code') or '').strip()
            if len(code) == 6 and code.isdigit():
                name_to_code[n] = code
    return names, name_to_code


# 정정/연결/시장구분/투자주의 등 KIND이 DART 제목 앞뒤에 붙이는 마커
_BRACKET_RE = re.compile(r'\[[^\]]*\]')      # [정정] [기재정정] [첨부정정] [연결포함] [투자주의] ...
_PAREN_RE = re.compile(r'\([^)]*\)')          # (안내공시) (미확정) (약식) (자율공시) (IR) ...
_NONWORD_RE = re.compile(r'[\s·ㆍ‧ㆍ·,.\-~/·…\'"“”‘’]+')


# 우선주 등 KIND 종목명에 붙는 접미사. 보통주명 + 이 접미사까지만 같은 종목으로 인정.
# (예: '코리아써키트우', '삼성전자우'). '두산' vs '두산에너빌리티'처럼 다른 법인은 배제.
_PREF_SUFFIXES = ('우', '우B', '우C', '2우B', '3우B', '1우', '2우', '3우')


def _match_holding(kind_name: str, portfolio_names: set[str]) -> str | None:
    """KIND 종목명 → 보유 종목명 매칭. 정확 일치 또는 보통주명+우선주접미사만 인정.

    기존의 단순 부분문자열(`pn in kind_name`)은 '두산'이 '두산에너빌리티'에 substring으로
    걸려 다른 상장법인을 오매칭하는 버그가 있었다. 길이 차가 접미사 범위를 넘으면 배제한다.
    동시에 후보가 여러 개면 가장 긴(가장 구체적인) 보통주명을 선택해 부분 종목명 충돌을 줄인다.
    """
    kn = (kind_name or '').strip()
    if not kn:
        return None
    best = None
    for pn in portfolio_names:
        if kn == pn:
            return pn  # 정확 일치 즉시 채택
        # 보통주명으로 시작하고 나머지가 우선주 접미사일 때만 인정
        if kn.startswith(pn) and kn[len(pn):] in _PREF_SUFFIXES:
            if best is None or len(pn) > len(best):
                best = pn
    return best


def _norm_title(title: str) -> str:
    """cross-source 제목 정규화: 대괄호 마커·괄호 내용·중점·구두점·공백 전부 제거.

    KIND은 DART 공시를 미러링하면서 '[정정]', '[연결포함]' 같은 마커와 시장구분을 덧붙이고
    가운뎃점(ㆍ/·)·괄호표기가 미세하게 다를 수 있어, 핵심 어절만 남겨 비교한다.
    예) '[기재정정]단일판매ㆍ공급계약체결' → '단일판매공급계약체결'
        '기업설명회(IR)개최(안내공시)'      → '기업설명회개최'
    """
    t = title or ''
    t = _BRACKET_RE.sub('', t)
    t = _PAREN_RE.sub('', t)
    t = _NONWORD_RE.sub('', t)
    return t.strip().lower()


def _load_disclosures() -> dict:
    if DISCLOSURES_FILE.exists():
        with open(DISCLOSURES_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {'updated_at': None, 'items': []}


def _fetch_kind_day(session: requests.Session, date_str: str) -> list[dict]:
    """KIND todaydisclosure.do — 해당 날짜 전체 공시 리스트 (raw rows)."""
    data = {
        'method': 'searchTodayDisclosureSub',
        'forward': 'todaydisclosure_sub',
        'currentPageSize': '500',
        'pageIndex': '1',
        'orderMode': '0',
        'orderStat': 'D',
        'marketType': '',
        'searchCorpName': '',
        'searchType': 'A',
        'keyword': '',
        'todayFlag': 'N',
        'selDate': date_str,
    }
    resp = session.post(
        'https://kind.krx.co.kr/disclosure/todaydisclosure.do',
        data=data,
        headers={'Referer': 'https://kind.krx.co.kr/disclosure/todaydisclosure.do?method=searchTodayDisclosureMain'},
        timeout=20,
    )
    resp.encoding = 'utf-8'
    soup = BeautifulSoup(resp.text, 'html.parser')
    rows: list[dict] = []
    for tr in soup.find_all('tr'):
        cells = tr.find_all('td')
        if len(cells) < 4:
            continue
        time_str = cells[0].get_text(strip=True)
        name = cells[1].get_text(strip=True)
        title = cells[2].get_text(strip=True)
        submitter = cells[3].get_text(strip=True)
        # acptNo는 cells[2]의 a.onclick에서 추출: openDisclsViewer('20260526000917', '')
        a = cells[2].find('a')
        m = re.search(r"openDisclsViewer\('(\d+)'", a.get('onclick', '')) if a else None
        acpt_no = m.group(1) if m else ''
        rows.append({
            'time': time_str,
            'name': name,
            'title': title,
            'submitter': submitter,
            'acpt_no': acpt_no,
            'date': date_str,
        })
    return rows


def main() -> None:
    portfolio_names, name_to_code = _portfolio_index()
    if not portfolio_names:
        print("portfolio_data.json에 보유 종목 없음 — 종료")
        return
    print(f"보유 종목: {len(portfolio_names)}개 (코드 매핑 {len(name_to_code)}개)")

    existing = _load_disclosures()
    seen_keys = set()
    # cross-source dedup: DART 항목의 (정규화제목, 종목명, 날짜) 집합. KIND이 같은 사건을
    # 미러링하면 이 집합에 걸려 버려진다(DART 우선 — code·summary 보유).
    dart_event_keys: set[tuple[str, str, str]] = set()
    for it in existing.get('items', []):
        if it.get('source') == 'KIND':
            seen_keys.add(f"kind:{it.get('rcept_no') or it.get('acpt_no')}")
        else:
            seen_keys.add(f"dart:{it.get('rcept_no')}")
            dart_event_keys.add((_norm_title(it.get('title', '')),
                                 (it.get('name') or '').strip(),
                                 (it.get('date') or '').strip()))
    print(f"기존 누적: {len(existing.get('items', []))}건 (KIND/DART 합), "
          f"DART 이벤트키 {len(dart_event_keys)}개")
    dup_skipped = 0
    code_mapped = 0

    # 기본은 어제~오늘 (cron 일일 운영). --days N으로 N일치 백필 가능 (1회용 시드 갱신).
    days_back = 1
    if '--days' in sys.argv:
        try:
            days_back = max(1, int(sys.argv[sys.argv.index('--days') + 1]))
        except (IndexError, ValueError):
            pass
    today = datetime.now(KST).date()
    dates = [today - timedelta(days=i) for i in range(days_back, -1, -1)]
    print(f"조회 구간: {dates[0]} ~ {dates[-1]} ({len(dates)}일)")
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    # session init
    session.get('https://kind.krx.co.kr/disclosure/todaydisclosure.do?method=searchTodayDisclosureMain', timeout=15)

    new_items: list[dict] = []
    for d in dates:
        ds = d.strftime('%Y-%m-%d')
        try:
            rows = _fetch_kind_day(session, ds)
        except Exception as e:
            print(f"  {ds} KIND fetch 실패: {e}")
            continue
        for r in rows:
            # 1. 거래소 안내공시 키워드 매칭
            if not any(k in r['title'] for k in EXCHANGE_KW):
                continue
            # 2. 보유 종목명 매칭 — 정확 일치 또는 보통주명+우선주접미사만 (다른 법인 substring 오매칭 방지)
            matched_name = _match_holding(r['name'], portfolio_names)
            if not matched_name:
                continue
            # 3. acpt 기준 dedup (KIND 자체 중복)
            if not r['acpt_no']:
                continue
            key = f"kind:{r['acpt_no']}"
            if key in seen_keys:
                continue
            # 4. cross-source dedup — 같은 사건이 DART에 이미 있으면 KIND 버림(DART 우선)
            event_key = (_norm_title(r['title']), matched_name, r['date'])
            if event_key in dart_event_keys:
                dup_skipped += 1
                continue
            seen_keys.add(key)
            dart_event_keys.add(event_key)  # KIND끼리 같은 사건 중복도 1건으로
            # 5. 종목코드 역매핑 (보유종목 name→code; UI 종목 필터 드롭다운에 잡히도록)
            code = name_to_code.get(matched_name, '')
            if code:
                code_mapped += 1
            # 6. 항목 생성
            summary = f"{r['submitter']} · {r['time']}"
            new_items.append({
                'rcept_no': r['acpt_no'],  # DART와 같은 필드명으로 통일 (UI 호환)
                'code': code,
                'name': matched_name,
                'date': r['date'],
                'title': r['title'],
                'summary': summary,
                # KIND viewer popup URL — JCommon.js openDisclsViewer2가 실제 호출하는 패턴.
                # acptno 소문자 + method=search + viewerhost 필수 (없으면 blank.html redirect).
                'url': f"https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno={r['acpt_no']}&docno=&viewerhost=kind.krx.co.kr&viewerport=",
                'source': 'KIND',
            })
            print(f"  +{matched_name} [{code or '코드없음'}] | {r['title'][:50]}")

    print(f"\n신규 KIND: {len(new_items)}건 "
          f"(DART중복 제거 {dup_skipped}건, 코드매핑 {code_mapped}건)")
    if new_items:
        # 누적 + 날짜 내림차순
        merged = existing.get('items', []) + new_items
        merged.sort(key=lambda x: (x.get('date', ''), x.get('rcept_no', '')), reverse=True)
        existing['items'] = merged
        existing['updated_at'] = datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')
        with open(DISCLOSURES_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        print(f"[성공] disclosures.json: 총 {len(merged)}건 (+{len(new_items)} KIND 신규)")
    else:
        print("[변경 없음]")


if __name__ == '__main__':
    main()
