import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator, FuncFormatter
import os
from datetime import datetime, timedelta
import matplotlib.font_manager as fm

# 한글 폰트 설정
plt.rcParams['font.family'] = 'Malgun Gothic'  # Windows 기본 한글 폰트
plt.rcParams['axes.unicode_minus'] = False  # 마이너스 기호 깨짐 방지

# Constants
WRAP_NAV_FILE = 'Wrap_NAV.xlsx'
CHARTS_DIR = 'charts'
LINE_COLOR = '#404040'  # RGB(64, 64, 64)

# 포트폴리오 매핑 (엑셀 시트의 컬럼명 -> 표시할 이름)
PORTFOLIO_NAMES = {
    '트루밸류': '삼성 트루밸류',
    'Value ESG': 'NH Value ESG',
    '개방형 랩': 'DB 개방형',
    '목표전환형': 'DB 목표전환형'
}

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

def draw_wrap_charts():
    """Draw charts for Wrap portfolios from Wrap_NAV.xlsx."""
    if not os.path.exists(WRAP_NAV_FILE):
        print(f"File not found: {WRAP_NAV_FILE}")
        return

    try:
        # Load data from '기준가' sheet
        df = pd.read_excel(WRAP_NAV_FILE, sheet_name='기준가')

        # Set Date column as index
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.set_index('Date')
        else:
            df.index = pd.to_datetime(df.iloc[:, 0])
            df = df.iloc[:, 1:]

        if df.empty:
            print("Dataset is empty.")
            return

        # Get the latest date across all data
        global_latest_date = df.index.max()
        start_date = global_latest_date - timedelta(days=180)  # Approx 6 months

        print(f"Latest Data: {global_latest_date.strftime('%Y-%m-%d')}")
        print(f"Filter Start Date: {start_date.strftime('%Y-%m-%d')}")

        # Draw chart for each portfolio
        for col_name, display_name in PORTFOLIO_NAMES.items():
            if col_name not in df.columns:
                print(f"Portfolio not found in data: {col_name}")
                continue

            # Get portfolio data
            portfolio_data = df[[col_name]].copy()
            portfolio_data = portfolio_data.dropna()

            if portfolio_data.empty:
                print(f"No data for portfolio: {col_name}")
                continue

            # Filter data within the range
            mask = (portfolio_data.index >= start_date) & (portfolio_data.index <= global_latest_date)
            filtered_data = portfolio_data.loc[mask].copy()

            if filtered_data.empty:
                print(f"No data in range for: {col_name}")
                continue

            # Forward-fill missing dates
            date_range = pd.date_range(start=filtered_data.index.min(),
                                      end=filtered_data.index.max(),
                                      freq='D')

            filtered_data = filtered_data.reindex(date_range, method='ffill')

            # Get latest value
            latest_value = portfolio_data.iloc[-1][col_name]
            latest_date = portfolio_data.index[-1]

            # WoW Calculation
            target_date = latest_date - timedelta(days=7)
            past_data = portfolio_data[portfolio_data.index <= target_date]

            wow_label = ""
            if not past_data.empty:
                past_value = past_data.iloc[-1][col_name]

                if past_value != 0:
                    change = ((latest_value - past_value) / past_value) * 100
                    sign = "+" if change > 0 else ""
                    wow_label = f" ({sign}{change:.1f}%)"

            # Plotting
            fig, ax = plt.subplots(figsize=(10, 6))

            # Plot line
            ax.plot(filtered_data.index, filtered_data[col_name], color=LINE_COLOR)

            # Format Price
            if abs(latest_value) >= 1000:
                price_str = f"{latest_value:,.0f}"
            elif abs(latest_value) >= 1:
                price_str = f"{latest_value:,.2f}"
            else:
                price_str = f"{latest_value:,.4f}"

            # Construct Title
            title_text = f"{display_name} | {price_str}"

            if wow_label:
                title_text += f" {wow_label}"

            # Set Title
            ax.set_title(title_text, fontsize=14, color='black', pad=10)

            # Remove axis labels
            ax.set_xlabel("")
            ax.set_ylabel("")

            # X-axis date formatting - YY/MM format (no rotation)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%y/%m'))
            ax.xaxis.set_major_locator(mdates.MonthLocator())
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha='center')

            # Y-axis: Smart formatting with ~8 ticks
            ax.yaxis.set_major_locator(MaxNLocator(nbins=8, prune='both'))
            ax.yaxis.set_major_formatter(FuncFormatter(smart_format_yaxis))

            # Y-axis tight margins
            ax.margins(y=0.02)

            # Grid
            ax.grid(True, linestyle='--', alpha=0.5)

            # Save chart
            safe_name = "".join([c if c.isalnum() else "_" for c in display_name])
            save_path = os.path.join(CHARTS_DIR, f"{safe_name}.png")
            plt.savefig(save_path, bbox_inches='tight')
            plt.close()

            print(f"Saved chart: {save_path}")

    except Exception as e:
        print(f"Error drawing Wrap charts: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    setup_charts_dir()
    draw_wrap_charts()
