"""Universe 종목별 가격/수익률 → universe.json (Sheets 의존성 제거).

워크플로:
  1. universe_tickers.csv 읽기 (#, 통화, 섹터, 티커, 기업명) — 통화 컬럼은 무시하고 prefix로 결정
  2. 티커 prefix → yfinance ticker 변환 (KRX:006800 → 006800.KS 등)
  3. yfinance로 가격/수익률(YTD/1D/1W/1M/3M/6M/1Y)/시가총액 fetch (병렬)
  4. universe.json 생성 — Sheets API 응답 형식과 동일한 구조 (header row + values rows)
     → universe.html JS 변경 최소화

출력 스키마 (universe.json):
  {
    "updated_at": "2026-05-26 14:00 KST",
    "values": [
      ["#", "통화", "섹터", "티커", "기업명", "시가총액 (억원)", "가격", "YTD", "1D", "1W", "1M", "3M", "6M", "1Y", ...],
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
    if v is None or pd.isna(v):
        return ''
    return f'{v:+.2f}%'


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


def fetch_one(idx: int, raw_ticker: str, sector: str, name: str) -> list[str] | None:
    """단일 종목의 22개 컬럼 데이터 생성. 실패 시 None."""
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

        # 시가총액 (yfinance fast_info)
        marcap_local = None
        try:
            fi = t.fast_info
            marcap_local = float(fi.get('market_cap') or 0)
        except Exception:
            pass

        # KRW 환산 (간단하게 정적 환율 사용. 정확도가 중요하면 별도 env vars로 갱신)
        # 또는 KRW가 아닌 경우 그냥 시가총액만 표시 (단위 USD/JPY 등으로 헷갈리지만 일단)
        if currency == 'KRW':
            marcap_str = fmt_marcap_krw_eok(marcap_local)
            marcap_raw_eok = marcap_local / 1e8 if marcap_local else 0
        else:
            # USD/JPY 등은 그대로 단위로 표시 (대략. 정확한 KRW 환산은 후속 작업)
            marcap_str = f'{marcap_local:,.0f} ({currency})' if marcap_local else ''
            marcap_raw_eok = marcap_local or 0

        # 가격: 현지 통화 단위, 정수 또는 소수점 2자리
        if currency == 'KRW':
            price_str = f'{last:,.0f}'
        else:
            price_str = f'{last:,.2f}'

        # 22개 컬럼 (Sheets 헤더 그대로)
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
        ]
    except Exception as e:
        print(f"  Warning: {raw_ticker} ({yf_tk}): {e}")
        return None


def main() -> None:
    if not TICKERS_FILE.exists():
        raise RuntimeError(f"{TICKERS_FILE} 없음")
    rows: list[dict] = []
    with open(TICKERS_FILE, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    print(f"종목 수: {len(rows)}")

    HEADER = ['#', '통화', '섹터', '티커', '기업명', '시가총액 (억원)', '가격',
              'YTD', '1D', '1W', '1M', '3M', '6M', '1Y',
              '시가총액 raw', 'YTD(P)', '1D(P)', '1W(P)', '1M(P)', '3M(P)', '6M(P)', '1Y(P)']
    values: list[list[str]] = [HEADER]

    # 병렬 fetch
    results: dict[int, list[str]] = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {
            ex.submit(fetch_one, i + 1, r['티커'].strip(), r.get('섹터', '').strip(), r['기업명'].strip()): i
            for i, r in enumerate(rows)
        }
        done = 0
        for fut in as_completed(futures):
            i = futures[fut]
            row = fut.result()
            if row is not None:
                results[i] = row
            done += 1
            if done % 50 == 0:
                print(f"  진행: {done}/{len(rows)}")

    # 순서 보존
    for i in sorted(results):
        values.append(results[i])

    out = {
        'updated_at': datetime.now(KST).strftime('%Y-%m-%d %H:%M KST'),
        'values': values,
    }
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"[성공] universe.json: {len(values) - 1}종목 / {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
