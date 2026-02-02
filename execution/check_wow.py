
import csv
from datetime import datetime, timedelta

def check_wow_logic():
    csv_file = 'dataset.csv'
    data = {} # {item_name: [(date, price), ...]}
    
    # 1. Read CSV
    try:
        with open(csv_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader) # Skip header
            for row in reader:
                if len(row) < 3: continue
                date_str = row[0]
                name = row[1]
                try:
                    price = float(row[2].replace(',', ''))
                    # Date parsing
                    if '-' in date_str:
                        dt = datetime.strptime(date_str, '%Y-%m-%d')
                    else: continue
                    
                    if name not in data: data[name] = []
                    data[name].append((dt, price))
                except:
                    continue
    except FileNotFoundError:
        print("dataset.csv not found")
        return

    # 2. Logic Verification
    print(f"Total items: {len(data)}")
    
    for name, rows in data.items():
        # Sort by date
        rows.sort(key=lambda x: x[0])
        
        if not rows: continue
        
        latest_date, latest_price = rows[-1]
        target_date = latest_date - timedelta(days=7)
        
        # Find closest past date <= target_date
        past_price = None
        past_date_found = None
        
        # Search backwards from end
        for i in range(len(rows)-1, -1, -1):
            curr_dt, curr_price = rows[i]
            if curr_dt <= target_date:
                past_price = curr_price
                past_date_found = curr_dt
                break
        
        wow_str = "N/A"
        if past_price is not None and past_price != 0:
            change = ((latest_price - past_price) / past_price) * 100
            sign = "+" if change > 0 else ""
            wow_str = f"{sign}{change:.1f}%"
            
        print(f"[{name}] Latest: {latest_date.strftime('%Y-%m-%d')} (${latest_price}) | "
              f"7 Days Ago ({target_date.strftime('%Y-%m-%d')}): Found {past_date_found.strftime('%Y-%m-%d') if past_date_found else 'None'} (${past_price}) | "
              f"WoW: {wow_str}")

if __name__ == "__main__":
    check_wow_logic()
