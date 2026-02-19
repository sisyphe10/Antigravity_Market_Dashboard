
import time
import schedule
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import os
import csv
import yfinance as yf
import warnings

import pandas as pd

# Import shared configuration
from config import CATEGORY_MAP, YFINANCE_TICKERS, TARGET_DRAM_ITEMS, TARGET_NAND_ITEMS, CSV_FILE

# 경고 메시지 무시
warnings.simplefilter(action='ignore', category=FutureWarning)

# === 유틸리티 함수 ===
def setup_csv():
    """CSV 파일 초기 설정"""
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['날짜', '제품명', '가격', '데이터 타입'])
        print(f"✅ CSV 파일 생성 완료: {CSV_FILE}")
    else:
        print(f"✅ 기존 CSV 파일 사용: {CSV_FILE}")

def setup_driver(headless=True):
    """Selenium 웹드라이버 설정"""
    chrome_options = Options()
    if headless:
        chrome_options.add_argument('--headless')

    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def save_to_csv(data):
    """중복 방지 기능이 강화된 CSV 저장 (배치 내 중복까지 제거)"""
    try:
        existing_keys = set()
        if os.path.exists(CSV_FILE):
            with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    if len(row) >= 2:
                        key = (row[0], row[1])
                        existing_keys.add(key)

        new_data = []
        current_batch_keys = set()

        for row in data:
            current_key = (row[0], row[1])
            if current_key not in existing_keys and current_key not in current_batch_keys:
                new_data.append(row)
                current_batch_keys.add(current_key)

        if new_data:
            with open(CSV_FILE, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerows(new_data)
            print(f"✅ {len(new_data)}건 저장 완료 (중복 제외됨)")
            return True
        else:
            print("💡 새로운 데이터가 없습니다. (모두 중복)")
            return True

    except Exception as e:
        print(f"\n❌ 저장 중 오류: {str(e)}")
        return False

def get_last_scfi_date():
    try:
        if not os.path.exists(CSV_FILE): return None
        last_date = None
        with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) >= 4 and row[3] == 'OCEAN_FREIGHT' and 'SCFI' in row[1]:
                    last_date = row[0]
        return last_date
    except:
        return None

# ==========================================
# 2. [US] 미국 지수/PER/PBR (yfinance)
# ==========================================
def crawl_us_indices():
    """미국 지수 및 PER/PBR 수집"""
    print(f"\n{'=' * 60}")
    print(f"🇺🇸 미국 지수/PER/PBR 크롤링 시작 (yfinance)")
    print(f"{'=' * 60}")

    collected_data = []

    targets = {
        "S&P 500": {"idx": "^GSPC", "etf": "SPY"},
        "NASDAQ": {"idx": "^IXIC", "etf": "QQQ"},
        "RUSSELL 2000": {"idx": "^RUT", "etf": "IWM"}
    }

    for name, tickers in targets.items():
        try:
            # 1. 지수 가격
            idx_ticker = yf.Ticker(tickers['idx'])
            hist = idx_ticker.history(period="1d")

            if not hist.empty:
                price = float(hist['Close'].iloc[0])
                d_date = hist.index[0].strftime('%Y-%m-%d')
                collected_data.append((d_date, name, price, 'INDEX_US'))
                print(f"✓ {name}: {price:,.2f}")

                # 2. 펀더멘탈 (ETF 사용)
                etf_ticker = yf.Ticker(tickers['etf'])
                info = etf_ticker.info

                if 'trailingPE' in info and info['trailingPE']:
                    pe = info['trailingPE']
                    collected_data.append((d_date, f"{name} PER", pe, 'INDEX_US'))

                if 'priceToBook' in info and info['priceToBook']:
                    pbr = info['priceToBook']
                    collected_data.append((d_date, f"{name} PBR", pbr, 'INDEX_US'))

        except Exception as e:
            print(f"❌ {name} 오류: {e}")

    if collected_data:
        save_to_csv(collected_data)

# ==========================================
# 3. [DRAM/NAND] 반도체 가격
# ==========================================
def crawl_dram_nand(data_type):
    """DRAM 및 NAND 가격 크롤링"""
    print(f"\n📊 {data_type} 크롤링 시작")
    driver = None
    try:
        driver = setup_driver()
        driver.get(f'https://www.dramexchange.com/#{data_type.lower()}')
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'table')))

        if not driver: return

        current_date = datetime.now().strftime('%Y-%m-%d')
        collected_data = []
        target_items = TARGET_DRAM_ITEMS if data_type == 'DRAM' else TARGET_NAND_ITEMS
        found_items = set()

        tables = driver.find_elements(By.TAG_NAME, 'table')
        for table in tables:
            # 1. 헤더에서 'Average' 컬럼 인덱스 찾기
            price_col_idx = 1  # 기본값: 2번째 컬럼 (인덱스 1)
            try:
                header_rows = table.find_elements(By.TAG_NAME, 'tr')
                if header_rows:
                    headers = header_rows[0].find_elements(By.TAG_NAME, 'th')
                    if not headers:
                        headers = header_rows[0].find_elements(By.TAG_NAME, 'td')
                    
                    for i, th in enumerate(headers):
                        header_text = th.text.strip().lower()
                        if 'average' in header_text or 'avg' in header_text:
                            price_col_idx = i
                            print(f"  Target column found: '{th.text}' (Index {i})")
                            break
            except Exception as e:
                print(f"  Header parsing warning: {e}")

            # 2. 데이터 행 파싱
            rows = table.find_elements(By.TAG_NAME, 'tr')
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, 'td')
                if not cells: cells = row.find_elements(By.TAG_NAME, 'th')
                
                # 최소한 target 인덱스보다는 길어야 함
                if len(cells) <= price_col_idx: continue

                item_name = cells[0].text.strip()
                if item_name in target_items and item_name not in found_items:
                    try:
                        # 찾은 인덱스의 가격 사용
                        price = cells[price_col_idx].text.strip()
                        if price and price.replace('.', '').replace(',', '').isdigit():
                            val = float(price.replace(',', ''))
                            collected_data.append((current_date, item_name, val, data_type))
                            found_items.add(item_name)
                            print(f"✓ {item_name}: ${price}")
                    except:
                        pass

        if collected_data:
            save_to_csv(collected_data)
        else:
            print(f"⚠️ {data_type} 데이터 없음")

    except Exception as e:
        print(f"❌ {data_type} 오류: {e}")
    finally:
        if driver: driver.quit()

