"""etfcheck.co.kr 내부 API 클라이언트"""
import os
import re
import hashlib
import time
import json
import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

ETFCHECK_BASE = 'https://www.etfcheck.co.kr/user/etp/'
ETFCHECK_HOME = 'https://www.etfcheck.co.kr/'
# 2026-07-08 사이트 개편: 키 '4lm@flEh68'→'er@#$dfe^fd12', 버킷 60s→30s, Referer 필수화 (전부 403 원인)
# 2026-07-21 키 재로테이션: 'er@#$dfe^fd12'→'#$dser#GVEWS329@' (버킷 30s 동일).
# 2026-07-26 두 가지 동시 변경으로 07-22부터 전량 403 (수집 중단):
#   (1) 키가 build.js 인라인 → 웹팩 모듈 1867(`E.a.key`)로 이동·재로테이션: '#$dser#GVEWS329@'→'d$MsKjvz'(8자).
#       8자라 버킷 숫자 8·9는 JS `n[8]`/`n[9]`=undefined → 문자열 'undefined'가 그대로 이어붙는다(아래 복제).
#   (2) API가 세션 쿠키 connect.sid 요구: 홈페이지를 먼저 GET해 세션을 연 뒤 그 쿠키를 실어야 통과.
#       (bare requests.get → 403). _get_session()으로 세션 확보·403 시 1회 재수립. [[project_antigravity_active_etf_alert]]
# 2026-07-27 키가 6일새 4번 로테이션(4lm@flEh68 → er@#$dfe^fd12 → #$dser#GVEWS329@ → d$MsKjvz
#   → csdXMPdc). 하드코딩 추격을 끝내고 **build.js에서 런타임 추출**한다(웹팩
#   모듈의 `{key:"…"}` 유일 매칭). 추출 실패 시 아래 폴백 상수를 쓰고, 403을 만나면 force 재추출해 장중 로테이션도
#   자가치유한다. build.js는 ~5.4MB라 프로세스당 1회만 받는다(KEY_TTL).
ETFCHECK_KEY = 'csdXMPdc'          # 폴백(최후 확인 2026-07-27)
ETFCHECK_BUCKET_MS = 30000
ETFCHECK_BUILD_JS = 'https://www.etfcheck.co.kr/js/build.js'
_KEY_RE = re.compile(r'\{key:"([^"]{4,32})"\}')
_KEY_TTL = 3600.0
_key_cache = None
_key_ts = 0.0

# 2026-07-26 etfcheck가 레이트리밋 도입: ~30요청 후 IP 전체를 403(sticky, 쿨다운 김).
#   대응(중앙화): (a) 요청 최소 간격 ETFCHECK_MIN_INTERVAL초 (b) ROTATE_EVERY건마다 세션 선제
#   로테이션(per-session 카운트 리셋 겨냥) (c) 403 시 세션 재수립 + 장기 백오프(쿨다운 대기,
#   IP 재자극 방지). 간격/로테이션은 환경변수로 무재배포 튜닝 가능.
ETFCHECK_MIN_INTERVAL = float(os.environ.get('ETFCHECK_MIN_INTERVAL', '3.0'))
ETFCHECK_ROTATE_EVERY = int(os.environ.get('ETFCHECK_ROTATE_EVERY', '25'))
_last_req_ts = 0.0
_req_count = 0

# 2026-07-21 맥미니 공인 IP가 etfcheck WAF에 IP 차단(정적 파일까지 403). 현 운영은 수집 자체를
#   Oracle VM(직결 200)에서 실행하므로 프록시 불필요(VM엔 ETFCHECK_PROXY 미설정 → 직결). 이 훅은
#   선택적 dormant 옵션으로 남겨둔다(설정 시 requests가 해당 SOCKS/HTTP 프록시로 우회).
ETFCHECK_PROXY = os.environ.get('ETFCHECK_PROXY') or None

logger = logging.getLogger(__name__)

_session = None


