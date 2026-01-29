
import csv
import os

CSV_FILE = 'dataset.csv'

def remove_old_treasury_data():
    """Remove old US 2 Year Treasury Yield data (now replaced with 5 Year and 13 Week)"""
    
    if not os.path.exists(CSV_FILE):
        print(f"File not found: {CSV_FILE}")
        return
    
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
                    item_name = row[1]
                    
                    # Remove old US 2 Year Treasury Yield data
                    if item_name == 'US 2 Year Treasury Yield':
                        removed_count += 1
                        print(f"Removing: {row[0]} - {item_name}")
                        continue
                
                rows_to_keep.append(row)
        
        # Write back
        with open(CSV_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerows(rows_to_keep)
        
        print(f"\nRemoved {removed_count} old US 2 Year Treasury rows")
        print(f"Remaining rows: {len(rows_to_keep) - 1}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    remove_old_treasury_data()
