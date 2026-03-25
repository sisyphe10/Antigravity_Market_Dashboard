"""
KRX OpenAPI 데이터 수집 → dataset.csv 적재
차트는 draw_charts.py가 dataset.csv를 읽어서 자동 생성합니다.
"""
import os
import requests
import pandas as pd
from datetime import datetime, timedelta

API_KEY = 'E9E8B0A915D74BC59CFA41D5534CF19EF4B24C9E'
DATASET_FILE = 'dataset.csv'


def fetch_api(url, date_str):
    try:
        r = requests.get(url, params={'AUTH_KEY': API_KEY, 'basDd': date_str}, timeout=10)
        return r.json().get('OutBlock_1', [])
    except:
        return []


def collect_product(df, product_name, data_type, fetch_fn, lookback_days=180):
    """특정 상품 데이터를 수집"""
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


if __name__ == '__main__':
    df = pd.read_csv(DATASET_FILE, encoding='utf-8-sig')

    print("KRX 데이터 수집 중...")
    all_new = []
    all_new += collect_product(df, 'KRX GOLD Trading Volume', 'COMMODITY', fetch_gold_volume)
    all_new += collect_product(df, 'KRX ETS (KAU25)', 'COMMODITY', fetch_ets_kau25_price)
    all_new += collect_product(df, 'KRX ETS Trading Volume', 'COMMODITY', fetch_ets_volume)

    if all_new:
        new_df = pd.DataFrame(all_new)
        df = pd.concat([df, new_df], ignore_index=True)
        df['날짜'] = pd.to_datetime(df['날짜'])
        df = df.drop_duplicates(subset=['날짜', '제품명'], keep='last')
        df = df.sort_values('날짜')
        df['날짜'] = df['날짜'].dt.strftime('%Y-%m-%d')
        df.to_csv(DATASET_FILE, index=False, encoding='utf-8-sig')

    print("완료!")
