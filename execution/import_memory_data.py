
import pandas as pd
import csv
import os
from datetime import datetime

EXCEL_FILE = 'old_data.xlsx'
CSV_FILE = 'dataset.csv'
SHEET_NAME = 'memory'

# 현재 수집 중인 DRAM 항목 (market_crawler.py와 매칭)
ITEM_MAPPING = {
    'DDR4_8GB_3200': 'DDR4 8Gb (1Gx8) 3200',  # 또는 'DDR4 8Gb (512Mx16) 3200'
    'DDR4_16GB_3200': 'DDR4 16Gb (2Gx8)3200',  # 또는 'DDR4 16Gb (1Gx16)3200'
    'DDR5_16GB_4800': 'DDR5 16G (2Gx8) 4800/5600'
}

def get_existing_keys():
    """기존 dataset.csv의 (날짜, 제품명) 키 세트 반환"""
    existing_keys = set()
    if os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                for row in reader:
                    if len(row) >= 2:
                        existing_keys.add((row[0], row[1]))
        except Exception as e:
            print(f"Error reading existing data: {e}")
    return existing_keys

def import_memory_data():
    """old_data.xlsx의 memory 시트에서 데이터 가져오기"""
    print("=" * 60)
    print("Importing Memory Historical Data from Excel")
    print("=" * 60)
    
    if not os.path.exists(EXCEL_FILE):
        print(f"\nError: {EXCEL_FILE} not found!")
        return
    
    try:
        # Read Excel file
        print(f"\nReading sheet '{SHEET_NAME}' from {EXCEL_FILE}...")
        df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME)
        
        print(f"Found {len(df)} rows and {len(df.columns)} columns")
        print(f"Columns: {list(df.columns)}")
        
        # 첫 번째 열이 날짜라고 가정
        date_col = df.columns[0]
        
        # 날짜를 datetime으로 변환
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        
        # 날짜가 유효한 행만 필터링
        df = df.dropna(subset=[date_col])
        
        # 날짜를 문자열로 변환 (YYYY-MM-DD 형식)
        df[date_col] = df[date_col].dt.strftime('%Y-%m-%d')
        
        print(f"\nAfter date filtering: {len(df)} rows")
        
        # 기존 데이터 키 가져오기
        existing_keys = get_existing_keys()
        print(f"Existing data has {len(existing_keys)} entries")
        
        # 각 항목별로 처리
        new_data = []
        
        for excel_col, target_name in ITEM_MAPPING.items():
            if excel_col not in df.columns:
                print(f"\nWarning: Column '{excel_col}' not found in Excel. Skipping.")
                continue
            
            print(f"\nProcessing: {excel_col} -> {target_name}")
            
            # Forward-fill missing values (이전 값으로 채우기)
            df[excel_col] = df[excel_col].fillna(method='ffill')
            
            # 여전히 NaN인 경우 (맨 처음 값들) backward-fill
            df[excel_col] = df[excel_col].fillna(method='bfill')
            
            added_count = 0
            for idx, row in df.iterrows():
                date_str = row[date_col]
                price = row[excel_col]
                
                # NaN이 아니고 숫자인 경우만 처리
                if pd.notna(price) and isinstance(price, (int, float)):
                    key = (date_str, target_name)
                    
                    if key not in existing_keys:
                        new_data.append([date_str, target_name, float(price), 'DRAM'])
                        added_count += 1
            
            print(f"  Added {added_count} new rows")
        
        # CSV에 저장
        if new_data:
            print(f"\nSaving {len(new_data)} total new rows to {CSV_FILE}...")
            with open(CSV_FILE, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerows(new_data)
            print("Save complete!")
        else:
            print("\nNo new data to add (all data already exists)")
        
        print("\n" + "=" * 60)
        print("Import Complete!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import_memory_data()
