"""11개 지수의 일간 종가 가져와서 월별 수익률 계산 → monthly_returns.json

지수 (X축 표시 순서):
  KOSPI, KOSDAQ, NIKKEI, TAIEX, S&P 500, NASDAQ, RUSSELL 2000, BTC, ETH, GOLD, SILVER

소스:
  KOSPI/KOSDAQ = Wrap_NAV.xlsx '기준가' 시트(KIS 확정지수). 해외 9개 지수 = yfinance.
  (야후의 한국지수 ^KS11/^KQ11는 지연·부정확 — 2026-06-23 KOSPI -9.99% 폭락이 익일까지
   야후 미반영되어 WRAP 탭 월별수익률[기준가 시트 기반]과 어긋났던 버그 수정.
   기준가 시트를 못 읽으면 야후로 graceful 폴백.)

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
NAV_FILE = os.path.join(ROOT, 'Wrap_NAV.xlsx')
NAV_SHEET = '기준가'
# display_name → 기준가 시트 컬럼명 (KIS 확정지수, 야후 대신 사용). 실패 시 야후 폴백.
NAV_INDICES = {'KOSPI': 'KOSPI', 'KOSDAQ': 'KOSDAQ'}

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


def fetch_monthly_closes_from_nav(col: str) -> pd.Series:
    """Wrap_NAV.xlsx '기준가' 시트(KIS 확정지수)에서 월별 마지막 종가 Series.

    index=YYYY-MM 문자열, value=close. 야후 경로와 동일한 월말-resample 규칙.
    파일/시트/컬럼 부재 또는 빈 컬럼이면 ValueError → 호출부에서 야후로 폴백.
    """
    df = pd.read_excel(NAV_FILE, sheet_name=NAV_SHEET)
    df.columns = [str(c).strip() for c in df.columns]  # 컬럼명 방어(공백/BOM)
    if 'Date' not in df.columns or col not in df.columns:
        raise ValueError(f"기준가 시트 컬럼 없음: Date/{col}")
    df['Date'] = pd.to_datetime(df['Date'])
    s = df.set_index('Date')[col].dropna().sort_index()
    if isinstance(s.index, pd.DatetimeIndex) and s.index.tz is not None:
        s.index = s.index.tz_localize(None)
    if s.empty:
        raise ValueError(f"기준가 {col} 비어있음")
    monthly_last = s.groupby(s.index.to_period('M')).last()
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
            if name in NAV_INDICES:
                # KOSPI/KOSDAQ: 기준가 시트(KIS 확정지수) 우선, 실패 시 야후 폴백
                try:
                    series = fetch_monthly_closes_from_nav(NAV_INDICES[name])
                    print('[기준가/KIS]', end=' ')
                except Exception as ne:
                    print(f'[기준가 실패→야후 폴백: {ne}]', end=' ')
                    series = fetch_monthly_closes(ticker, start, end)
            else:
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

    # 현재 연도 YTD: (현재 연도 가장 최근 월 종가 / 작년 12월 종가) - 1
    current_year = today_kst.year
    base_ym = f'{current_year - 1:04d}-12'
    ytd_returns = {}
    for name, _ in INDICES:
        series = monthly_data.get(name, {})
        base_close = series.get(base_ym)
        current_yms = sorted([ym for ym in series.keys() if ym.startswith(f'{current_year:04d}-')])
        latest_close = series.get(current_yms[-1]) if current_yms else None
        if base_close is None or latest_close is None or base_close == 0:
            ytd_returns[name] = None
        else:
            ytd_returns[name] = round((latest_close / base_close) - 1, 6)

    out = {
        'indices': [name for name, _ in INDICES],
        'rows': rows,
        'ytd': {
            'year': current_year,
            'returns': ytd_returns,
        },
        'updated_at': datetime.now(tz=KST).strftime('%Y-%m-%d %H:%M:%S KST'),
    }
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'\n✅ {OUTPUT_JSON} 저장 ({len(rows)}개월 × {len(INDICES)}개 지수)')


if __name__ == '__main__':
    main()
