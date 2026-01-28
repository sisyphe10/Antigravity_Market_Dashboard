
import yfinance as yf
import csv
import os
from datetime import datetime, timedelta

CSV_FILE = 'dataset.csv'

# yfinance 티커 목록 (market_crawler.py와 동일)
YFINANCE_TICKERS = {
    # --- 암호화폐 ---
    'Bitcoin': {'ticker': 'BTC-USD', 'type': 'CRYPTO'},
    'Ethereum': {'ticker': 'ETH-USD', 'type': 'CRYPTO'},
    'Binance Coin': {'ticker': 'BNB-USD', 'type': 'CRYPTO'},
    'Ripple': {'ticker': 'XRP-USD', 'type': 'CRYPTO'},
    'Solana': {'ticker': 'SOL-USD', 'type': 'CRYPTO'},

    # --- 원자재 ---
    'WTI Crude Oil': {'ticker': 'CL=F', 'type': 'COMMODITY'},
    'Brent Crude Oil': {'ticker': 'BZ=F', 'type': 'COMMODITY'},
    'Natural Gas': {'ticker': 'NG=F', 'type': 'COMMODITY'},
    'Gold': {'ticker': 'GC=F', 'type': 'COMMODITY'},
    'Silver': {'ticker': 'SI=F', 'type': 'COMMODITY'},
    'Copper': {'ticker': 'HG=F', 'type': 'COMMODITY'},
    'Uranium ETF (URA)': {'ticker': 'URA', 'type': 'COMMODITY'},
    'Wheat Futures': {'ticker': 'ZW=F', 'type': 'COMMODITY'},

    # --- 지수 및 금리 ---
    'VIX Index': {'ticker': '^VIX', 'type': 'INDEX_US'},
    'US 10 Year Treasury Yield': {'ticker': '^TNX', 'type': 'INTEREST_RATE'},

    # --- 환율 (FX) ---
    'Dollar Index (DXY)': {'ticker': 'DX-Y.NYB', 'type': 'FX'},
    'KRW/USD': {'ticker': 'KRW=X', 'type': 'FX'},
    'JPY/USD': {'ticker': 'JPY=X', 'type': 'FX'},
    'CNY/USD': {'ticker': 'CNY=X', 'type': 'FX'},
    'TWD/USD': {'ticker': 'TWD=X', 'type': 'FX'},
    'EUR/USD': {'ticker': 'EUR=X', 'type': 'FX'},
}

# US Indices (market_crawler.py의 crawl_us_indices와 동일)
US_INDICES = {
    "S&P 500": {"idx": "^GSPC", "etf": "SPY"},
    "NASDAQ": {"idx": "^IXIC", "etf": "QQQ"},
    "RUSSELL 2000": {"idx": "^RUT", "etf": "IWM"}
}

def get_existing_data():
    """기존 데이터를 읽어서 (날짜, 제품명) 키 세트 반환"""
    existing_keys = set()
    if os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                for row in reader:
                    if len(row) >= 2:
                        existing_keys.add((row[0], row[1]))
        except:
            pass
    return existing_keys

def save_to_csv(data):
    """중복 방지하며 CSV에 저장"""
    if not data:
        return
    
    try:
        with open(CSV_FILE, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerows(data)
        print(f"  Saved {len(data)} rows")
    except Exception as e:
        print(f"  Error saving: {e}")

def collect_historical_yfinance():
    """yfinance 항목들의 6개월 과거 데이터 수집"""
    print("=" * 60)
    print("Collecting 6 months of historical data from yfinance")
    print("=" * 60)
    
    # 6개월 전부터 오늘까지
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)
    
    print(f"\nDate range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    existing_keys = get_existing_data()
    total_new_rows = 0
    
    # 1. YFINANCE_TICKERS 항목들
    print(f"\n[1/2] Processing {len(YFINANCE_TICKERS)} yfinance tickers...")
    for name, info in YFINANCE_TICKERS.items():
        print(f"\n  {name} ({info['ticker']})...")
        try:
            ticker = yf.Ticker(info['ticker'])
            hist = ticker.history(start=start_date, end=end_date)
            
            if hist.empty:
                print(f"    No data available")
                continue
            
            new_data = []
            for date, row in hist.iterrows():
                date_str = date.strftime('%Y-%m-%d')
                key = (date_str, name)
                
                if key not in existing_keys:
                    price = float(row['Close'])
                    new_data.append([date_str, name, price, info['type']])
            
            if new_data:
                save_to_csv(new_data)
                total_new_rows += len(new_data)
                print(f"    Added {len(new_data)} new rows")
            else:
                print(f"    All data already exists")
                
        except Exception as e:
            print(f"    Error: {e}")
    
    # 2. US Indices (지수 + PER/PBR)
    print(f"\n[2/2] Processing {len(US_INDICES)} US indices...")
    for name, tickers in US_INDICES.items():
        print(f"\n  {name}...")
        try:
            # 지수 가격
            idx_ticker = yf.Ticker(tickers['idx'])
            hist = idx_ticker.history(start=start_date, end=end_date)
            
            if not hist.empty:
                new_data = []
                for date, row in hist.iterrows():
                    date_str = date.strftime('%Y-%m-%d')
                    key = (date_str, name)
                    
                    if key not in existing_keys:
                        price = float(row['Close'])
                        new_data.append([date_str, name, price, 'INDEX_US'])
                
                if new_data:
                    save_to_csv(new_data)
                    total_new_rows += len(new_data)
                    print(f"    Added {len(new_data)} index price rows")
            
            # PER/PBR (ETF 기반 - 최근 값만 가능)
            # 참고: yfinance는 과거 PER/PBR을 제공하지 않으므로 현재 값만 수집
            etf_ticker = yf.Ticker(tickers['etf'])
            info = etf_ticker.info
            today_str = end_date.strftime('%Y-%m-%d')
            
            fundamental_data = []
            if 'trailingPE' in info and info['trailingPE']:
                key = (today_str, f"{name} PER")
                if key not in existing_keys:
                    fundamental_data.append([today_str, f"{name} PER", info['trailingPE'], 'INDEX_US'])
            
            if 'priceToBook' in info and info['priceToBook']:
                key = (today_str, f"{name} PBR")
                if key not in existing_keys:
                    fundamental_data.append([today_str, f"{name} PBR", info['priceToBook'], 'INDEX_US'])
            
            if fundamental_data:
                save_to_csv(fundamental_data)
                total_new_rows += len(fundamental_data)
                print(f"    Added {len(fundamental_data)} fundamental rows")
                
        except Exception as e:
            print(f"    Error: {e}")
    
    print("\n" + "=" * 60)
    print(f"COMPLETE: Added {total_new_rows} new rows to {CSV_FILE}")
    print("=" * 60)

if __name__ == "__main__":
    collect_historical_yfinance()