def _new_session():
    """새 세션 생성 + 홈페이지 GET으로 connect.sid 세션 쿠키 확보 (2026-07-26 API 요구)."""
    s = requests.Session()
    s.headers.update({
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/126 Safari/537.36'),
        'Referer': 'https://www.etfcheck.co.kr/',
    })
    if ETFCHECK_PROXY:
        s.proxies = {'http': ETFCHECK_PROXY, 'https': ETFCHECK_PROXY}
    try:
        s.get(ETFCHECK_HOME, timeout=30)  # Set-Cookie: connect.sid
    except requests.exceptions.RequestException:
        pass  # 쿠키 확보 실패해도 요청은 시도(다음 403에서 재수립)
    return s


def _get_session():
    global _session
    if _session is None:
        _session = _new_session()
    return _session


def _reset_session():
    global _session
    _session = _new_session()
    return _session


def _pace():
    """요청 최소 간격 강제 (레이트리밋 회피). 모든 _request 호출에 공통 적용."""
    global _last_req_ts
    dt = time.time() - _last_req_ts
    if dt < ETFCHECK_MIN_INTERVAL:
        time.sleep(ETFCHECK_MIN_INTERVAL - dt)
    _last_req_ts = time.time()


def _resolve_key(force=False):
    """Checkclient 키를 build.js에서 추출(프로세스 캐시 _KEY_TTL초). 실패 시 ETFCHECK_KEY 폴백.

    사이트가 키를 웹팩 모듈로 옮긴 뒤 수시 로테이션하므로 상수 추격은 실패한다(2026-07-22~27
    수집 전면 중단의 직접 원인). 매칭은 모듈 리터럴 `{key:"…"}` 하나뿐이며, 2건 이상 잡히면
    구조가 바뀐 것이므로 폴백을 쓴다(오탐 키로 전량 403 내는 쪽이 더 나쁘다)."""
    global _key_cache, _key_ts
    if _key_cache and not force and (time.time() - _key_ts) < _KEY_TTL:
        return _key_cache
    try:
        proxies = {'http': ETFCHECK_PROXY, 'https': ETFCHECK_PROXY} if ETFCHECK_PROXY else None
        resp = requests.get(
            ETFCHECK_BUILD_JS, timeout=60, proxies=proxies,
            headers={'User-Agent': 'Mozilla/5.0', 'Referer': ETFCHECK_HOME},
        )
        resp.raise_for_status()
        found = set(_KEY_RE.findall(resp.text))
        if len(found) == 1:
            key = found.pop()
            if key != _key_cache:
                logger.info('etfcheck 키 갱신: %s (len=%d)', key, len(key))
            _key_cache, _key_ts = key, time.time()
            return _key_cache
        logger.warning('etfcheck 키 추출 실패(매칭 %d건) — 폴백 상수 사용', len(found))
    except requests.exceptions.RequestException as e:
        logger.warning('etfcheck build.js 조회 실패(%s) — 폴백 상수 사용', e)
    _key_cache, _key_ts = (_key_cache or ETFCHECK_KEY), time.time()
    return _key_cache


def generate_checkclient():
    """시간 기반 Checkclient 인증 해시 생성 (30초 버킷).

    JS(build.js) 원본: n=key, a=String(floor(Date.now()/3e4)); r=''; for i: r+=n[a[i]-'0'].
    키가 8자라 버킷 숫자 8·9는 n[8]/n[9]=undefined → JS 문자열 결합이 'undefined'를 이어붙인다.
    이 동작을 그대로 복제한다(미복제 시 8·9 포함 버킷에서 해시 불일치 → 403)."""
    key = _resolve_key()
    bucket = str(int(time.time() * 1000 / ETFCHECK_BUCKET_MS))
    mapped = ''.join(
        key[i] if i < len(key) else 'undefined'
        for i in (int(ch) for ch in bucket)
    )
    return hashlib.sha256(mapped.encode()).hexdigest()


# 403(레이트리밋/IP 쿨다운) 시 재시도 전 대기(초). 세션을 새로 열고 이만큼 쉰 뒤 재시도.
# 쿨다운을 넉넉히 넘겨 IP 재자극을 막는다. 마지막 실패는 예외 → 수집기가 err 기록·retry_failed가 재차 시도.
_403_BACKOFF = [90, 180, 300]
# 네트워크 transient(Timeout/ConnectionError) 재시도 대기(초).
_NET_BACKOFF = [2, 5, 10]


