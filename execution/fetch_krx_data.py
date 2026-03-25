"""
KRX OpenAPI 데이터 수집 → dataset.csv 적재 → 차트 생성
- 금 거래대금 (바 차트)
- KAU25 배출권 종가 (라인 차트)
- 배출권 거래대금 (바 차트)
"""
import os
import requests
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter, MaxNLocator
from datetime import datetime, timedelta

API_KEY = 'E9E8B0A915D74BC59CFA41D5534CF19EF4B24C9E'
DATASET_FILE = 'dataset.csv'
LINE_COLOR = '#404040'


def smart_format_yaxis(y, pos):
    if y >= 1e12:
        return f'{y/1e12:.1f}조'
    elif y >= 1e8:
        return f'{y/1e8:.0f}억'
    elif y >= 1e4:
        return f'{y/1e4:.0f}만'
    return f'{y:,.0f}'


def smart_format_price(y, pos):
    if abs(y) >= 1000:
        return f'{y:,.0f}'
    elif abs(y) >= 1:
        return f'{y:.1f}'
    return f'{y:.2f}'


def fetch_api(url, date_str):
    try:
        r = requests.get(url, params={'AUTH_KEY': API_KEY, 'basDd': date_str}, timeout=10)
        return r.json().get('OutBlock_1', [])
    except:
        return []


def collect_product(df, product_name, data_type, fetch_fn, lookback_days=180):
    """특정 상품 데이터를 수집하여 df에 추가"""
    existing = df[df['제품명'] == product_name]
    if not existing.empty:
        last_date = pd.to_datetime(existing['날짜']).max()
    else:
        last_date = datetime.now() - timedelta(days=lookback_days)

    today = datetime.now()
    current = last_date + timedelta(days=1)
    new_rows = []

    while current <= today:
        if current.weekday() < 5:
            date_str = current.strftime('%Y%m%d')
            val = fetch_fn(date_str)
            if val is not None and val > 0:
                new_rows.append({
                    '날짜': current.strftime('%Y-%m-%d'),
                    '제품명': product_name,
                    '가격': val,
                    '데이터 타입': data_type
                })
        current += timedelta(days=1)

    if new_rows:
        print(f"  {product_name}: {len(new_rows)}일치 추가")
    else:
        print(f"  {product_name}: 신규 데이터 없음")

    return new_rows


def fetch_gold_volume(date_str):
    items = fetch_api('http://data-dbg.krx.co.kr/svc/apis/gen/gold_bydd_trd', date_str)
    total = sum(int(item.get('ACC_TRDVAL', '0') or '0') for item in items)
    return total if total > 0 else None


def fetch_ets_kau25_price(date_str):
    items = fetch_api('http://data-dbg.krx.co.kr/svc/apis/gen/ets_bydd_trd', date_str)
    for item in items:
        if 'KAU25' in item.get('ISU_NM', ''):
            price = int(item.get('TDD_CLSPRC', '0') or '0')
            return price if price > 0 else None
    return None


def fetch_ets_volume(date_str):
    items = fetch_api('http://data-dbg.krx.co.kr/svc/apis/gen/ets_bydd_trd', date_str)
    total = sum(int(item.get('ACC_TRDVAL', '0') or '0') for item in items)
    return total if total > 0 else None


def draw_bar_chart(df, product_name, chart_file, title_prefix):
    """바 차트 (거래대금용)"""
    data = df[df['제품명'] == product_name].copy()
    if data.empty:
        return
    data['날짜'] = pd.to_datetime(data['날짜'])
    data['값'] = pd.to_numeric(data['가격'], errors='coerce')
    data = data.sort_values('날짜')

    latest_date = data['날짜'].max()
    filtered = data[data['날짜'] >= latest_date - timedelta(days=180)].copy()
    if filtered.empty:
        return

    latest_val = filtered.iloc[-1]['값']
    target = latest_date - timedelta(days=7)
    past = filtered[filtered['날짜'] <= target]
    wow = ""
    if not past.empty and past.iloc[-1]['값'] > 0:
        change = (latest_val / past.iloc[-1]['값'] - 1) * 100
        wow = f" ({'+' if change > 0 else ''}{change:.1f}%)"

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(filtered['날짜'], filtered['값'], color=LINE_COLOR, width=1.5, alpha=0.8)
    ax.set_title(f"{title_prefix} | {smart_format_yaxis(latest_val, None)}{wow}", fontsize=14, color='black', pad=10)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%y/%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha='center')
    ax.yaxis.set_major_locator(MaxNLocator(nbins=8, prune='both'))
    ax.yaxis.set_major_formatter(FuncFormatter(smart_format_yaxis))
    ax.margins(y=0.02)
    ax.grid(True, linestyle='--', alpha=0.5)

    os.makedirs('charts', exist_ok=True)
    fig.savefig(chart_file, dpi=100, bbox_inches='tight')
    plt.close(fig)
    print(f"  차트 저장: {chart_file}")


