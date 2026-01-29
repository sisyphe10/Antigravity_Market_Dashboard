
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
    'FX': 'Exchange Rate',
    'INDEX_US': 'US Indices',
    'INTEREST_RATE': 'Interest Rates',
    'INDEX': 'US Indices',
    'OCEAN_FREIGHT': 'Commodities'  # SCFI moved to Commodities
}

def get_category_for_item(item_name, data_type):
    """Determine category based on item name and data type"""
    # Special handling for DDR items (they're DRAM but should be in Memory)
    if 'DDR4' in item_name or 'DDR5' in item_name:
        return 'Memory'
    # Use data type mapping
    return CATEGORY_MAP.get(data_type, 'Other')

def smart_format_yaxis(y, pos):
    """
    Smart Y-axis formatter - no more than 1 decimal place.
    - Large values (>=100): no decimals
    - Medium/small values: max 1 decimal
    """
    if abs(y) >= 100:
        return f'{y:,.0f}'  # No decimals for >= 100
    elif abs(y) >= 1:
        return f'{y:.1f}'   # Max 1 decimal for 1-100
    else:
        return f'{y:.2f}'   # Max 2 decimals for very small values < 1

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
            date_range = pd.date_range(start=filtered_data['날짜'].min(), 
                                      end=filtered_data['날짜'].max(), 
                                      freq='D')
            
            filtered_data = filtered_data.set_index('날짜')
            filtered_data = filtered_data.reindex(date_range, method='ffill')
            filtered_data.index.name = '날짜'
            filtered_data = filtered_data.reset_index()

            # Plotting
            fig, ax = plt.subplots(figsize=(10, 6))
            
            # Plot line
            ax.plot(filtered_data['날짜'], filtered_data['가격'], color=LINE_COLOR, label=name)
            
            # Title without "(Last 6 Months)" - just the item name
            ax.set_title(f"{name}", fontsize=14)
            
            # Axis labels positioned as requested
            # X-axis label at bottom right
            ax.set_xlabel("Date", fontsize=10, loc='right')
            # Y-axis label at top left
            ax.set_ylabel("Price", fontsize=10, loc='top')
            
            # X-axis date formatting - YY/MM format (no rotation)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%y/%m'))
            ax.xaxis.set_major_locator(mdates.MonthLocator())
            # Don't rotate labels - keep them horizontal
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha='center')

            # Y-axis: Smart formatting with ~8 ticks
            ax.yaxis.set_major_locator(MaxNLocator(nbins=8, prune='both'))
            ax.yaxis.set_major_formatter(FuncFormatter(smart_format_yaxis))

            # Y-axis tight margins
            ax.margins(y=0.02)

            # Legend at top center (without redundant title info)
            ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.1), ncol=1)

            # Grid
            ax.grid(True, linestyle='--', alpha=0.5)

            # Get category from data type
            category = 'Other'
            if '데이터 타입' in group.columns:
                data_type = group['데이터 타입'].iloc[0]
                category = get_category_for_item(name, data_type)
            
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
