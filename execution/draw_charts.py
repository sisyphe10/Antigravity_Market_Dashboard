
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator, FuncFormatter
import os
from datetime import datetime, timedelta

# Constants
CSV_FILE = 'dataset.csv'
CHARTS_DIR = 'charts'
LINE_COLOR = '#404040'  # RGB(64, 64, 64)

# Category mapping for grouping
CATEGORY_MAP = {
    'DRAM': 'Memory',
    'NAND': 'Memory',
    'CRYPTO': 'Cryptocurrency',
    'COMMODITY': 'Commodities',
    'FX': 'Foreign Exchange',
    'INDEX_US': 'US Indices',
    'INTEREST_RATE': 'Interest Rates',
    'INDEX': 'Market Indices',
    'OCEAN_FREIGHT': 'Shipping'
}

def smart_format_yaxis(y, pos):
    """
    Smart Y-axis formatter that adjusts precision based on value range.
    - Large values (>1000): no decimals
    - Medium values (1-1000): 1-2 decimals
    - Small values (<1): 2-4 decimals
    """
    if abs(y) >= 1000:
        return f'{y:,.0f}'  # No decimals for large numbers
    elif abs(y) >= 100:
        return f'{y:.0f}'   # No decimals for hundreds
    elif abs(y) >= 10:
        return f'{y:.1f}'   # 1 decimal for tens
    elif abs(y) >= 1:
        return f'{y:.2f}'   # 2 decimals for single digits
    elif abs(y) >= 0.01:
        return f'{y:.3f}'   # 3 decimals for cents
    else:
        return f'{y:.4f}'   # 4 decimals for very small values

def setup_charts_dir():
    """Create charts directory if it doesn't exist."""
    if not os.path.exists(CHARTS_DIR):
        os.makedirs(CHARTS_DIR)
        print(f"Created directory: {CHARTS_DIR}")

def draw_charts():
    """Draw charts for each item in dataset.csv."""
    if not os.path.exists(CSV_FILE):
        print(f"File not found: {CSV_FILE}")
        return

    try:
        # Load data
        df = pd.read_csv(CSV_FILE)
        
        # Standardize column names (remove whitespace)
        df.columns = [c.strip() for c in df.columns]
        
        # Check required columns
        required_cols = ['날짜', '제품명', '가격']
        if not all(col in df.columns for col in required_cols):
            print(f"Missing columns. Required: {required_cols}")
            return

        # Convert date column to datetime
        df['날짜'] = pd.to_datetime(df['날짜'])
        
        # Convert price to numeric, handling commas
        df['가격'] = pd.to_numeric(df['가격'].astype(str).str.replace(',', ''), errors='coerce')
        
        # Sort by date
        df = df.sort_values(by='날짜')

        # Get the latest date across all data
        if df.empty:
            print("Dataset is empty.")
            return

        global_latest_date = df['날짜'].max()
        start_date = global_latest_date - timedelta(days=180) # Approx 6 months

        print(f"Latest Data: {global_latest_date.strftime('%Y-%m-%d')}")
        print(f"Filter Start Date: {start_date.strftime('%Y-%m-%d')}")

        # Group by item name
        grouped = df.groupby('제품명')

        for name, group in grouped:
            # Filter data within the range
            mask = (group['날짜'] >= start_date) & (group['날짜'] <= global_latest_date)
            filtered_data = group.loc[mask].copy()

            if filtered_data.empty:
                print(f"No data in range for: {name}")
                continue

            # Forward-fill missing dates
            # Create a complete date range
            date_range = pd.date_range(start=filtered_data['날짜'].min(), 
                                      end=filtered_data['날짜'].max(), 
                                      freq='D')
            
            # Reindex to include all dates, forward-fill missing values
            filtered_data = filtered_data.set_index('날짜')
            filtered_data = filtered_data.reindex(date_range, method='ffill')
            filtered_data.index.name = '날짜'
            filtered_data = filtered_data.reset_index()

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

            # Y-axis: Smart formatting with ~8 ticks
            ax = plt.gca()
            ax.yaxis.set_major_locator(MaxNLocator(nbins=8, prune='both'))
            ax.yaxis.set_major_formatter(FuncFormatter(smart_format_yaxis))

            # Y-axis tight margins
            plt.margins(y=0.02) 

            # Legend at top center
            plt.legend(loc='upper center', bbox_to_anchor=(0.5, 1.1), ncol=1)

            # Grid
            plt.grid(True, linestyle='--', alpha=0.5)

            # Save with category metadata in filename for later grouping
            # Get category from data type if available
            category = 'Other'
            if '데이터 타입' in group.columns:
                data_type = group['데이터 타입'].iloc[0]
                category = CATEGORY_MAP.get(data_type, 'Other')
            
            # Clean filename
            safe_name = "".join([c if c.isalnum() else "_" for c in name])
            save_path = os.path.join(CHARTS_DIR, f"{safe_name}.png")
            plt.savefig(save_path, bbox_inches='tight', metadata={'Category': category})
            plt.close()
            
            print(f"Saved chart: {save_path} (Category: {category})")

    except Exception as e:
        print(f"Error drawing charts: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    setup_charts_dir()
    draw_charts()
