"""etfcheck.co.kr 내부 API 클라이언트"""
import os
import hashlib
import time
import json
import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

ETFCHECK_BASE = 'https://www.etfcheck.co.kr/user/etp/'
# 2026-07-08 사이트 개편: 키 '4lm@flEh68'→'er@#$dfe^fd12', 버킷 60s→30s, Referer 필수화 (전부 403 원인)
# 2026-07-21 키 재로테이션: 'er@#$dfe^fd12'→'#$dser#GVEWS329@' (버킷 30s 동일). build.js 내
#   axios.interceptors.request 의 n="#$dser#GVEWS329@" 에서 추출·검증(200/success). [[project_antigravity_active_etf_alert]]
ETFCHECK_KEY = '#$dser#GVEWS329@'
ETFCHECK_BUCKET_MS = 30000

# 2026-07-21 맥미니 공인 IP가 etfcheck WAF에 IP 차단(정적 파일까지 403). 현 운영은 수집 자체를
#   Oracle VM(직결 200)에서 실행하므로 프록시 불필요(VM엔 ETFCHECK_PROXY 미설정 → 직결). 이 훅은
#   선택적 dormant 옵션으로 남겨둔다(설정 시 requests가 해당 SOCKS/HTTP 프록시로 우회).
ETFCHECK_PROXY = os.environ.get('ETFCHECK_PROXY') or None


def generate_checkclient():
    """시간 기반 Checkclient 인증 해시 생성 (30초 버킷)"""
    bucket = str(int(time.time() * 1000 / ETFCHECK_BUCKET_MS))
    mapped = ''.join(ETFCHECK_KEY[int(ch)] for ch in bucket)
    return hashlib.sha256(mapped.encode()).hexdigest()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError)),
    reraise=True,
)
def _request(endpoint, params=None):
    """etfcheck API 호출 (timeout 30s, transient 실패 시 최대 3회 retry with exponential backoff)"""
    proxies = {'http': ETFCHECK_PROXY, 'https': ETFCHECK_PROXY} if ETFCHECK_PROXY else None
    resp = requests.get(
        ETFCHECK_BASE + endpoint,
        params=params,
        headers={
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://www.etfcheck.co.kr/',  # 2026-07-08부터 필수 (없으면 403)
            'Checkclient': generate_checkclient(),
        },
        proxies=proxies,
        timeout=30,
    )
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
