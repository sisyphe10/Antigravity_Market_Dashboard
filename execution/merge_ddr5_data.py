
import pandas as pd
import os
import csv
from datetime import datetime
from config import CSV_FILE

EXCEL_FILE = 'old_data.xlsx'
SHEET_NAME = 'memory'
TARGET_ITEM_NAME = 'DDR5 16G (2Gx8) 4800/5600'
CATEGORY = 'Memory'

def merge_ddr5_data():
    """Merge DDR5 data from Excel + Today's price into dataset.csv"""
    print("Starting DDR5 data merge...")
    
    new_rows = []
    
    # 1. Read Excel Data
    if os.path.exists(EXCEL_FILE):
        try:
            df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME)
            print(f"Read Excel file. Columns: {df.columns.tolist()}")
            
            # Find columns
            price_col = None
            date_col = None
            
            for col in df.columns:
                col_str = str(col)
                if 'D5_16Gb_4800' in col_str:
                    price_col = col
                if 'Date' in col_str or 'date' in col_str or '날짜' in col_str:
                    date_col = col
            
            if price_col and date_col:
                print(f"Found columns - Price: {price_col}, Date: {date_col}")
                
                # Extract data
                valid_data = df[[date_col, price_col]].dropna()
                
                for _, row in valid_data.iterrows():
                    date_val = row[date_col]
                    price_val = row[price_col]
                    
                    # Convert date to string
                    if isinstance(date_val, str):
                        try:
                            date_str = datetime.strptime(date_val, '%Y-%m-%d').strftime('%Y-%m-%d')
                        except:
                            date_str = date_val.split(' ')[0] # Simple split fix
                    else:
                        date_str = date_val.strftime('%Y-%m-%d')
                        
                    # Use raw price as requested by user
                    new_rows.append([date_str, TARGET_ITEM_NAME, price_val, CATEGORY])
                    
                print(f"Extracted {len(new_rows)} rows from Excel")
            else:
                print("Columns not found in Excel")
        except Exception as e:
            print(f"Error reading Excel: {e}")
    else:
        print(f"Excel file not found: {EXCEL_FILE}")
        
    # 2. Add Today's Price (Manual input from user)
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_price = 36.533
    new_rows.append([today_str, TARGET_ITEM_NAME, today_price, CATEGORY])
    print(f"Added today's price: {today_price}")
    
    # 3. Read existing dataset to prevent duplicates
    existing_keys = set()
    rows_to_keep = []
    
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header:
                rows_to_keep.append(header)
            
            for row in reader:
                if len(row) >= 2:
                    # Remove existing DDR5 data to replace with new data
                    if row[1] == TARGET_ITEM_NAME:
                        continue
                    
                    rows_to_keep.append(row)
                    existing_keys.add((row[0], row[1]))
    
    # 4. Merge new data
    added_count = 0
    for row in new_rows:
        date_str = row[0]
        item_name = row[1]
        
        # We removed all existing DDR5, so just check date dupes within new_rows?
        # Actually simplest is just valid rows are gathered.
        # But we might have duplicates in Excel itself. 
        # Let's use a dict to keep latest value for each date
        pass 

    # Key by date to remove duplicates, preferring latest
    ddr5_data_by_date = {}
    for row in new_rows:
        ddr5_data_by_date[row[0]] = row
        
    sorted_dates = sorted(ddr5_data_by_date.keys())
    
    for date in sorted_dates:
        rows_to_keep.append(ddr5_data_by_date[date])
        added_count += 1
        
    print(f"Total DDR5 rows to be saved: {added_count}")
        
    # 5. Save back to CSV
    # Sort by date (row[0])
    # Skip header when sorting
    header = rows_to_keep[0]
    data_rows = rows_to_keep[1:]
    data_rows.sort(key=lambda x: x[0])
    
    with open(CSV_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data_rows)
        
    print(f"Successfully saved {len(data_rows)} rows to {CSV_FILE}")

if __name__ == "__main__":
    merge_ddr5_data()