def draw_line_chart(df, product_name, chart_file, title_prefix):
    """라인 차트 (종가용)"""
    data = df[df['제품명'] == product_name].copy()
    if data.empty:
        return
    data['날짜'] = pd.to_datetime(data['날짜'])
    data['값'] = pd.to_numeric(data['가격'], errors='coerce')
    data = data.sort_values('날짜')

    latest_date = data['날짜'].max()
    filtered = data[data['날짜'] >= latest_date - timedelta(days=180)].copy()
    if filtered.empty:
        return

    # Forward fill
    date_range = pd.date_range(start=filtered['날짜'].min(), end=filtered['날짜'].max(), freq='D')
    filtered = filtered.set_index('날짜').reindex(date_range, method='ffill').reset_index()
    filtered.columns = ['날짜'] + list(filtered.columns[1:])

    latest_val = filtered.iloc[-1]['값']
    target = latest_date - timedelta(days=7)
    past = filtered[filtered['날짜'] <= target]
    wow = ""
    if not past.empty and past.iloc[-1]['값'] > 0:
        change = (latest_val / past.iloc[-1]['값'] - 1) * 100
        wow = f" ({'+' if change > 0 else ''}{change:.1f}%)"

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(filtered['날짜'], filtered['값'], color=LINE_COLOR)
    ax.set_title(f"{title_prefix} | {latest_val:,.0f}{wow}", fontsize=14, color='black', pad=10)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%y/%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha='center')
    ax.yaxis.set_major_locator(MaxNLocator(nbins=8, prune='both'))
    ax.yaxis.set_major_formatter(FuncFormatter(smart_format_price))
    ax.margins(y=0.02)
    ax.grid(True, linestyle='--', alpha=0.5)

    os.makedirs('charts', exist_ok=True)
    fig.savefig(chart_file, dpi=100, bbox_inches='tight')
    plt.close(fig)
    print(f"  차트 저장: {chart_file}")


if __name__ == '__main__':
    df = pd.read_csv(DATASET_FILE, encoding='utf-8-sig')

    print("1. KRX 데이터 수집 중...")
    all_new = []
    all_new += collect_product(df, 'KRX GOLD Trading Volume', 'Commodities', fetch_gold_volume)
    all_new += collect_product(df, 'KRX ETS (KAU25)', 'Commodities', fetch_ets_kau25_price)
    all_new += collect_product(df, 'KRX ETS Trading Volume', 'Commodities', fetch_ets_volume)

    if all_new:
        new_df = pd.DataFrame(all_new)
        df = pd.concat([df, new_df], ignore_index=True)
        df['날짜'] = pd.to_datetime(df['날짜'])
        df = df.drop_duplicates(subset=['날짜', '제품명'], keep='last')
        df = df.sort_values('날짜')
        df['날짜'] = df['날짜'].dt.strftime('%Y-%m-%d')
        df.to_csv(DATASET_FILE, index=False, encoding='utf-8-sig')

    print("\n2. 차트 생성 중...")
    draw_bar_chart(df, 'KRX GOLD Trading Volume', 'charts/KRX_GOLD_Trading_Volume.png', 'KRX GOLD Trading Volume')
    draw_line_chart(df, 'KRX ETS (KAU25)', 'charts/KRX_ETS_KAU25.png', 'KRX ETS (KAU25)')
    draw_bar_chart(df, 'KRX ETS Trading Volume', 'charts/KRX_ETS_Trading_Volume.png', 'KRX ETS Trading Volume')

    print("\n완료!")
