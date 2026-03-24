"""
KRX 금 거래대금 데이터 수집 → CSV 저장 → 차트 생성
매일 실행하여 데이터를 누적합니다.
"""
import os
import sys
import requests
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter, MaxNLocator
from datetime import datetime, timedelta

API_KEY = 'E9E8B0A915D74BC59CFA41D5534CF19EF4B24C9E'
API_URL = 'http://data-dbg.krx.co.kr/svc/apis/gen/gold_bydd_trd'
DATASET_FILE = 'dataset.csv'
CHART_FILE = 'charts/KRX_GOLD_Trading_Volume.png'
PRODUCT_NAME = 'KRX GOLD Trading Volume'
LINE_COLOR = '#404040'


def fetch_gold_data(date_str):
    """KRX API에서 특정 날짜의 금 거래대금 조회"""
    try:
        r = requests.get(API_URL, params={'AUTH_KEY': API_KEY, 'basDd': date_str}, timeout=10)
        data = r.json()
        items = data.get('OutBlock_1', [])
        total_val = 0
        for item in items:
            val = int(item.get('ACC_TRDVAL', '0') or '0')
            total_val += val
        return total_val
    except:
        return None


def collect_data():
    """신규 데이터 수집하여 dataset.csv에 추가"""
    df = pd.read_csv(DATASET_FILE, encoding='utf-8-sig')
    df['날짜'] = pd.to_datetime(df['날짜'])

    # 기존 금 데이터에서 마지막 날짜 확인
    gold_df = df[df['제품명'] == PRODUCT_NAME]
    if not gold_df.empty:
        last_date = gold_df['날짜'].max()
    else:
        last_date = datetime.now() - timedelta(days=180)

    today = datetime.now()
    start = last_date + timedelta(days=1)

    new_rows = []
    current = start
    while current <= today:
        if current.weekday() < 5:
            date_str = current.strftime('%Y%m%d')
            val = fetch_gold_data(date_str)
            if val is not None and val > 0:
                new_rows.append({
                    '날짜': current.strftime('%Y-%m-%d'),
                    '제품명': PRODUCT_NAME,
                    '가격': val,
                    '데이터 타입': 'Commodities'
                })
                print(f"  {date_str}: {val:,.0f}원")
        current += timedelta(days=1)

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        df = pd.concat([df, new_df], ignore_index=True)
        df['날짜'] = pd.to_datetime(df['날짜'])
        df = df.drop_duplicates(subset=['날짜', '제품명'], keep='last')
        df = df.sort_values('날짜')
        df['날짜'] = df['날짜'].dt.strftime('%Y-%m-%d')
        df.to_csv(DATASET_FILE, index=False, encoding='utf-8-sig')
        print(f"  {len(new_rows)}일치 추가")
    else:
        print("  신규 데이터 없음")

    # 금 데이터만 반환 (차트용)
    result = df[df['제품명'] == PRODUCT_NAME].copy()
    result['날짜'] = pd.to_datetime(result['날짜'])
    result['거래대금'] = pd.to_numeric(result['가격'], errors='coerce')
    return result


def smart_format_yaxis(y, pos):
    """Y축 포맷: 억원 단위"""
    if y >= 1e12:
        return f'{y/1e12:.1f}조'
    elif y >= 1e8:
        return f'{y/1e8:.0f}억'
    elif y >= 1e4:
        return f'{y/1e4:.0f}만'
    return f'{y:,.0f}'


def draw_chart(df):
    """금 거래대금 바 차트 생성"""
    if df.empty:
        print("  데이터 없음, 차트 생성 스킵")
        return

    df['날짜'] = pd.to_datetime(df['날짜'])
    df = df.sort_values('날짜')

    # 최근 6개월
    latest_date = df['날짜'].max()
    start_date = latest_date - timedelta(days=180)
    filtered = df[df['날짜'] >= start_date].copy()

    if filtered.empty:
        return

    latest_val = filtered.iloc[-1]['거래대금']

    # WoW 계산
    target_date = latest_date - timedelta(days=7)
    past = filtered[filtered['날짜'] <= target_date]
    wow_label = ""
    if not past.empty:
        past_val = past.iloc[-1]['거래대금']
        if past_val > 0:
            change = (latest_val / past_val - 1) * 100
            sign = "+" if change > 0 else ""
            wow_label = f" ({sign}{change:.1f}%)"

    # 차트 그리기
    fig, ax = plt.subplots(figsize=(10, 6))

    # 바 차트 (거래대금)
    bar_colors = [LINE_COLOR if v < latest_val else '#cc0000' for v in filtered['거래대금']]
    ax.bar(filtered['날짜'], filtered['거래대금'], color=LINE_COLOR, width=1.5, alpha=0.8)

    # 제목
    val_str = smart_format_yaxis(latest_val, None)
    title_text = f"KRX GOLD Trading Volume | {val_str}{wow_label}"
    ax.set_title(title_text, fontsize=14, color='black', pad=10)

    ax.set_xlabel("")
    ax.set_ylabel("")

    # X축
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%y/%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha='center')

    # Y축
    ax.yaxis.set_major_locator(MaxNLocator(nbins=8, prune='both'))
    ax.yaxis.set_major_formatter(FuncFormatter(smart_format_yaxis))
    ax.margins(y=0.02)

    ax.grid(True, linestyle='--', alpha=0.5)

    os.makedirs('charts', exist_ok=True)
    fig.savefig(CHART_FILE, dpi=100, bbox_inches='tight')
    plt.close(fig)
    print(f"  차트 저장: {CHART_FILE}")


if __name__ == '__main__':
    print("1. KRX 금 거래대금 수집 중...")
    df = collect_data()
    print("2. 차트 생성 중...")
    draw_chart(df)
    print("완료!")
