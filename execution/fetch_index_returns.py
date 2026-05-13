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
  TSE           → NIKKEI      (^N225)
  HKG           → HSI         (^HSI)
  AMS, ETR, EPA → STOXX       (^STOXX50E)

1M 수익률 정의: 최근 거래일 종가 vs 21 거래일 전 종가.
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

import yfinance as yf

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_JSON = os.path.join(ROOT, 'index_returns.json')

KST = timezone(timedelta(hours=9))

INDICES = [
    ('KOSPI',   '^KS11'),
    ('KOSDAQ',  '^KQ11'),
    ('NASDAQ',  '^IXIC'),
    ('S&P 500', '^GSPC'),
    ('TSEC',    '^TWII'),
    ('NIKKEI',  '^N225'),
    ('HSI',     '^HSI'),
    ('STOXX',   '^STOXX50E'),
]

LOOKBACK_DAYS = 21  # 거래일


def fetch_1m_return(ticker: str) -> float | None:
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


def main():
    returns = {}
    for name, ticker in INDICES:
        print(f'  {name} ({ticker}) ...', end=' ')
        try:
            r = fetch_1m_return(ticker)
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


if __name__ == '__main__':
    main()
