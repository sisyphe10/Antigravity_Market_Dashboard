"""etfcheck.co.kr 내부 API 클라이언트"""
import hashlib
import time
import urllib.request
import urllib.parse
import json
import logging

ETFCHECK_BASE = 'https://www.etfcheck.co.kr/user/etp/'
ETFCHECK_KEY = '4lm@flEh68'


def generate_checkclient():
    """���간 기반 Checkclient 인증 해시 생성"""
    minutes = str(int(time.time() * 1000 / 60000))
    mapped = ''.join(ETFCHECK_KEY[int(ch)] for ch in minutes)
    return hashlib.sha256(mapped.encode()).hexdigest()


def _request(endpoint, params=None):
    """etfcheck API 호출"""
    url = ETFCHECK_BASE + endpoint
    if params:
        url += '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Checkclient': generate_checkclient(),
    })
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read().decode())
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
