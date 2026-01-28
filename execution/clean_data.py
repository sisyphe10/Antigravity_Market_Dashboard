
import csv
import os

CSV_FILE = 'dataset.csv'

def clean_data():
    if not os.path.exists(CSV_FILE):
        print(f"❌ File not found: {CSV_FILE}")
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
                if len(row) >= 4:
                    data_type = row[3]
                    # Filter out INDEX_KR
                    if data_type == 'INDEX_KR':
                        removed_count += 1
                        continue
                    # Also check for 'KOSPI' or 'KOSDAQ' in name just in case
                    if 'KOSPI' in row[1] or 'KOSDAQ' in row[1]:
                         removed_count += 1
                         continue
                
                rows_to_keep.append(row)

        with open(CSV_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerows(rows_to_keep)

        print(f"Cleanup complete. Removed {removed_count} rows.")
        print(f"Remaining rows: {len(rows_to_keep) - 1}") # exclude header

    except Exception as e:
        print(f"Error cleaning data: {e}")

if __name__ == "__main__":
    clean_data()
