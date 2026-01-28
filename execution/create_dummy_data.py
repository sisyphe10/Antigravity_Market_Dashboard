
import csv
import random
from datetime import datetime, timedelta

CSV_FILE = 'dataset.csv'
ITEMS = ['DDR5 16G (2Gx8) 4800/5600', 'Bitcoin', 'KOSPI']

def create_dummy_data():
    with open(CSV_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['날짜', '제품명', '가격', '데이터 타입'])
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=200) # ~ 7 months
        
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            
            # DDR5
            price = 3.5 + random.uniform(-0.5, 0.5)
            writer.writerow([date_str, ITEMS[0], round(price, 2), 'DRAM'])
            
            # Bitcoin
            price = 45000 + random.uniform(-5000, 5000)
            writer.writerow([date_str, ITEMS[1], round(price, 2), 'CRYPTO'])

            # KOSPI
            price = 2500 + random.uniform(-200, 200)
            writer.writerow([date_str, ITEMS[2], round(price, 2), 'INDEX_KR'])
            
            current_date += timedelta(days=1)
            
    print(f"Generated dummy data in {CSV_FILE}")

if __name__ == '__main__':
    create_dummy_data()