def _do(sess, endpoint, params):
    return sess.get(
        ETFCHECK_BASE + endpoint,
        params=params,
        headers={
            'Checkclient': generate_checkclient(),
            # 2026-07-26 WAF가 axios 시그니처 검사 — 없으면 403
            'Accept': 'application/json, text/plain, */*',
            'X-Requested-With': 'XMLHttpRequest',
        },
        timeout=30,
    )


def _request(endpoint, params=None):
    """etfcheck API 호출 (세션 쿠키 + Checkclient 인증, 레이트리밋 대응 스로틀 내장).

    - 요청 최소 간격 강제(_pace) + ROTATE_EVERY건마다 세션 선제 로테이션.
    - 403(레이트리밋/IP 쿨다운): 세션 재수립 + 장기 백오프 후 재시도(_403_BACKOFF), 소진 시 예외.
    - Timeout/ConnectionError: 짧은 백오프 재시도(_NET_BACKOFF)."""
    global _req_count
    net_i = 0
    b403_i = 0
    while True:
        # 세션 선제 로테이션(per-session 카운트 리셋 겨냥)
        if _req_count > 0 and _req_count % ETFCHECK_ROTATE_EVERY == 0:
            _reset_session()
        _pace()
        sess = _get_session()
        try:
            resp = _do(sess, endpoint, params)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if net_i >= len(_NET_BACKOFF):
                raise
            time.sleep(_NET_BACKOFF[net_i]); net_i += 1
            continue
        _req_count += 1

        if resp.status_code in (401, 403):
            # 레이트리밋/세션만료/키 로테이션 → 키 재추출 + 세션 재수립 + 장기 백오프 후 재시도
            _resolve_key(force=True)
            _reset_session()
            if b403_i >= len(_403_BACKOFF):
                resp.raise_for_status()  # 소진 → HTTPError 전파
            time.sleep(_403_BACKOFF[b403_i]); b403_i += 1
            continue

        resp.raise_for_status()
        data = resp.json()
        if not data.get('success'):
            raise ValueError(f"API error: {data.get('message', 'unknown')}")
        return data.get('results', [])


def fetch_constituents(etf_code):
    """ETF 구성종목/비중 조회. Returns list of {stock_code, stock_name, weight, qty, px}

    qty=F16499(CU당 보유수량), px=F15001(종목 현재가). 값이 비정상('-'/공백/NaN)이면
    None — 종목 하나의 파싱 실패가 배치 전체를 죽이지 않도록 예외를 전파하지 않는다
    (과거 빈 stock_code 배치 실패 사고와 같은 방어 스타일)."""
    results = _request('getEtfPdfRankListWeight', {'code': etf_code})
    if not results:
        return []

    def _fnum(v):
        """방어적 float 변환 — 실패/NaN이면 None"""
        try:
            f = float(v)
            return f if f == f else None
        except (ValueError, TypeError):
            return None

    constituents = []
    for r in results:
        name = r.get('NAME', '')
        if not name:
            continue
        try:
            weight = float(r.get('WEIGHT', 0) or 0)
        except (ValueError, TypeError):
            weight = 0.0

        # 구성종목 코드: F16013_PDF 또는 F16013_T (ETF 자체 코드인 F16013과 다름)
        stock_code = r.get('F16013_PDF', '') or r.get('F16013_T', '')
        if not stock_code:
            isin = r.get('F16316', '') or r.get('F16012_PDF', '')
            if isin and len(isin) >= 9:
                stock_code = isin[3:9]

        constituents.append({
            'stock_code': stock_code,
            'stock_name': name,
            'weight': weight,
            'qty': _fnum(r.get('F16499')),
            'px': _fnum(r.get('F15001')),
        })
    return constituents


def fetch_etf_outline(etf_code):
    """ETF 기본정보 조회"""
    results = _request('getEtpItemOutline', {'code': etf_code})
    if results:
        return results[0] if isinstance(results, list) else results
    return None
