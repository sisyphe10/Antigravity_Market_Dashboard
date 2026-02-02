
import csv
import os

CSV_FILE = 'dataset.csv'
TARGET_TO_REMOVE = 'Uranium ETF (URA)'

def remove_ura_data():
    if not os.path.exists(CSV_FILE):
        print("CSV file not found")
        return

    rows_to_keep = []
    removed_count = 0
    
    with open(CSV_FILE, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
            rows_to_keep.append(header)
        except StopIteration:
            pass
            
        for row in reader:
            if len(row) > 1 and row[1] == TARGET_TO_REMOVE:
                removed_count += 1
                continue
            rows_to_keep.append(row)
            
    if removed_count > 0:
        with open(CSV_FILE, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(rows_to_keep)
        print(f"Removed {removed_count} rows of '{TARGET_TO_REMOVE}'")
    else:
        print(f"No rows found for '{TARGET_TO_REMOVE}'")

if __name__ == "__main__":
    remove_ura_data()
