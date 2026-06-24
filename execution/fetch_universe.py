"""Universe 종목별 가격/수익률 → universe.json (Sheets 의존성 제거).

워크플로:
  1. universe_tickers.csv 읽기 (#, 통화, 섹터, 티커, 기업명) — 통화 컬럼은 무시하고 prefix로 결정
  2. 티커 prefix → yfinance ticker 변환 (KRX:006800 → 006800.KS 등)
  3. yfinance로 가격/수익률(YTD/1D/1W/1M/3M/6M/1Y)/DD(52주 고점 대비)/시가총액 fetch (병렬)
  4. universe.json 생성 — Sheets API 응답 형식과 동일한 구조 (header row + values rows)
     → universe.html JS 변경 최소화

출력 스키마 (universe.json):
  {
    "updated_at": "2026-05-26 14:00 KST",
    "values": [
      ["#", "통화", "섹터", "티커", "기업명", "시가총액 (억원)", "가격", "YTD", "1D", "1W", "1M", "3M", "6M", "1Y", ..., "DD"],
      ["1", "KRW", "증권", "KRX:006800", "미래에셋증권", "3조9,001억", "11500", "1.20%", "-0.50%", ...],
      ...
    ]
  }
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
TICKERS_FILE = ROOT / 'universe_tickers.csv'
OUTPUT_FILE = ROOT / 'universe.json'
HISTORY_FILE = ROOT / 'universe_history.json'   # 종목별 일별 종가 시계열 (기간 수익률 탭용)
N_HISTORY = 252                                  # 보존 거래일 수 (≈1년)

# 티커 prefix → yfinance suffix + 통화 매핑
PREFIX_MAP = {
    'KRX':         {'suffix': '.KS', 'currency': 'KRW'},   # KOSPI
    'KOSDAQ':      {'suffix': '.KQ', 'currency': 'KRW'},
    'NASDAQ':      {'suffix': '',    'currency': 'USD'},
    'NYSE':        {'suffix': '',    'currency': 'USD'},
    'NYSEAMERICAN':{'suffix': '',    'currency': 'USD'},
    'TPE':         {'suffix': '.TW', 'currency': 'TWD'},   # 대만 (TSEC)
    'TYO':         {'suffix': '.T',  'currency': 'JPY'},   # 도쿄 (NIKKEI)
    'TSE':         {'suffix': '.TO', 'currency': 'CAD'},   # 토론토
    'HKG':         {'suffix': '.HK', 'currency': 'HKD'},   # 홍콩
    'AMS':         {'suffix': '.AS', 'currency': 'EUR'},   # 암스테르담
    'ETR':         {'suffix': '.DE', 'currency': 'EUR'},   # 프랑크푸르트 (XETRA)
    'EPA':         {'suffix': '.PA', 'currency': 'EUR'},   # 파리
}

# 통화 → KRW 환율 fetch (yfinance Forex 페어). 시가총액 KRW 환산용.
def fetch_fx_to_krw() -> dict[str, float]:
    """USD/JPY/EUR/HKD/TWD/CAD → KRW 환율 dict. 실패 시 fallback 환율 사용."""
    pairs = {
        'USD': 'KRW=X',       # USDKRW
        'JPY': 'JPYKRW=X',
        'EUR': 'EURKRW=X',
        'HKD': 'HKDKRW=X',
        'TWD': 'TWDKRW=X',
        'CAD': 'CADKRW=X',
    }
    # 폴백 (yfinance fetch 실패 시) — 2026-05 대략치
    fallback = {'USD': 1380, 'JPY': 9.0, 'EUR': 1500, 'HKD': 177, 'TWD': 43, 'CAD': 1010}
    rates: dict[str, float] = {'KRW': 1.0}
    for ccy, pair in pairs.items():
        try:
            hist = yf.Ticker(pair).history(period='5d', auto_adjust=False)
            if not hist.empty:
                rates[ccy] = float(hist['Close'].dropna().iloc[-1])
            else:
                rates[ccy] = fallback[ccy]
                print(f"  Warning: {pair} 환율 fetch 실패 → fallback {fallback[ccy]}")
        except Exception as e:
            rates[ccy] = fallback[ccy]
            print(f"  Warning: {pair} 예외 → fallback {fallback[ccy]} ({e})")
    return rates


def to_yf_ticker(raw: str) -> tuple[str | None, str | None]:
    """KRX:006800 → ('006800.KS', 'KRW'). 매핑 실패 시 (None, None)."""
    if ':' not in raw:
        return None, None
    prefix, code = raw.split(':', 1)
    m = PREFIX_MAP.get(prefix)
    if not m:
        return None, None
    return code + m['suffix'], m['currency']


def fmt_pct(v: float | None) -> str:
    """수익률 표시 — 일의 자리까지 (소수점 없음). 예: +15% / -3% / 0%."""
    if v is None or pd.isna(v):
        return ''
    return f'{v:+.0f}%'


def fmt_dd(v: float | None) -> str:
    """DD(52주 고점 대비 낙폭) 표시 — 항상 0% 이하. 예: -12% / 0%."""
    if v is None or pd.isna(v):
        return ''
    return f'{v:.0f}%'


def fmt_marcap_krw_eok(marcap_krw: float | None) -> str:
    """원화 시가총액(원) → '12조3,456억' 또는 '999억' 형식. KRW가 아니면 환산은 호출자 책임."""
    if marcap_krw is None or marcap_krw <= 0:
        return ''
    eok = int(marcap_krw / 1e8)
    jo = eok // 10000
    rest = eok % 10000
    if jo > 0:
        return f'{jo:,}조{rest:,}억' if rest > 0 else f'{jo:,}조'
    return f'{eok:,}억'


def closes_to_hist(closes: 'pd.Series', currency: str, n: int = N_HISTORY) -> dict:
    """pandas Close Series → {'YYYY-MM-DD': 종가} 최근 n 거래일.

    universe_history.json용 일별 종가 덤프. KRW/JPY는 정수, 그 외 소수 2자리(표시값과 동일 정밀도).
    """
    is_int = currency in ('KRW', 'JPY')
    out: dict = {}
    for ts, v in closes.tail(n).items():
        if v is None or pd.isna(v):
            continue
        d = ts.strftime('%Y-%m-%d')
        out[d] = int(round(float(v))) if is_int else round(float(v), 2)
    return out


def dict_to_hist(prices: dict, currency: str, n: int = N_HISTORY) -> dict:
    """{'YYYY-MM-DD': close} dict → 최근 n개만 추려 반올림. 네이버 폴백 시리즈용."""
    is_int = currency in ('KRW', 'JPY')
    out: dict = {}
    for d, v in sorted(prices.items())[-n:]:
        if v is None:
            continue
        out[d] = int(round(float(v))) if is_int else round(float(v), 2)
    return out


# 통화별 anomaly threshold — 각 시장의 일일 가격제한을 약간 초과하는 값이 의심점.
# KRW/JPY: ±30%, TWD: ±10%, 가격제한 없는 시장(USD/EUR/HKD/CAD): 50% (실적 갭업/뉴스 변동 흡수).
THRESHOLD_BY_CURRENCY = {
    'KRW': 0.30,
    'JPY': 0.30,
    'TWD': 0.10,
    'USD': 0.50,
    'EUR': 0.50,
    'HKD': 0.50,
    'CAD': 0.50,
}
DEFAULT_ANOMALY_THRESHOLD = 0.50


def fetch_naver_kr(code: str, days: int = 400) -> dict[str, int]:
    """네이버 siseJson API로 KRX/KOSDAQ **수정주가** 종가 시리즈 fetch.

    requestType=1은 무상증자·액면분할 권리락 비율로 자동 조정된 가격을 반환.
    예: 코미코 2026-05-12 1:1 무상증자 권리락 → 5/22 이전 가격이 절반으로 자동 조정.
    1Y(252영업일) lookback 위해 days=400 (≈영업일 270개) 기본.

    응답 형식: [['날짜','시가','고가','저가','종가','거래량','외국인소진율'], ["20260527",94200,98600,93000,93000,22548,19.44], ...]
    JavaScript 배열 (trailing 공백/줄바꿈) — 정규식으로 row 추출.
    """
    import re
    end_d = datetime.now(KST).strftime('%Y%m%d')
    start_d = (datetime.now(KST) - timedelta(days=days)).strftime('%Y%m%d')
    url = (
        f'https://api.finance.naver.com/siseJson.naver?'
        f'symbol={code}&requestType=1&timeframe=day&startTime={start_d}&endTime={end_d}'
    )
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode('utf-8', errors='replace')
    except Exception:
        return {}
    # row 형식: ["20260527", 94200, 98600, 93000, 93000, 22548, 19.44]
    # 날짜 다음 3개(시가/고가/저가) skip, 4번째가 수정주가 종가. 종가는 float 가능.
    pattern = r'\["(\d{8})",\s*[\d.]+,\s*[\d.]+,\s*[\d.]+,\s*([\d.]+),'
    prices: dict[str, int] = {}
    for date_str, close_str in re.findall(pattern, body):
        formatted = f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}'
        prices[formatted] = int(float(close_str))
    return prices


# 네이버 해외주식 API 커버리지 — 이상치 팩트체크용 독립 소스.
# 일본(.T)·홍콩(.HK)은 야후와 동일 suffix 직매핑, 미국 3거래소는 suffix가 비일관
# (KO=무suffix, NVDA.O, UMAC.K)이라 ac 검색으로 reutersCode 해석. 대만/유럽/캐나다 미커버.
NAVER_WORLD_DIRECT_SUFFIX = {'TYO': '.T', 'HKG': '.HK'}
US_PREFIXES = {'NASDAQ', 'NYSE', 'NYSEAMERICAN'}


def _http_json(url: str):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode('utf-8', errors='replace'))
    except Exception:
        return None


def resolve_naver_world_code(prefix: str, code: str) -> str | None:
    """티커 → 네이버 해외주식 reutersCode. 실패/미커버 시 None."""
    if prefix in NAVER_WORLD_DIRECT_SUFFIX:
        return code + NAVER_WORLD_DIRECT_SUFFIX[prefix]
    if prefix in US_PREFIXES:
        d = _http_json(f'https://ac.stock.naver.com/ac?q={code}&target=stock')
        if not d:
            return None
        for item in d.get('items', []):
            if (item.get('category') == 'stock' and item.get('nationCode') == 'USA'
                    and item.get('code') == code):
                return item.get('reutersCode') or None
    return None


def fetch_naver_world(reuters_code: str) -> dict[str, float]:
    """네이버 해외주식 일봉 종가 dict {YYYY-MM-DD: close}. YTD 범위 반환."""
    d = _http_json(f'https://api.stock.naver.com/chart/foreign/item/{reuters_code}?periodType=dayCandle')
    prices: dict[str, float] = {}
    if not d:
        return prices
    for p in d.get('priceInfos', []):
        ld, cp = p.get('localDate'), p.get('closePrice')
        if ld and cp:
            prices[f'{ld[:4]}-{ld[4:6]}-{ld[6:]}'] = float(cp)
    return prices


def confirm_anomaly_real(prefix: str, code: str, prev_d: str, cur_d: str, yf_pct: float) -> bool:
    """이상치 팩트체크 — 독립 소스(네이버 해외주식)에서 같은 날 같은 점프가 재현되면 실제 급등.

    실제 급등(UMAC 2026-05-28 +57% 펜타곤 드론 펀딩)은 모든 소스에 동일하게 나타나고,
    Yahoo 데이터 오류(분할·무증 미반영)는 Yahoo에만 나타난다는 점을 이용.
    허용 오차: max(5%p, |점프|의 20%). 데이터 없음/미커버 시 False(보수적 blank 유지).
    """
    rc = resolve_naver_world_code(prefix, code)
    if not rc:
        return False
    prices = fetch_naver_world(rc)
    p0, p1 = prices.get(prev_d), prices.get(cur_d)
    if not p0 or not p1:
        return False
    nv_pct = (p1 / p0 - 1) * 100
    return abs(nv_pct - yf_pct) <= max(5.0, abs(yf_pct) * 0.2)


def compute_returns_from_dict(prices: dict) -> dict | None:
    """{YYYY-MM-DD: close} dict → {last, ytd, 1d, 1w, 1m, 3m, 6m, 1y, dd} pct dict.

    영업일 기반 lookback (yfinance fetch_one과 동일 로직). YTD는 연초 이후 첫 거래일 기준.
    dd는 최근 252거래일(당일 포함) 최고 종가 대비 낙폭.
    """
    if not prices or len(prices) < 2:
        return None
    sorted_d = sorted(prices.keys())
    last = float(prices[sorted_d[-1]])

    def lookback(n: int) -> float | None:
        if len(sorted_d) <= n:
            return None
        base = float(prices[sorted_d[-n - 1]])
        if base <= 0:
            return None
        return (last / base - 1) * 100

    year_start = f'{datetime.now(KST).year}-01-01'
    ytd_dates = [d for d in sorted_d if d >= year_start]
    ytd = None
    if ytd_dates:
        base = float(prices[ytd_dates[0]])
        if base > 0:
            ytd = (last / base - 1) * 100

    high_1y = max(float(prices[d]) for d in sorted_d[-252:])
    dd = (last / high_1y - 1) * 100 if high_1y > 0 else None

    return {
        'last': last,
        'ytd': ytd,
        '1d': lookback(1),
        '1w': lookback(5),
        '1m': lookback(21),
        '3m': lookback(63),
        '6m': lookback(126),
        '1y': lookback(252),
        'dd': dd,
    }


def detect_data_anomaly(closes: 'pd.Series', threshold: float = 0.30, window: int = 7):
    """
    최근 window 영업일에서 인접 일간 절대변동률이 threshold를 **초과**하면
    (prev_date, prev_close, curr_date, curr_close, pct) 반환. 없으면 None.

    window=7 근거: Yahoo 데이터 오류(분할·무증 미반영)는 며칠 내 정정되어 시리즈에서
    사라지지만, 실제 급등(UMAC 2026-05-28 +57% 펜타곤 드론 펀딩 사례)은 영구히 남는다.
    창을 짧게 잡으면 오래된 실제 급등이 오탐으로 계속 blank되는 문제를 자연 해소.

    각 시장의 일일 가격제한을 초과하는 점프는 yfinance/Yahoo의 분할·병합·무증·유증
    데이터 오류 가능성 (코미코 2026-05-18 -51.7% 사례). threshold는 통화별로
    THRESHOLD_BY_CURRENCY를 통해 fetch_one()에서 전달.

    EPS 마진: 161200/124000 = 1.30000000000000004 같은 부동소수점 노이즈를 흡수해
    정확한 상한가/하한가가 false positive로 잡히지 않게 함.
    """
    EPS = 1e-6
    recent = closes.tail(window + 1)
    if len(recent) < 2:
        return None
    pct = recent.pct_change()
    abs_pct = pct.abs()
    if abs_pct.max() <= threshold + EPS:
        return None
    max_idx = abs_pct.idxmax()
    loc = recent.index.get_loc(max_idx)
    if loc == 0:
        return None
    prev_idx = recent.index[loc - 1]
    return (
        prev_idx.strftime('%Y-%m-%d'),
        float(recent.loc[prev_idx]),
        max_idx.strftime('%Y-%m-%d'),
        float(recent.loc[max_idx]),
        float(pct.loc[max_idx]) * 100,
    )


def fetch_one(idx: int, raw_ticker: str, sector: str, name: str, fx_to_krw: dict[str, float]) -> list[str] | None:
    """단일 종목의 23개 컬럼 데이터 생성. 실패 시 None. fx_to_krw: 통화 → KRW 환율."""
    yf_tk, currency = to_yf_ticker(raw_ticker)
    if not yf_tk:
        return None
    try:
        t = yf.Ticker(yf_tk)
        hist = t.history(period='2y', auto_adjust=False)
        if hist.empty or len(hist) < 2:
            return None
        closes = hist['Close'].dropna()
        if len(closes) < 2:
            return None
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2])

        # Sanity check — 통화별 가격제한 초과 점프는 yfinance 데이터 오류 가능성
        # (코미코 5/18 -51.7% 같은 사례). 적발 시 수익률 모두 blank 처리.
        threshold = THRESHOLD_BY_CURRENCY.get(currency, DEFAULT_ANOMALY_THRESHOLD)
        anomaly = detect_data_anomaly(closes, threshold=threshold, window=7)

        # 기간별 lookback (거래일 기준)
        def lookback_pct(days: int) -> float | None:
            if len(closes) <= days:
                return None
            base = float(closes.iloc[-days - 1])
            if base <= 0:
                return None
            return (last / base - 1) * 100

        # YTD: 1월 1일 이후 첫 거래일 종가 기준
        year_start = pd.Timestamp(datetime.now(KST).year, 1, 1).tz_localize(closes.index.tz)
        ytd_slice = closes[closes.index >= year_start]
        ytd = None
        if not ytd_slice.empty:
            base = float(ytd_slice.iloc[0])
            if base > 0:
                ytd = (last / base - 1) * 100

        ret_1d = lookback_pct(1)
        ret_1w = lookback_pct(5)
        ret_1m = lookback_pct(21)
        ret_3m = lookback_pct(63)
        ret_6m = lookback_pct(126)
        ret_1y = lookback_pct(252)

        # DD: 52주(252거래일, 당일 포함) 최고 종가 대비 현재 낙폭. 항상 0% 이하.
        high_1y = float(closes.tail(252).max())
        dd = (last / high_1y - 1) * 100 if high_1y > 0 else None

        # 시가총액 — yfinance fast_info.market_cap이 항상 None 반환하는 bug 우회.
        # info['marketCap']은 정상 동작 (단, 호출당 추가 API request 발생).
        # rate limit (특히 TYO 종목) 회피용 1회 재시도 + sleep.
        marcap_local = None
        for attempt in range(2):
            try:
                info = t.info or {}
                mc = info.get('marketCap')
                if mc:
                    marcap_local = float(mc)
                    break
                # info는 받았는데 marketCap만 누락 — 재시도 의미 없음
                break
            except Exception as e:
                if 'Too Many Requests' in str(e) and attempt == 0:
                    time.sleep(3)
                    continue
                break

        # 모든 종목 시가총액을 KRW로 환산해서 표시 + 정렬용 raw도 KRW 억원으로 통일.
        # 섹터 가중평균(RSI 등)이 의미 있으려면 모든 종목 시총이 같은 단위여야 함.
        if marcap_local:
            fx = fx_to_krw.get(currency, 1.0)
            marcap_krw = marcap_local * fx
            marcap_str = fmt_marcap_krw_eok(marcap_krw)
            marcap_raw_eok = marcap_krw / 1e8
        else:
            marcap_str = ''
            marcap_raw_eok = 0

        # 가격: 현지 통화 단위, 정수 또는 소수점 2자리
        if currency == 'KRW':
            price_str = f'{last:,.0f}'
        else:
            price_str = f'{last:,.2f}'

        # anomaly 적발 시: 1차로 독립 소스(네이버 해외주식) 팩트체크 — 실제 급등이면 통과.
        # 미확인이면 한국 종목은 네이버 fallback으로 재계산, 그 외는 blank.
        if anomaly and currency != 'KRW' and ':' in raw_ticker:
            prev_d, prev_p, cur_d, cur_p, pct = anomaly
            prefix, code = raw_ticker.split(':', 1)
            if confirm_anomaly_real(prefix, code, prev_d, cur_d, pct):
                print(f"  Info: {raw_ticker} ({name}) jump {prev_d} → {cur_d} ({pct:+.1f}%) "
                      f"confirmed real by Naver cross-check. Kept.")
                anomaly = None
        if anomaly:
            prev_d, prev_p, cur_d, cur_p, pct = anomaly
            if currency == 'KRW' and ':' in raw_ticker:
                code = raw_ticker.split(':', 1)[1]
                naver_prices = fetch_naver_kr(code)
                rets = compute_returns_from_dict(naver_prices)
                if rets:
                    print(f"  Info: {raw_ticker} ({name}) yfinance anomaly "
                          f"({prev_d} → {cur_d}, {pct:+.1f}%) → Naver fallback applied.")
                    naver_last = rets['last']
                    naver_price_str = f'{naver_last:,.0f}'
                    return [
                        str(idx), currency, sector, raw_ticker, name,
                        marcap_str, naver_price_str,
                        fmt_pct(rets['ytd']),
                        fmt_pct(rets['1d']),
                        fmt_pct(rets['1w']),
                        fmt_pct(rets['1m']),
                        fmt_pct(rets['3m']),
                        fmt_pct(rets['6m']),
                        fmt_pct(rets['1y']),
                        f'{int(marcap_raw_eok):,}' if marcap_raw_eok else '',
                        '', '', '', '', '', '', '',
                        fmt_dd(rets['dd']),
                    ], dict_to_hist(naver_prices, currency)
                else:
                    print(f"  Warning: {raw_ticker} ({name}) yfinance anomaly "
                          f"({prev_d} → {cur_d}, {pct:+.1f}%), Naver fallback also failed. Blanked.")
            else:
                print(f"  Warning: {raw_ticker} ({name}) yfinance anomaly — "
                      f"{prev_d} {prev_p:,.0f} → {cur_d} {cur_p:,.0f} ({pct:+.1f}%). Returns blanked.")
            return [
                str(idx), currency, sector, raw_ticker, name,
                marcap_str, price_str,
                '', '', '', '', '', '', '',  # YTD/1D/1W/1M/3M/6M/1Y
                f'{int(marcap_raw_eok):,}' if marcap_raw_eok else '',
                '', '', '', '', '', '', '',
                '',  # DD — anomaly 데이터로는 신뢰 불가, blank
            ], {}  # 시계열도 신뢰 불가 → main에서 직전 universe_history.json 값으로 폴백

        # 23개 컬럼 (Sheets 헤더 + DD)
        return [
            str(idx),
            currency,
            sector,
            raw_ticker,
            name,
            marcap_str,
            price_str,
            fmt_pct(ytd),
            fmt_pct(ret_1d),
            fmt_pct(ret_1w),
            fmt_pct(ret_1m),
            fmt_pct(ret_3m),
            fmt_pct(ret_6m),
            fmt_pct(ret_1y),
            # 컬럼 14: 시가총액 raw 정렬용 (억원 단위)
            f'{int(marcap_raw_eok):,}' if marcap_raw_eok else '',
            # 컬럼 15~21: P(피크대비) 메트릭 — 옛 Sheets 컬럼명 'YTD(P) ... 1Y(P)'. 데이터 출처 미상이라 빈값.
            '', '', '', '', '', '', '',
            # 컬럼 22: DD (52주 고점 대비 낙폭)
            fmt_dd(dd),
        ], closes_to_hist(closes, currency)
    except Exception as e:
        print(f"  Warning: {raw_ticker} ({yf_tk}): {e}")
        return None


def _load_existing_by_ticker() -> dict[str, list[str]]:
    """기존 universe.json에서 티커 → row 매핑. 부분 실패 시 fallback용."""
    if not OUTPUT_FILE.exists():
        return {}
    try:
        with open(OUTPUT_FILE, encoding='utf-8') as f:
            d = json.load(f)
        return {r[3]: r for r in d.get('values', [])[1:] if len(r) > 3}
    except Exception:
        return {}


def _load_existing_history() -> dict:
    """기존 universe_history.json → {ticker: {date: close}}. 부분 실패 종목 폴백용."""
    if not HISTORY_FILE.exists():
        return {}
    try:
        with open(HISTORY_FILE, encoding='utf-8') as f:
            d = json.load(f)
        dates = d.get('dates', [])
        out: dict = {}
        for tk, arr in d.get('stocks', {}).items():
            out[tk] = {dates[i]: v for i, v in enumerate(arr) if i < len(dates) and v is not None}
        return out
    except Exception:
        return {}


def _write_history(hist_by_ticker: dict) -> None:
    """{ticker: {date: close}} → universe_history.json {dates:[...], stocks:{ticker:[정렬된 종가|null]}}.

    전 종목 거래일 합집합을 공통 날짜축(최근 N_HISTORY)으로 잡고, 종목별 배열을 그 축에 정렬.
    시장별 휴일이 달라도 같은 축으로 정렬됨(휴장일은 null). 프런트는 ticker로 join.
    """
    all_dates: set = set()
    for h in hist_by_ticker.values():
        all_dates.update(h.keys())
    dates = sorted(all_dates)[-N_HISTORY:]
    date_index = {d: i for i, d in enumerate(dates)}
    stocks: dict = {}
    for tk, h in hist_by_ticker.items():
        arr = [None] * len(dates)
        has = False
        for d, v in h.items():
            j = date_index.get(d)
            if j is not None:
                arr[j] = v
                has = True
        if has:
            stocks[tk] = arr
    out = {
        'updated_at': datetime.now(KST).strftime('%Y-%m-%d %H:%M KST'),
        'dates': dates,
        'stocks': stocks,
    }
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"[성공] universe_history.json: {len(stocks)}종목 × {len(dates)}일 / {HISTORY_FILE}")


def main() -> None:
    if not TICKERS_FILE.exists():
        raise RuntimeError(f"{TICKERS_FILE} 없음")
    rows: list[dict] = []
    with open(TICKERS_FILE, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    print(f"종목 수: {len(rows)}")

    existing_by_ticker = _load_existing_by_ticker()
    print(f"기존 universe.json: {len(existing_by_ticker)}종목 (fallback 가능)")
    existing_hist = _load_existing_history()

    # 환율 fetch (KRW 환산용)
    print("환율 fetch 중 (USD/JPY/EUR/HKD/TWD/CAD → KRW)...")
    fx_to_krw = fetch_fx_to_krw()
    print(f"  환율: {', '.join(f'{k}={v:.2f}' for k, v in fx_to_krw.items() if k != 'KRW')}")

    HEADER = ['#', '통화', '섹터', '티커', '기업명', '시가총액 (억원)', '가격',
              'YTD', '1D', '1W', '1M', '3M', '6M', '1Y',
              '시가총액 raw', 'YTD(P)', '1D(P)', '1W(P)', '1M(P)', '3M(P)', '6M(P)', '1Y(P)',
              'DD']
    values: list[list[str]] = [HEADER]

    # 병렬 fetch (worker 5로 줄여 rate limit 회피). fetch_one은 (row, hist) 튜플 반환.
    results: dict[int, tuple] = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {
            ex.submit(fetch_one, i + 1, r['티커'].strip(), r.get('섹터', '').strip(), r['기업명'].strip(), fx_to_krw): i
            for i, r in enumerate(rows)
        }
        done = 0
        for fut in as_completed(futures):
            i = futures[fut]
            res = fut.result()
            if res is not None:
                results[i] = res
            done += 1
            if done % 50 == 0:
                print(f"  진행: {done}/{len(rows)}")

    # 전 종목 fetch 실패(yfinance 전면 rate-limit/차단)면 이전 universe.json을 덮지 않고
    # red 처리 — all-carry-forward로 stale 파일을 쓰면 신선도 모니터가 못 잡는다.
    if not results:
        print("[치명] 전 종목 fetch 실패 → universe.json 미갱신(이전 값 보존), exit 1")
        sys.exit(1)

    # 부분 실패 보완 — 새 fetch 실패한 종목은 기존 universe.json 값 사용
    fallback_count = 0
    sequence_fixed: list[list[str]] = []
    hist_by_ticker: dict = {}   # ticker → {date: close} (universe_history.json용)
    for i, r in enumerate(rows):
        ticker = r['티커'].strip()
        if i in results:
            row, hist = results[i]
            row = row.copy()
            # 시가총액 빈값일 때도 기존 값 fallback
            if (not row[5] or not row[14]) and ticker in existing_by_ticker:
                old = existing_by_ticker[ticker]
                if old[5] and old[14]:
                    row[5] = old[5]
                    row[14] = old[14]
                    fallback_count += 1
            sequence_fixed.append(row)
            # 시계열: 신규 수집분 우선, 비었으면(anomaly blank 등) 직전 universe_history.json 값 보존
            h = hist if hist else existing_hist.get(ticker, {})
            if h:
                hist_by_ticker[ticker] = h
        elif ticker in existing_by_ticker:
            old = existing_by_ticker[ticker].copy()
            old[0] = str(i + 1)  # 순번 갱신
            # 구버전(DD 없는 22컬럼) row는 헤더 길이에 맞춰 패딩 — JSON 직사각형 유지
            while len(old) < len(HEADER):
                old.append('')
            sequence_fixed.append(old)
            fallback_count += 1
            # fetch 실패 종목도 직전 시계열 보존
            if ticker in existing_hist:
                hist_by_ticker[ticker] = existing_hist[ticker]
    values.extend(sequence_fixed)

    if fallback_count:
        print(f"  fallback 적용: {fallback_count}종목 (이전 universe.json 값 보존)")

    # data_date: 이번 run에서 실제 fetch 성공한 종목들의 최신 시세 일자.
    # carry-forward로 universe.json이 항상 갱신돼도 신선도 모니터가 '진짜' 데이터 일자를
    # 보게 별도 기록 (updated_at은 매 run now()라 stale 판별에 못 씀).
    fresh_dates = [max(h) for (_row, h) in results.values() if h]
    data_date = max(fresh_dates) if fresh_dates else None

    out = {
        'updated_at': datetime.now(KST).strftime('%Y-%m-%d %H:%M KST'),
        'data_date': data_date,
        'values': values,
    }
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"[성공] universe.json: {len(values) - 1}종목, data_date={data_date} / {OUTPUT_FILE}")

    _write_history(hist_by_ticker)


if __name__ == '__main__':
    main()
