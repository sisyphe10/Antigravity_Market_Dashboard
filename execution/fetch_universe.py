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
import time
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
    """수익률 표시 — 일의 자리까지 (소수점 없음). 예: +15% / -3% / 0%."""
    if v is None or pd.isna(v):
        return ''
    return f'{v:+.0f}%'


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

        # 통화별 시가총액 표시 — KRW 종목은 억원, 다른 통화는 K/M/B 표기
        if marcap_local and currency == 'KRW':
            marcap_str = fmt_marcap_krw_eok(marcap_local)
            marcap_raw_eok = marcap_local / 1e8
        elif marcap_local:
            # 비KRW: B/M 단위로 (예: $1.2B, $35M). 통화 기호 별도.
            sym = {'USD': '$', 'JPY': '¥', 'TWD': 'NT$', 'CAD': 'C$', 'HKD': 'HK$', 'EUR': '€'}.get(currency, '')
            if marcap_local >= 1e9:
                marcap_str = f'{sym}{marcap_local/1e9:,.1f}B'
            elif marcap_local >= 1e6:
                marcap_str = f'{sym}{marcap_local/1e6:,.0f}M'
            else:
                marcap_str = f'{sym}{marcap_local:,.0f}'
            marcap_raw_eok = marcap_local  # 정렬용 raw (원화 환산 X, 통화별 raw)
        else:
            marcap_str = ''
            marcap_raw_eok = 0

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

    HEADER = ['#', '통화', '섹터', '티커', '기업명', '시가총액 (억원)', '가격',
              'YTD', '1D', '1W', '1M', '3M', '6M', '1Y',
              '시가총액 raw', 'YTD(P)', '1D(P)', '1W(P)', '1M(P)', '3M(P)', '6M(P)', '1Y(P)']
    values: list[list[str]] = [HEADER]

    # 병렬 fetch (worker 5로 줄여 rate limit 회피)
    results: dict[int, list[str]] = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
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

    # 부분 실패 보완 — 새 fetch 실패한 종목은 기존 universe.json 값 사용
    fallback_count = 0
    sequence_fixed: list[list[str]] = []
    for i, r in enumerate(rows):
        ticker = r['티커'].strip()
        if i in results:
            row = results[i].copy()
            # 시가총액 빈값일 때도 기존 값 fallback
            if (not row[5] or not row[14]) and ticker in existing_by_ticker:
                old = existing_by_ticker[ticker]
                if old[5] and old[14]:
                    row[5] = old[5]
                    row[14] = old[14]
                    fallback_count += 1
            sequence_fixed.append(row)
        elif ticker in existing_by_ticker:
            old = existing_by_ticker[ticker].copy()
            old[0] = str(i + 1)  # 순번 갱신
            sequence_fixed.append(old)
            fallback_count += 1
    values.extend(sequence_fixed)

    if fallback_count:
        print(f"  fallback 적용: {fallback_count}종목 (이전 universe.json 값 보존)")

    out = {
        'updated_at': datetime.now(KST).strftime('%Y-%m-%d %H:%M KST'),
        'values': values,
    }
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"[성공] universe.json: {len(values) - 1}종목 / {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
