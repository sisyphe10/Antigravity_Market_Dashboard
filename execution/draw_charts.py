
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os
from datetime import datetime, timedelta

# Constants
CSV_FILE = 'dataset.csv'
CHARTS_DIR = 'charts'
LINE_COLOR = '#404040'  # RGB(64, 64, 64)

def setup_charts_dir():
    """Create charts directory if it doesn't exist."""
    if not os.path.exists(CHARTS_DIR):
        os.makedirs(CHARTS_DIR)
        print(f"✅ Created directory: {CHARTS_DIR}")

def draw_charts():
    """Draw charts for each item in dataset.csv."""
    if not os.path.exists(CSV_FILE):
        print(f"❌ File not found: {CSV_FILE}")
        return

    try:
        # Load data
        df = pd.read_csv(CSV_FILE)
        
        # Standardize column names (remove whitespace)
        df.columns = [c.strip() for c in df.columns]
        
        # Check required columns
        required_cols = ['날짜', '제품명', '가격']
        if not all(col in df.columns for col in required_cols):
            print(f"❌ Missing columns. Required: {required_cols}")
            return

        # Convert date column to datetime
        df['날짜'] = pd.to_datetime(df['날짜'])
        
        # Sort by date
        df = df.sort_values(by='날짜')

        # Get the latest date across all data (latest 'collected' or 'available' date)
        if df.empty:
            print("⚠️ Dataset is empty.")
            return

        global_latest_date = df['날짜'].max()
        start_date = global_latest_date - timedelta(days=180) # Approx 6 months

        print(f"📅 Latest Data: {global_latest_date.strftime('%Y-%m-%d')}")
        print(f"📉 Filter Start Date: {start_date.strftime('%Y-%m-%d')}")

        # Group by item name
        grouped = df.groupby('제품명')

        for name, group in grouped:
            # Filter for last 6 months relative to global latest date
            # (Or should it be relative to the item's latest? 
            #  User said "based on the most recent data" (latest data point).
            #  I'll use global latest to keep the X-axis comparable if needed, 
            #  but usually, we just want the history. 
            #  Let's allow items to have their own history if they stopped updating, 
            #  but user said "Last 6 months period".)
            #  
            #  Actually, "From the latest data point, show last 6 months" 
            #  implies the window [latest - 6mo, latest].
            
            # Filter data within the range
            mask = (group['날짜'] >= start_date) & (group['날짜'] <= global_latest_date)
            filtered_data = group.loc[mask]

            if filtered_data.empty:
                print(f"⚠️ No data in range for: {name}")
                continue

            # Plotting
            plt.figure(figsize=(10, 6))
            
            # Plot line
            plt.plot(filtered_data['날짜'], filtered_data['가격'], color=LINE_COLOR, label=name)
            
            # Formatting
            plt.title(f"{name} (Last 6 Months)", fontsize=14)
            plt.xlabel("Date")
            plt.ylabel("Price")
            
            # X-axis date formatting
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            plt.gca().xaxis.set_major_locator(mdates.MonthLocator())
            plt.gcf().autofmt_xdate() # Rotate dates

            # Y-axis tight margins: "위아래 여백이 크지 않았으면 좋겠어"
            # margins(y=0) removes standard padding.
            plt.margins(y=0.02) 

            # Legend at top center
            plt.legend(loc='upper center', bbox_to_anchor=(0.5, 1.1), ncol=1)

            # Grid
            plt.grid(True, linestyle='--', alpha=0.5)

            # Save
            # Clean filename
            safe_name = "".join([c if c.isalnum() else "_" for c in name])
            save_path = os.path.join(CHARTS_DIR, f"{safe_name}.png")
            plt.savefig(save_path, bbox_inches='tight')
            plt.close()
            
            print(f"✓ Saved chart: {save_path}")

    except Exception as e:
        print(f"❌ Error drawing charts: {e}")

if __name__ == "__main__":
    setup_charts_dir()
    draw_charts()
