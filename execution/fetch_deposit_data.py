"""
네이버 금융에서 고객예탁금 + 신용잔고 수집 → dataset.csv 적재
"""
import sys
import os
import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

DATASET = 'dataset.csv'
DATA_TYPE = 'DEPOSIT'
HEADERS = {'User-Agent': 'Mozilla/5.0'}


def fetch_deposit_data(pages=3):
    """네이버 금융에서 고객예탁금/신용잔고 수집"""
    df = pd.read_csv(DATASET)
    existing_dates = {}
    for product in ['고객예탁금', '신용잔고']:
        existing_dates[product] = set(df[df['제품명'] == product]['날짜'].values)

    new_rows = []
    for page in range(1, pages + 1):
        url = f'https://finance.naver.com/sise/sise_deposit.naver?page={page}'
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')

        table = soup.select('table')[0]
        for row in table.select('tr'):
            cells = row.select('td')
            if len(cells) < 5:
                continue

            date_text = cells[0].get_text(strip=True)
            if not date_text or '.' not in date_text:
                continue

            try:
                parts = date_text.split('.')
                year = 2000 + int(parts[0])
                date_str = f'{year}-{int(parts[1]):02d}-{int(parts[2]):02d}'
            except:
                continue

            try:
                deposit = int(cells[1].get_text(strip=True).replace(',', ''))
                credit = int(cells[3].get_text(strip=True).replace(',', ''))
            except:
                continue

            for product, value in [('고객예탁금', deposit), ('신용잔고', credit)]:
                if date_str not in existing_dates[product]:
                    new_rows.append({'날짜': date_str, '제품명': product, '가격': value, '데이터 타입': DATA_TYPE})
                    existing_dates[product].add(date_str)

    if new_rows:
        combined = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
        combined.to_csv(DATASET, index=False)
        print(f'고객예탁금/신용잔고: {len(new_rows)}행 추가')
    else:
        print('고객예탁금/신용잔고: 새 데이터 없음')


if __name__ == '__main__':
    fetch_deposit_data()
