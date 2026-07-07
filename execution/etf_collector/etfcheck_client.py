"""etfcheck.co.kr 내부 API 클라이언트"""
import hashlib
import time
import json
import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

ETFCHECK_BASE = 'https://www.etfcheck.co.kr/user/etp/'
# 2026-07-08 사이트 개편: 키 '4lm@flEh68'→'er@#$dfe^fd12', 버킷 60s→30s, Referer 필수화 (전부 403 원인)
ETFCHECK_KEY = 'er@#$dfe^fd12'
ETFCHECK_BUCKET_MS = 30000


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
    resp = requests.get(
        ETFCHECK_BASE + endpoint,
        params=params,
        headers={
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://www.etfcheck.co.kr/',  # 2026-07-08부터 필수 (없으면 403)
            'Checkclient': generate_checkclient(),
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get('success'):
        raise ValueError(f"API error: {data.get('message', 'unknown')}")
    return data.get('results', [])


def fetch_constituents(etf_code):
    """ETF 구성종목/비중 조회. Returns list of {stock_code, stock_name, weight}"""
    results = _request('getEtfPdfRankListWeight', {'code': etf_code})
    if not results:
        return []

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
        })
    return constituents


def fetch_etf_outline(etf_code):
    """ETF 기본정보 조회"""
    results = _request('getEtpItemOutline', {'code': etf_code})
    if results:
        return results[0] if isinstance(results, list) else results
    return None
