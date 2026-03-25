"""
SEIBro 해외증권 결제 TOP 50 종목 데이터 수집
- 일자별 미국 매수결제 TOP 50 종목 + 금액 수집
- dataset.csv에 적재 (데이터 타입: SEIBro)
"""
import sys
import os
import time
import logging
import pandas as pd
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

SEIBRO_URL = 'https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/ovsSec/BIP_CNTS10013V.xml&menuNo=92'
DATASET_CSV = 'dataset.csv'
DATA_TYPE = 'SEIBro'
PAGE_LOAD_WAIT = 8
SEARCH_WAIT = 8


def get_driver():
    opts = Options()
    opts.add_argument('--headless')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--window-size=1920,1080')
    return webdriver.Chrome(options=opts)


def get_existing_dates(csv_path):
    """이미 수집된 SEIBro 날짜 목록"""
    if not os.path.exists(csv_path):
        return set()
    df = pd.read_csv(csv_path)
    seibro = df[df['데이터 타입'] == DATA_TYPE]
    return set(seibro['날짜'].unique())


def get_trading_days(start_date, end_date):
    """주말 제외한 날짜 리스트"""
    days = []
    d = start_date
    while d <= end_date:
        if d.weekday() < 5:  # Mon-Fri
            days.append(d)
        d += timedelta(days=1)
    return days


def fetch_day(driver, date_str):
    """하루치 TOP 50 데이터 수집. date_str: 'YYYYMMDD' """
    driver.execute_script(f"""
        sd1_inputCalendar1.setValue('{date_str}');
        sd1_inputCalendar2.setValue('{date_str}');
    """)
    time.sleep(0.5)

    driver.find_element(By.ID, 'group186').click()
    time.sleep(SEARCH_WAIT)

    try:
        driver.switch_to.alert.accept()
        return []  # alert = no data for this date
    except:
        pass

    rows = []
    for row_idx in range(50):
        rank = ''
        try:
            rank = driver.find_element(By.ID, f'grid2_cell_{row_idx}_0').text.strip()
        except:
            pass
        if not rank:
            break

        name = driver.find_element(By.ID, f'grid2_cell_{row_idx}_3').text.strip()
        amount_str = driver.find_element(By.ID, f'grid2_cell_{row_idx}_4').text.strip()

        # 금액 파싱 (콤마 제거)
        try:
            amount = int(amount_str.replace(',', ''))
        except:
            amount = 0

        if name and amount > 0:
            rows.append({
                '날짜': f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}',
                '제품명': name,
                '가격': amount,
                '데이터 타입': DATA_TYPE,
            })

    return rows


def main():
    # 날짜 범위 결정
    today = datetime.now().date()
    start_of_year = datetime(today.year, 1, 1).date()

    # 기존 데이터 확인
    existing_dates = get_existing_dates(DATASET_CSV)
    trading_days = get_trading_days(start_of_year, today)

    # 수집 필요한 날짜만 필터
    dates_to_fetch = [
        d for d in trading_days
        if d.strftime('%Y-%m-%d') not in existing_dates
    ]

    if not dates_to_fetch:
        logging.info("모든 날짜가 이미 수집됨. 완료.")
        return

    logging.info(f"수집 대상: {len(dates_to_fetch)}일 ({dates_to_fetch[0]} ~ {dates_to_fetch[-1]})")

    driver = get_driver()
    all_rows = []

    try:
        # 페이지 로드 (1회)
        logging.info("SEIBro 페이지 로드 중...")
        driver.get(SEIBRO_URL)
        time.sleep(PAGE_LOAD_WAIT)
        try:
            driver.switch_to.alert.accept()
        except:
            pass

        for i, d in enumerate(dates_to_fetch):
            date_str = d.strftime('%Y%m%d')
            logging.info(f"[{i+1}/{len(dates_to_fetch)}] {d} 수집 중...")

            rows = fetch_day(driver, date_str)
            if rows:
                all_rows.extend(rows)
                logging.info(f"  → {len(rows)}개 종목 수집")
            else:
                logging.info(f"  → 데이터 없음 (휴일/공휴일)")

    finally:
        driver.quit()

    if not all_rows:
        logging.info("수집된 데이터 없음.")
        return

    # dataset.csv에 추가
    new_df = pd.DataFrame(all_rows)
    if os.path.exists(DATASET_CSV):
        existing_df = pd.read_csv(DATASET_CSV)
        combined = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        combined = new_df

    combined.to_csv(DATASET_CSV, index=False)
    logging.info(f"완료! {len(all_rows)}개 행 추가 (총 {len(combined)}행)")


if __name__ == '__main__':
    main()
