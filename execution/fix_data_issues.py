
import csv
import os

CSV_FILE = 'dataset.csv'

def fix_data_issues():
    """Fix EUR/USD incorrect data (value = 1) and remove incomplete DDR5 data"""
    
    if not os.path.exists(CSV_FILE):
        print(f"File not found: {CSV_FILE}")
        return
    
    rows_to_keep = []
    eur_fixed = 0
    ddr5_removed = 0
    
    try:
        with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header:
                rows_to_keep.append(header)
            
            for row in reader:
                if len(row) >= 3:
                    item_name = row[1]
                    price = row[2]
                    
                    # Remove DDR5 16G data (only 1 row, not useful for charts)
                    if 'DDR5 16G' in item_name:
                        ddr5_removed += 1
                        print(f"Removing DDR5: {row[0]} - {item_name}")
                        continue
                    
                    # Fix EUR/USD data where price = 1 (incorrect)
                    if item_name == 'EUR/USD' and price.strip() == '1':
                        eur_fixed += 1
                        print(f"Removing incorrect EUR/USD: {row[0]} - price={price}")
                        continue
                
                rows_to_keep.append(row)
        
        # Write back
        with open(CSV_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerows(rows_to_keep)
        
        print(f"\nCleanup complete!")
        print(f"Fixed/removed {eur_fixed} incorrect EUR/USD rows")
        print(f"Removed {ddr5_removed} DDR5 rows")
        print(f"Remaining rows: {len(rows_to_keep) - 1}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    fix_data_issues()
