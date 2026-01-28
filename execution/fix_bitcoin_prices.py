
import csv
import os

CSV_FILE = 'dataset.csv'

def fix_bitcoin_prices():
    """Fix Bitcoin prices for Jan 27-28, 2026"""
    
    if not os.path.exists(CSV_FILE):
        print(f"File not found: {CSV_FILE}")
        return
    
    rows = []
    fixed_count = 0
    
    # Correct prices from user
    correct_prices = {
        '2026-01-27': 89207.46,
        '2026-01-28': 89043.03
    }
    
    try:
        with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header:
                rows.append(header)
            
            for row in reader:
                if len(row) >= 3:
                    date_str = row[0]
                    item_name = row[1]
                    
                    # Fix Bitcoin prices for these specific dates
                    if item_name == 'Bitcoin' and date_str in correct_prices:
                        old_price = row[2]
                        new_price = correct_prices[date_str]
                        row[2] = str(new_price)
                        print(f"Fixed {date_str}: {old_price} -> {new_price}")
                        fixed_count += 1
                
                rows.append(row)
        
        # Write back
        with open(CSV_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        
        print(f"\nFixed {fixed_count} Bitcoin prices")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    fix_bitcoin_prices()
