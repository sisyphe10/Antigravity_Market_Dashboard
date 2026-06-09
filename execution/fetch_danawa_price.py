"""
다나와(prod.danawa.com) 제품 최저가 수집 → dataset.csv 적재.

하루 1회 실행. 같은 (날짜, 제품명) 은 건너뛰어 중복 방지.
PRODUCTS 에 pcode 를 추가하면 여러 제품을 동시에 추적할 수 있다.
"""
import sys
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests

sys.stdout.reconfigure(encoding='utf-8')

DATASET = 'dataset.csv'
DATA_TYPE = 'DRAM_RETAIL'   # CATEGORY_MAP → 'Memory'
KST = ZoneInfo('Asia/Seoul')

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
    )
}

# pcode → dataset.csv 의 제품명(차트 시리즈 csv 키와 일치해야 함)
PRODUCTS = {
    '18911780': '삼성 DDR5 소매가',     # 삼성전자 DDR5-5600 (16GB)
    '18883523': 'SK하이닉스 DDR5 소매가',  # SK하이닉스 DDR5-5600 (16GB)
}

# 최저가 추출 패턴 (우선순위 순). intMinFee 숨김 필드가 가장 안정적.
PATTERNS = [
    r'id="intMinFee"\s+value="([\d,]+)"',
    r'최저가\s*([\d,]+)\s*원',
    r'class="text__num">([\d,]+)</span>',
]


def fetch_lowest_price(pcode):
    url = f'https://prod.danawa.com/info/?pcode={pcode}'
    html = requests.get(url, headers=HEADERS, timeout=15).text
    for pat in PATTERNS:
        m = re.search(pat, html)
        if m:
            return int(m.group(1).replace(',', ''))
    return None


def fetch_danawa_prices():
    df = pd.read_csv(DATASET)
    today = datetime.now(KST).strftime('%Y-%m-%d')

    existing = {}
    for name in PRODUCTS.values():
        existing[name] = set(df[df['제품명'] == name]['날짜'].values)

    new_rows = []
    for pcode, name in PRODUCTS.items():
        if today in existing[name]:
            print(f'{name}: {today} 이미 기록됨 (skip)')
            continue
        try:
            price = fetch_lowest_price(pcode)
        except Exception as e:
            print(f'{name}: 수집 오류 - {e}', file=sys.stderr)
            continue
        if price is None:
            print(f'{name}: 최저가 파싱 실패 (skip)', file=sys.stderr)
            continue
        new_rows.append({'날짜': today, '제품명': name, '가격': price, '데이터 타입': DATA_TYPE})
        print(f'{name}: {price:,}원')

    if new_rows:
        combined = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
        combined.to_csv(DATASET, index=False)
        print(f'다나와 최저가: {len(new_rows)}행 추가')
    else:
        print('다나와 최저가: 새 데이터 없음')


if __name__ == '__main__':
    fetch_danawa_prices()
