
import os
import glob
from datetime import datetime
import csv

# Version 3.0 - Added category grouping
CHARTS_DIR = 'charts'
OUTPUT_FILE = 'index.html'
CSV_FILE = 'dataset.csv'

# Category mapping (must match draw_charts.py)
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

def get_item_category(item_name):
    """Get category for an item by looking up in dataset.csv"""
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
        category_order = ['Memory', 'Cryptocurrency', 'US Indices', 'Market Indices', 
                         'Commodities', 'Foreign Exchange', 'Interest Rates', 'Shipping', 'Other']
        
        for category in category_order:
            if category not in charts_by_category:
                continue
                
            charts = charts_by_category[category]
            
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
                    <h3>{chart['title']}</h3>
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
            --bg-color: #1a1a1a;
            --card-bg: #2d2d2d;
            --text-color: #e0e0e0;
            --accent-color: #4a90e2;
            --category-bg: #252525;
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
            padding: 20px 0;
            border-bottom: 1px solid #333;
        }}

        h1 {{
            margin: 0;
            font-size: 2.5rem;
            color: var(--text-color);
        }}

        .last-updated {{
            margin-top: 10px;
            color: #888;
            font-style: italic;
        }}

        .category-section {{
            margin-bottom: 50px;
        }}

        .category-title {{
            font-size: 1.8rem;
            color: var(--accent-color);
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid var(--accent-color);
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
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
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
            color: #ccc;
        }}

        .chart-card img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
        }}

        footer {{
            text-align: center;
            margin-top: 50px;
            color: #666;
            font-size: 0.9rem;
        }}
    </style>
</head>
<body>
    <header>
        <h1>📊 Market Data Dashboard</h1>
        <div class="last-updated">Last Updated: {now}</div>
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
