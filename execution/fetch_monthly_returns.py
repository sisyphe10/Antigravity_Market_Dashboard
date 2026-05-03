"""yfinance에서 11개 지수의 일간 종가 가져와서 월별 수익률 계산 → monthly_returns.json

지수 (X축 표시 순서):
  KOSPI, KOSDAQ, NIKKEI, TAIEX, S&P 500, NASDAQ, RUSSELL 2000, BTC, ETH, GOLD, SILVER

수익률 정의:
  완료된 달 = (해당 달 마지막 종가 / 직전 달 마지막 종가) - 1
  진행 중인 달 (MTD) = (가장 최근 종가 / 직전 달 마지막 종가) - 1

기간: 2025-01부터 현재까지 (2024-12 종가 = 2025-01 수익률의 베이스)
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

import pandas as pd
import yfinance as yf

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_JSON = os.path.join(ROOT, 'monthly_returns.json')

KST = timezone(timedelta(hours=9))

# X축 순서대로 (display_name, yfinance_ticker)
INDICES = [
    ('KOSPI',        '^KS11'),
    ('KOSDAQ',       '^KQ11'),
    ('NIKKEI',       '^N225'),
    ('TAIEX',        '^TWII'),
    ('S&P500',       '^GSPC'),
    ('NASDAQ',       '^IXIC'),
    ('RUSSELL',      '^RUT'),
    ('BTC',          'BTC-USD'),
    ('ETH',          'ETH-USD'),
    ('GOLD',         'GC=F'),
    ('SILVER',       'SI=F'),
]

START_YEAR = 2025
START_MONTH = 1


def fetch_monthly_closes(ticker: str, start: datetime, end: datetime) -> pd.Series:
    """일간 종가 → 월별 마지막 종가 Series (index=YYYY-MM 문자열, value=close)."""
    hist = yf.Ticker(ticker).history(start=start.strftime('%Y-%m-%d'),
                                     end=end.strftime('%Y-%m-%d'),
                                     auto_adjust=False)
    if hist.empty:
        return pd.Series(dtype=float)
    closes = hist['Close'].dropna()
    if closes.empty:
        return pd.Series(dtype=float)
    # 월별 마지막 종가 + 가장 최근 종가 (현재 달 MTD용)
    monthly_last = closes.groupby(closes.index.to_period('M')).last()
    monthly_last.index = monthly_last.index.astype(str)  # YYYY-MM
    return monthly_last


def main():
    today_kst = datetime.now(tz=KST).date()
    # 2025-01 수익률을 위해 2024-12 종가 필요 → 2024-11-15 부터 안전하게
    start = datetime(START_YEAR - 1, 12, 1) - timedelta(days=20)
    end = datetime.combine(today_kst + timedelta(days=1), datetime.min.time())

    print(f'기간: {start.date()} ~ {today_kst}')

    monthly_data = {}  # name → { 'YYYY-MM': close }
    for name, ticker in INDICES:
        print(f'  {name} ({ticker}) ...', end=' ')
        try:
            series = fetch_monthly_closes(ticker, start, end)
            if series.empty:
                print('데이터 없음')
                monthly_data[name] = {}
                continue
            monthly_data[name] = series.to_dict()
            print(f'{len(series)}개월')
        except Exception as e:
            print(f'에러: {e}')
            monthly_data[name] = {}

    # 표시할 (year, month) 리스트: 2025-01 ~ 현재 달 (오름차순)
    rows = []
    cur_y, cur_m = START_YEAR, START_MONTH
    while (cur_y, cur_m) <= (today_kst.year, today_kst.month):
        ym = f'{cur_y:04d}-{cur_m:02d}'
        prev_y = cur_y if cur_m > 1 else cur_y - 1
        prev_m = cur_m - 1 if cur_m > 1 else 12
        prev_ym = f'{prev_y:04d}-{prev_m:02d}'

        is_mtd = (cur_y == today_kst.year and cur_m == today_kst.month)
        returns = {}
        for name, _ in INDICES:
            series = monthly_data.get(name, {})
            cur_close = series.get(ym)
            prev_close = series.get(prev_ym)
            if cur_close is None or prev_close is None or prev_close == 0:
                returns[name] = None
            else:
                returns[name] = round((cur_close / prev_close) - 1, 6)

        rows.append({
            'year': cur_y,
            'month': cur_m,
            'is_mtd': is_mtd,
            'returns': returns,
        })

        # 다음 달로
        if cur_m == 12:
            cur_y += 1
            cur_m = 1
        else:
            cur_m += 1

    out = {
        'indices': [name for name, _ in INDICES],
        'rows': rows,
        'updated_at': datetime.now(tz=KST).strftime('%Y-%m-%d %H:%M:%S KST'),
    }
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'\n✅ {OUTPUT_JSON} 저장 ({len(rows)}개월 × {len(INDICES)}개 지수)')


if __name__ == '__main__':
    main()
