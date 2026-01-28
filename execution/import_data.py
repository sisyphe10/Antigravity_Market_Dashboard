
import csv
import os
from datetime import datetime

LEGACY_FILE = 'temp_old_data.csv'
TARGET_FILE = 'dataset.csv'

def clean_date(date_str):
    """Convert '2025. 12. 16' to '2025-12-16'"""
    try:
        # Remove whitespace and replace dots
        date_str = date_str.strip()
        dt = datetime.strptime(date_str, '%Y. %m. %d')
        return dt.strftime('%Y-%m-%d')
    except ValueError:
        try:
            # Try without spaces just in case '2025.12.16'
            dt = datetime.strptime(date_str, '%Y.%m.%d')
            return dt.strftime('%Y-%m-%d')
        except:
            return None

def import_data():
    if not os.path.exists(LEGACY_FILE):
        print(f"❌ Legacy file not found: {LEGACY_FILE}")
        return

    # Read existing data to avoid duplicates
    existing_data = set()
    if os.path.exists(TARGET_FILE):
        with open(TARGET_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for row in reader:
                if len(row) >= 2:
                    # Key: (Date, ItemName)
                    existing_data.add((row[0], row[1]))
    
    # Read legacy data
    # Trying cp949 first because of the broken korean characters seen in terminal
    # If that fails, try utf-8
    rows_to_add = []
    
    try:
        with open(LEGACY_FILE, 'r', encoding='mbcs') as f: # 'mbcs' for Windows default ANSI/CP949
            reader = csv.reader(f)
            next(reader, None) # Skip header
            
            for row in reader:
                if len(row) < 3: continue
                
                raw_date = row[0]
                item_name = row[1]
                price = row[2]
                data_type = row[3] if len(row) > 3 else 'UNKNOWN'
                
                clean_d = clean_date(raw_date)
                if not clean_d:
                    print(f"⚠️ Skipping invalid date: {raw_date}")
                    continue
                
                # Check for duplicates
                if (clean_d, item_name) not in existing_data:
                    rows_to_add.append([clean_d, item_name, price, data_type])
                    existing_data.add((clean_d, item_name))
                    
    except Exception as e:
        print(f"❌ Error reading legacy file: {e}")
        return

    # Append to target file
    if rows_to_add:
        # If target didn't exist, create it with header
        if not os.path.exists(TARGET_FILE):
             with open(TARGET_FILE, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['날짜', '제품명', '가격', '데이터 타입'])
        
        with open(TARGET_FILE, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerows(rows_to_add)
            
        print(f"Successfully imported {len(rows_to_add)} rows.")
    else:
        print("No new data to import.")

    # Cleanup
    try:
        os.remove(LEGACY_FILE)
        # os.remove('old_data.xlsx') # User might want to keep the original? I'll leave it or ask.
        print("Cleaned up temporary CSV.")
    except:
        pass

if __name__ == '__main__':
    import_data()
