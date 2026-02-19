
import os
import glob
from datetime import datetime
import csv
import json
from pathlib import Path

# Import shared configuration
from config import CATEGORY_MAP, CSV_FILE

# Version 3.0 - Added category grouping
CHARTS_DIR = 'charts'
OUTPUT_FILE = 'index.html'
def create_portfolio_tables_html():
    """포트폴리오 테이블 HTML 생성"""
    portfolio_file = 'portfolio_data.json'

    if not os.path.exists(portfolio_file):
        return ""

    try:
        with open(portfolio_file, 'r', encoding='utf-8') as f:
            portfolio_data = json.load(f)

        html = ""

        for portfolio_name, stocks in portfolio_data.items():
            # 포트폴리오별 테이블 생성
            html += f"""
            <div class="portfolio-section">
                <h3 class="portfolio-title">{portfolio_name}</h3>
                <div class="table-container">
                    <table class="portfolio-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>종목코드</th>
                                <th>종목명</th>
                                <th>섹터</th>
                                <th>시가총액</th>
                                <th>Weight</th>
                                <th>오늘 수익률</th>
                                <th>기여도</th>
                                <th>누적 수익률</th>
                            </tr>
                        </thead>
                        <tbody>
            """

            # 합계 계산용 변수
            total_weight = 0
            weighted_return_sum = 0
            total_contribution = 0
            valid_returns_count = 0

            # 각 종목 행 추가
            for idx, stock in enumerate(stocks, 1):
                mc = stock['market_cap']
                if mc > 0:
                    jo = int(mc // 10000)
                    eok = int(mc % 10000)
                    if jo > 0:
                        market_cap_str = f"{jo:,}조{eok:,}억" if eok > 0 else f"{jo:,}조"
                    else:
                        market_cap_str = f"{eok:,}억"
                else:
                    market_cap_str = "N/A"

                # 오늘 수익률 포맷
                today_return = stock.get('today_return')
                weight = stock['weight']
                total_weight += weight

                if today_return is not None:
                    today_return_str = f"{today_return:+.1f}%"
                    today_color_class = "positive" if today_return > 0 else "negative" if today_return < 0 else ""
                    weighted_return_sum += today_return * weight / 100
                    valid_returns_count += 1
                else:
                    today_return_str = "N/A"
                    today_color_class = ""

                # 기여도 포맷
                contribution = stock.get('contribution')
                if contribution is not None:
                    contribution_str = f"{contribution:+.1f}"
                    contribution_color_class = "positive" if contribution > 0 else "negative" if contribution < 0 else ""
                    total_contribution += contribution
                else:
                    contribution_str = "N/A"
                    contribution_color_class = ""

                # 누적 수익률 포맷
                cumulative_return = stock.get('cumulative_return')
                if cumulative_return is not None:
                    cumulative_return_str = f"{cumulative_return:+.1f}%"
                    cumulative_color_class = "positive" if cumulative_return > 0 else "negative" if cumulative_return < 0 else ""
                else:
                    cumulative_return_str = "N/A"
                    cumulative_color_class = ""

                html += f"""
                            <tr>
                                <td>{idx}</td>
                                <td>{stock['code']}</td>
                                <td>{stock['name']}</td>
                                <td>{stock['sector']}</td>
                                <td>{market_cap_str}</td>
                                <td>{stock['weight']}%</td>
                                <td class="{today_color_class}">{today_return_str}</td>
                                <td class="{contribution_color_class}">{contribution_str}</td>
                                <td class="{cumulative_color_class}">{cumulative_return_str}</td>
                            </tr>
                """

            # 합계 행 추가
            portfolio_return_str = f"{weighted_return_sum:+.1f}%" if valid_returns_count > 0 else "N/A"
            portfolio_color = "positive" if weighted_return_sum > 0 else "negative" if weighted_return_sum < 0 else ""
            total_contribution_str = f"{total_contribution:+.1f}" if valid_returns_count > 0 else "N/A"
            contribution_total_color = "positive" if total_contribution > 0 else "negative" if total_contribution < 0 else ""

            html += f"""
                            <tr class="total-row">
                                <td colspan="5" style="text-align: right; font-weight: 600;">합계</td>
                                <td style="font-weight: 600;">{total_weight:.0f}%</td>
                                <td class="{portfolio_color}" style="font-weight: 600;">{portfolio_return_str}</td>
                                <td class="{contribution_total_color}" style="font-weight: 600;">{total_contribution_str}</td>
                                <td style="font-weight: 600;">-</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
            """

        return html

    except Exception as e:
        print(f"Error creating portfolio tables: {e}")
        return ""

def get_item_category(item_name):
    """Get category for an item by looking up in dataset.csv"""
    # Special handling for DDR items (they should be in Memory)
    if 'DDR4' in item_name or 'DDR5' in item_name:
        return 'MEMORY'

    # Special handling for S&P 500 related items (should be in US Indices)
    # Handle all variations: "S&P 500", "S_P_500", "S P 500"
    if 'S&P 500' in item_name or 'S_P_500' in item_name or 'S P 500' in item_name:
        return 'INDEX_US'

    # Special handling for Uranium ETF (should be in Commodities)
    if 'Uranium' in item_name or 'URA' in item_name:
        return 'COMMODITIES'

    # Special handling for Wrap portfolios
    wrap_keywords = ['트루밸류', '삼성 트루밸류', 'Value ESG', 'NH Value ESG',
                     '개방형', 'DB 개방형', '목표전환형', 'DB 목표전환형']
    if any(keyword in item_name for keyword in wrap_keywords):
        return 'Wrap'

    try:
        with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('제품명', '').strip() == item_name:
                    data_type = row.get('데이터 타입', '').strip()
                    return CATEGORY_MAP.get(data_type, 'Other')
    except:
        pass
    return 'Other'

def create_dashboard():
    # Check if charts directory exists
    if not os.path.exists(CHARTS_DIR):
        print(f"Charts directory not found: {CHARTS_DIR}")
        return

    # Get all png files
    chart_files = glob.glob(os.path.join(CHARTS_DIR, '*.png'))
    chart_files.sort()

    if not chart_files:
        print("No charts found.")
        charts_html = "<p style='text-align:center; width:100%;'>No charts available yet.</p>"
    else:
        # Group charts by category
        charts_by_category = {}
        
        for file_path in chart_files:
            filename = os.path.basename(file_path)
            # Extract item name from filename (remove .png and replace _ with space)
            item_name = os.path.splitext(filename)[0].replace('_', ' ')
            
            # Normalize S P 500 to S&P 500 (fix chart naming)
            item_name = item_name.replace('S P 500', 'S&P 500')
            
            # Fix Dollar Index naming: "Dollar Index  DXY " -> "Dollar Index (DXY)"
            if 'Dollar Index' in item_name:
                item_name = 'Dollar Index (DXY)'
                
            # Fix FX naming: convert "XXX USD" to "XXX/USD" to match dataset format
            item_name = item_name.replace(' USD', '/USD').strip()
            
            # Get category
            category = get_item_category(item_name)
            
            if category not in charts_by_category:
                charts_by_category[category] = []
            
            charts_by_category[category].append({
                'filename': filename,
                'title': item_name,
                'path': f"charts/{filename}"
            })
        
        # Build HTML with category sections
        charts_html = ""
        
        # Define category order for better organization
        category_order = ['Wrap', 'Portfolio', 'INDEX_KOREA', 'INDEX_US', 'EXCHANGE RATE', 'INTEREST RATES',
                         'CRYPTOCURRENCY', 'MEMORY', 'COMMODITIES']
        
        for category in category_order:
            # Portfolio는 차트가 아니라 테이블이므로 특별 처리
            if category == 'Portfolio':
                # Portfolio 테이블 HTML 생성
                portfolio_html = create_portfolio_tables_html()
                if portfolio_html:
                    charts_html += f"""
            <div class="category-section">
                <h2 class="category-title">Portfolio</h2>
                <div class="portfolio-section-wrapper">
                    {portfolio_html}
                </div>
            </div>
            """
                continue

            if category not in charts_by_category:
                continue

            charts = charts_by_category[category]
            
            # ========================================
            # Custom ordering for each category
            # ========================================
            
            # Cryptocurrency order
            if category == 'CRYPTOCURRENCY':
                custom_order = ['BTC', 'ETH', 'BNB', 'XRP', 'SOL']

            # Memory order
            elif category == 'MEMORY':
                custom_order = [
                    'DDR5 16G (2Gx8) 4800/5600',
                    'DDR4 16Gb (2Gx8)3200',
                    'DDR4 16Gb (1Gx16)3200',
                    'DDR4 8Gb (1Gx8) 3200',
                    'DDR4 8Gb (512Mx16) 3200',
                    'SLC 2Gb 256MBx8',
                    'SLC 1Gb 128MBx8',
                    'MLC 64Gb 8GBx8',
                    'MLC 32Gb 4GBx8'
                ]
            
            # US Indices order
            elif category == 'INDEX_US':
                custom_order = [
                    'S&P 500',
                    'S&P 500 PER',
                    'S&P 500 PBR',
                    'NASDAQ',
                    'NASDAQ PER',
                    'NASDAQ PBR',
                    'RUSSELL 2000',
                    'RUSSELL 2000 PER',
                    'RUSSELL 2000 PBR',
                    'VIX Index'
                ]
            
            # Commodities order
            elif category == 'COMMODITIES':
                custom_order = [
                    'Gold',
                    'Silver',
                    'Copper',
                    'WTI Crude Oil',
                    'Brent Crude Oil',
                    'Natural Gas',
                    'Wheat Futures',
                    'Sprott Physical Uranium Trust',
                    'SCFI Comprehensive Index'  # Shipping moved here
                ]
            
            # Exchange Rate order
            elif category == 'EXCHANGE RATE':
                custom_order = [
                    'Dollar Index (DXY)',
                    'KRW/USD',
                    'CNY/USD',
                    'JPY/USD',
                    'TWD/USD',
                    'EUR/USD'
                ]
            
            # Interest Rates order
            elif category == 'INTEREST RATES':
                custom_order = [
                    'US 13 Week Treasury Yield',
                    'US 5 Year Treasury Yield',
                    'US 10 Year Treasury Yield',
                    'US 30 Year Treasury Yield'
                ]

            # Wrap order
            elif category == 'Wrap':
                custom_order = [
                    '삼성 트루밸류',
                    'NH Value ESG',
                    'DB 개방형',
                    'DB 목표전환형'
                ]

            # Korea Indices order
            elif category == 'INDEX_KOREA':
                custom_order = [
                    'KOSPI',
                    'KOSPI/USD',
                    'KOSDAQ',
                    'KOSDAQ/USD'
                ]

            else:
                custom_order = None
            
            # Apply custom ordering if defined
            if custom_order:
                def sort_key(chart):
                    try:
                        return custom_order.index(chart['title'])
                    except ValueError:
                        return 999  # Put unknown items at the end
                charts = sorted(charts, key=sort_key)
            
            # Add category header
            charts_html += f"""
            <div class="category-section">
                <h2 class="category-title">{category}</h2>
                <div class="dashboard-grid">
            """
            
            # Add charts in this category
            for chart in charts:
                charts_html += f"""
                <div class="chart-card">
                    <!-- Title removed as requested (it's inside the chart now) -->
                    <!-- <h3>{chart['title']}</h3> -->
                    <a href="{chart['path']}" target="_blank">
                        <img src="{chart['path']}" alt="{chart['title']}" loading="lazy">
                    </a>
                </div>
                """
            
            charts_html += """
                </div>
            </div>
            """

    # Generate full HTML
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Market Data Dashboard</title>
    <style>
        :root {{
            --bg-color: #f8f9fa;
            --card-bg: #ffffff;
            --text-color: #333333;
            --accent-color: #4a90e2;
            --category-bg: #eeeeee;
        }}

        body {{
            font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 20px;
        }}

        header {{
            text-align: center;
            margin-bottom: 40px;
            padding: 20px;
            background-color: #000000;
            border-radius: 12px;
        }}

        h1 {{
            margin: 0;
            font-size: 2.5rem;
            color: #ffffff;
        }}

        .last-updated {{
            margin-top: 10px;
            color: #6c757d;
            font-style: italic;
        }}

        .nav-button {{
            display: inline-block;
            margin-top: 14px;
            padding: 8px 20px;
            background-color: #4a90e2;
            color: #ffffff;
            text-decoration: none;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 600;
            transition: background-color 0.2s;
        }}

        .nav-button:hover {{
            background-color: #357abd;
        }}

        .category-section {{
            margin-bottom: 50px;
        }}

        .category-title {{
            font-size: 1.8rem;
            color: #000000;
            margin-bottom: 20px;
            padding: 10px 16px;
            background-color: #e0e0e0;
            border-left: 4px solid #000000;
            border-radius: 4px;
            text-transform: uppercase;
        }}

        .dashboard-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(600px, 1fr));
            gap: 20px;
            max-width: 1600px;
            margin: 0 auto;
        }}

        @media (max-width: 768px) {{
            .dashboard-grid {{
                grid-template-columns: 1fr;
            }}
        }}

        .chart-card {{
            background-color: var(--card-bg);
            border-radius: 12px;
            padding: 15px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            transition: transform 0.2s ease;
            text-align: center;
        }}

        .chart-card:hover {{
            transform: translateY(-5px);
        }}

        .chart-card h3 {{
            margin-top: 0;
            margin-bottom: 15px;
            font-size: 1.2rem;
            color: #555555;
        }}

        .chart-card img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
        }}

        footer {{
            text-align: center;
            margin-top: 50px;
            color: #6c757d;
            font-size: 0.9rem;
        }}

        /* Portfolio Tables Styling */
        .portfolio-section {{
            margin-bottom: 40px;
        }}

        .portfolio-title {{
            font-size: 1.4rem;
            color: #333333;
            margin-bottom: 15px;
            padding-bottom: 8px;
            border-bottom: 1px solid #dee2e6;
        }}

        .table-container {{
            overflow-x: auto;
            background-color: var(--card-bg);
            border-radius: 8px;
            padding: 15px;
        }}

        .portfolio-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.95rem;
        }}

        .portfolio-table thead {{
            background-color: #e9ecef;
        }}

        .portfolio-table th {{
            padding: 12px 10px;
            text-align: left;
            font-weight: 600;
            color: #000000;
            border-bottom: 2px solid #000000;
        }}

        .portfolio-table td {{
            padding: 10px;
            border-bottom: 1px solid #dee2e6;
            color: #333333;
            text-align: center;
        }}

        .portfolio-table th {{
            text-align: center;
        }}

        .portfolio-table tbody tr:hover {{
            background-color: #f5f5f5;
        }}

        .portfolio-table .number {{
            text-align: right;
        }}

        .portfolio-table th:first-child,
        .portfolio-table td:first-child {{
            width: 50px;
            text-align: center;
        }}

        .portfolio-section-wrapper {{
            max-width: 1600px;
            margin: 0 auto;
        }}

        .portfolio-table .positive {{
            color: #cc0000;
            font-weight: 600;
        }}

        .portfolio-table .negative {{
            color: #0055cc;
            font-weight: 600;
        }}

        .portfolio-table .total-row {{
            background-color: #e9ecef;
            border-top: 2px solid #000000;
        }}

        .portfolio-table .total-row td {{
            font-weight: 600;
            padding: 12px 10px;
        }}
    </style>
</head>
<body>
    <header>
        <h1>📊 Market Data Dashboard</h1>
        <div class="last-updated">Last Updated: {now}</div>
        <a href="architecture.html" target="_blank" class="nav-button">🗂️ Workflow Architecture</a>
    </header>

    {charts_html}

    <footer>
        <p>Auto-generated by Antigravity Agent</p>
    </footer>
</body>
</html>
"""

    # Write to file
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"Dashboard generated: {OUTPUT_FILE}")

if __name__ == "__main__":
    create_dashboard()
