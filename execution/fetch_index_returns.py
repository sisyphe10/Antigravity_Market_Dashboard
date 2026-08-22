"""yfinance에서 주요 지수의 1M 후행 수익률 → index_returns.json

universe.html의 RSI(1M) 컬럼이 사용. 각 종목 1M 수익률에서 해당 시장 지수의 1M 수익률을
빼면 RSI(1M).

지수 매핑 (우선순위 순):
  티커 prefix → 지수
  KRX           → KOSPI       (^KS11)
  KOSDAQ        → KOSDAQ      (^KQ11)
  NASDAQ        → NASDAQ      (^IXIC)
  NYSE, NYSEAMERICAN → S&P 500 (^GSPC)
  TPE           → TSEC        (^TWII)
  TYO           → NIKKEI      (^N225)
  TSE           → TSX         (^GSPTSE, S&P/TSX Composite — Toronto SE)
  HKG           → HSI         (^HSI)
  SHA, SHE      → CSI 300     (텐센트 sh000300 — 야후 000300.SS는 일봉 결측 구간)
  CRYPTO        → BTC         (BTC-USD)
  AMS, ETR, EPA → STOXX       (^STOXX50E)

1M 수익률 정의: 최근 거래일 종가 vs 21 거래일 전 종가.

KOSPI/KOSDAQ는 Wrap_NAV.xlsx '기준가' 시트(KIS 확정지수), 해외 지수는 yfinance.
기준가 시트 로드 실패 시 야후 폴백. (야후 ^KS11/^KQ11 지연·잠정값 회피)
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

import pandas as pd
import requests
import yfinance as yf

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_JSON = os.path.join(ROOT, 'index_returns.json')
HISTORY_JSON = os.path.join(ROOT, 'index_history.json')  # 일별 종가 (Universe 기간 RSI/MDD용)
N_HISTORY = 252                                           # 보존 거래일 수 (≈1년)

KST = timezone(timedelta(hours=9))

INDICES = [
    ('KOSPI',   '^KS11'),
    ('KOSDAQ',  '^KQ11'),
    ('NASDAQ',  '^IXIC'),
    ('S&P 500', '^GSPC'),
    ('TSEC',    '^TWII'),
    ('NIKKEI',  '^N225'),
    ('TSX',     '^GSPTSE'),
    ('HSI',     '^HSI'),
    ('STOXX',   '^STOXX50E'),
]

# 중국 A주(SHA/SHE) 벤치마크 = CSI 300 (沪深300, 상하이+선전 대형주 300).
# 야후 000300.SS는 일봉이 통째로 비는 구간이 관측돼(2026-08 실측: 7/17 다음 봉이 8/17)
# 부적합 — fetch_universe.py A주 primary와 동일하게 텐센트 gtimg 일봉을 사용한다.
TENCENT_INDICES = {'CSI 300': 'sh000300'}
INDICES.append(('CSI 300', 'sh000300'))

# 암호화폐(CRYPTO prefix) 벤치마크 = BTC (사용자 확정 2026-08-23). yfinance BTC-USD 일봉.
INDICES.append(('BTC', 'BTC-USD'))

LOOKBACK_DAYS = 21  # 거래일

NAV_INDICES = {'KOSPI', 'KOSDAQ'}  # 기준가 시트(KIS 확정지수)에서 읽을 한국 지수


def load_nav_kr_indices() -> dict:
    """Wrap_NAV.xlsx '기준가' 시트에서 KOSPI/KOSDAQ 일별 종가 Series dict 반환.
    실패/부재 시 {} → 호출부가 야후 폴백. (1M=21거래일, history=252거래일 모두 커버하도록 전체 시트 반환)"""
    try:
        nav_file = os.path.join(ROOT, 'Wrap_NAV.xlsx')
        df = pd.read_excel(nav_file, sheet_name='기준가')
        df.columns = [str(c).strip() for c in df.columns]  # 컬럼명 방어(공백/BOM)
        if 'Date' not in df.columns:
            return {}
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date').sort_index()
        out = {}
        for name in ('KOSPI', 'KOSDAQ'):
            if name in df.columns:
                s = df[name].dropna()
                if not s.empty:
                    out[name] = s
        return out
    except Exception as e:
        print(f'  ⚠️ 기준가 시트 로드 실패 → 야후 폴백: {e}')
        return {}


def fetch_tencent_index_closes(ticker: str, n: int = 400) -> 'pd.Series | None':
    """텐센트 gtimg 지수 일봉 종가 Series (날짜 오름차순). 실패 시 None."""
    url = ('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
           f'?param={ticker},day,,,{n},qfq')
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()['data'][ticker]
        rows = data.get('qfqday') or data.get('day') or []
        closes = {row[0]: float(row[2]) for row in rows if len(row) >= 3}
        if not closes:
            return None
        ser = pd.Series(closes)
        ser.index = pd.to_datetime(ser.index)
        return ser.sort_index()
    except Exception as e:
        print(f'  ⚠️ 텐센트 지수 {ticker} 실패: {e}')
        return None


def fetch_1m_return(name: str, ticker: str, nav_kr: dict) -> float | None:
    closes = None
    if name in nav_kr:
        closes = nav_kr[name]
    elif name in TENCENT_INDICES:
        closes = fetch_tencent_index_closes(ticker)
    else:
        today = datetime.now(tz=KST).date()
        start = today - timedelta(days=60)
        end = today + timedelta(days=1)
        hist = yf.Ticker(ticker).history(start=start.strftime('%Y-%m-%d'),
                                         end=end.strftime('%Y-%m-%d'),
                                         auto_adjust=False)
        closes = hist['Close'].dropna() if not hist.empty else None
    if closes is None or len(closes) < LOOKBACK_DAYS + 1:
        return None
    latest = float(closes.iloc[-1])
    prev = float(closes.iloc[-(LOOKBACK_DAYS + 1)])
    if prev == 0:
        return None
    return round(latest / prev - 1, 6)


def fetch_history(name: str, ticker: str, nav_kr: dict) -> dict:
    """1년 일별 종가 dict {YYYY-MM-DD: close} (최근 N_HISTORY). 실패 시 {}."""
    closes = None
    if name in nav_kr:
        closes = nav_kr[name]
    elif name in TENCENT_INDICES:
        closes = fetch_tencent_index_closes(ticker)
    else:
        try:
            hist = yf.Ticker(ticker).history(period='1y', auto_adjust=False)
        except Exception:
            return {}
        if hist.empty:
            return {}
        closes = hist['Close'].dropna()
    if closes is None or closes.empty:
        return {}
    out = {}
    for ts, v in closes.tail(N_HISTORY).items():
        out[ts.strftime('%Y-%m-%d')] = round(float(v), 2)
    return out


def main():
    nav_kr = load_nav_kr_indices()
    if nav_kr:
        print(f'  KOSPI/KOSDAQ = KIS 기준가 시트 사용 ({", ".join(nav_kr)})')
    returns = {}
    for name, ticker in INDICES:
        src = 'KIS' if name in nav_kr else ticker
        print(f'  {name} ({src}) ...', end=' ')
        try:
            r = fetch_1m_return(name, ticker, nav_kr)
            returns[name] = r
            print(f'{r * 100:+.2f}%' if r is not None else '데이터 없음')
        except Exception as e:
            print(f'에러: {e}')
            returns[name] = None

    out = {
        'updated_at': datetime.now(tz=KST).strftime('%Y-%m-%d %H:%M:%S KST'),
        'lookback_trading_days': LOOKBACK_DAYS,
        'returns_1m': returns,
    }
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'\n✅ {OUTPUT_JSON} 저장 ({len(returns)}개 지수)')

    # index_history.json — 일별 종가 시계열 (Universe '기간 수익률' 탭 RSI(기간)/MDD 계산용)
    histories = {name: fetch_history(name, ticker, nav_kr) for name, ticker in INDICES}
    all_dates = set()
    for h in histories.values():
        all_dates |= set(h.keys())
    dates = sorted(all_dates)[-N_HISTORY:]
    didx = {d: i for i, d in enumerate(dates)}
    indices = {}
    for name, h in histories.items():
        arr = [None] * len(dates)
        for d, v in h.items():
            jj = didx.get(d)
            if jj is not None:
                arr[jj] = v
        indices[name] = arr
    out2 = {
        'updated_at': datetime.now(tz=KST).strftime('%Y-%m-%d %H:%M:%S KST'),
        'dates': dates,
        'indices': indices,
    }
    with open(HISTORY_JSON, 'w', encoding='utf-8') as f:
        json.dump(out2, f, ensure_ascii=False)
    print(f'✅ {HISTORY_JSON} 저장 ({len(indices)}개 지수 × {len(dates)}일)')


if __name__ == '__main__':
    main()
