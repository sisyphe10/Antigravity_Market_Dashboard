
import csv
import os
from datetime import datetime

CSV_FILE = 'dataset.csv'

def clean_legacy_data():
    """Remove old data for DDR5 16G and Bitcoin, keep only today's data onwards"""
    
    if not os.path.exists(CSV_FILE):
        print(f"File not found: {CSV_FILE}")
        return
    
    today = datetime.now().strftime('%Y-%m-%d')
    print(f"Today's date: {today}")
    
    rows_to_keep = []
    removed_count = 0
    
    try:
        with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header:
                rows_to_keep.append(header)
            
            for row in reader:
                if len(row) >= 2:
                    date_str = row[0]
                    item_name = row[1]
                    
                    # Check if this is DDR5 16G or Bitcoin
                    is_ddr5 = 'DDR5 16G' in item_name
                    is_bitcoin = item_name == 'Bitcoin'
                    
                    # If it's one of these items and date is before today, skip it
                    if (is_ddr5 or is_bitcoin) and date_str < today:
                        removed_count += 1
                        print(f"Removing: {date_str} - {item_name}")
                        continue
                
                rows_to_keep.append(row)
        
        # Write back
        with open(CSV_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerows(rows_to_keep)
        
        print(f"\nCleanup complete!")
        print(f"Removed {removed_count} old rows")
        print(f"Remaining rows: {len(rows_to_keep) - 1}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    clean_legacy_data()