# ==========================================
# 4. [SCFI] 해상운임지수
# ==========================================
def crawl_scfi_index():
    print(f"\n🚢 SCFI 크롤링 시작")
    driver = None
    try:
        driver = setup_driver()
        driver.get('https://en.sse.net.cn/indices/scfinew.jsp')
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'currdate')))

        scfi_date = driver.find_element(By.ID, 'currdate').text.strip()
        scfi_value = None

        tables = driver.find_elements(By.TAG_NAME, 'table')
        for table in tables:
            if 'Comprehensive Index' in table.text:
                rows = table.find_elements(By.TAG_NAME, 'tr')
                for row in rows:
                    if 'Comprehensive Index' in row.text:
                        idx4 = row.find_elements(By.CSS_SELECTOR, 'span.idx4')
                        if idx4: scfi_value = idx4[0].text.strip()

        if scfi_value and scfi_date:
            if get_last_scfi_date() == scfi_date:
                print(f"💡 SCFI 최신 상태 ({scfi_date})")
            else:
                save_to_csv([(scfi_date, 'SCFI Comprehensive Index', float(scfi_value), 'OCEAN_FREIGHT')])
                print(f"✅ SCFI 저장: {scfi_value}")
    except Exception as e:
        print(f"❌ SCFI 오류: {e}")
    finally:
        if driver: driver.quit()

# ==========================================
# 5. [yfinance] 기타 자산
# ==========================================
def crawl_yfinance_data():
    print(f"\n📈 yfinance 크롤링 시작")
    current_date = datetime.now().strftime('%Y-%m-%d')
    collected_data = []
    for name, info in YFINANCE_TICKERS.items():
        try:
            t = yf.Ticker(info['ticker'])
            h = t.history(period='1d')
            if not h.empty:
                price = float(h['Close'].iloc[0])
                d = h.index[0].strftime('%Y-%m-%d') if info['type'] != 'CRYPTO' else current_date
                collected_data.append((d, name, price, info['type']))
                print(f"✓ {name}: {price:.2f}")
        except:
            print(f"⚠️ {name} 실패")

    if collected_data: save_to_csv(collected_data)

# ==========================================
# 6. [KR] 한국 지수 + USD 환산
# ==========================================
def crawl_kr_indices():
    """한국 지수(KOSPI/KOSDAQ) + USD 환산 데이터 수집"""
    print(f"\n{'=' * 60}")
    print(f"🇰🇷 한국 지수 크롤링 시작")
    print(f"{'=' * 60}")

    collected_data = []

    try:
        kospi = yf.Ticker('^KS11').history(period='6mo')
        kosdaq = yf.Ticker('^KQ11').history(period='6mo')
        krw = yf.Ticker('KRW=X').history(period='6mo')

        if kospi.empty or kosdaq.empty or krw.empty:
            print("⚠️ 한국 지수 데이터 없음")
            return

        # 타임존 제거
        kospi.index = kospi.index.tz_localize(None)
        kosdaq.index = kosdaq.index.tz_localize(None)
        krw.index = krw.index.tz_localize(None)

        # KOSPI, KOSDAQ 원본 데이터
        for date, row in kospi.iterrows():
            d = date.strftime('%Y-%m-%d')
            collected_data.append((d, 'KOSPI', float(row['Close']), 'INDEX_KR'))

        for date, row in kosdaq.iterrows():
            d = date.strftime('%Y-%m-%d')
            collected_data.append((d, 'KOSDAQ', float(row['Close']), 'INDEX_KR'))

        # USD 환산 (KOSPI/USDKRW, KOSDAQ/USDKRW)
        for date in kospi.index:
            if date in krw.index:
                d = date.strftime('%Y-%m-%d')
                fx_rate = float(krw.loc[date, 'Close'])

                kospi_usd = float(kospi.loc[date, 'Close']) / fx_rate
                collected_data.append((d, 'KOSPI/USD', round(kospi_usd, 4), 'INDEX_KR'))

                if date in kosdaq.index:
                    kosdaq_usd = float(kosdaq.loc[date, 'Close']) / fx_rate
                    collected_data.append((d, 'KOSDAQ/USD', round(kosdaq_usd, 4), 'INDEX_KR'))

        print(f"✓ KOSPI: {len(kospi)}일, KOSDAQ: {len(kosdaq)}일 수집")
        print(f"✓ KOSPI/USD, KOSDAQ/USD 환산 완료")

    except Exception as e:
        print(f"❌ 한국 지수 오류: {e}")

    if collected_data:
        save_to_csv(collected_data)

# ==========================================
# Main Execution
# ==========================================
def main():
    print("🚀 전체 크롤링 시작")
    setup_csv()

    # 순차적 실행
    crawl_dram_nand('DRAM')
    crawl_dram_nand('NAND')
    crawl_scfi_index()
    crawl_yfinance_data()

    crawl_us_indices()
    crawl_kr_indices()

    print(f"\n📁 결과 파일: {CSV_FILE}")

if __name__ == "__main__":
    main()
