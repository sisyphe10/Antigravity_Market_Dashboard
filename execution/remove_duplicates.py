"""
Script to remove duplicate definitions from main files after config.py creation
"""

import re

def remove_duplicates_from_market_crawler():
    """Remove duplicate TARGET and YFINANCE_TICKERS from market_crawler.py"""
    with open('execution/market_crawler.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find and remove CSV_FILE = 'dataset.csv'
    content = re.sub(r"# === 상수 정의 ===\s*\nCSV_FILE = 'dataset.csv'\s*\n", "", content)
    
    # Find and remove TARGET_DRAM_ITEMS block
    content = re.sub(r"# DRAM 제품명\s*\nTARGET_DRAM_ITEMS = \{[^}]+\}\s*\n", "", content)
    
    # Find and remove TARGET_NAND_ITEMS block
    content = re.sub(r"# NAND 제품명\s*\nTARGET_NAND_ITEMS = \{[^}]+\}\s*\n", "", content)
    
    # Find and remove YFINANCE_TICKERS block (more complex, multi-line)
    content = re.sub(r"# yfinance 티커 목록\s*\nYFINANCE_TICKERS = \{.*?\n\}\s*\n", "", content, flags=re.DOTALL)
    
    # Clean up extra blank lines
    content = re.sub(r'\n\n\n+', '\n\n', content)
    
    with open('execution/market_crawler.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("[OK] Cleaned market_crawler.py")

def update_backfill_script():
    """Update backfill_yfinance_history.py to use config"""
    with open('execution/backfill_yfinance_history.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find import section and add config import
    new_lines = []
    import_added = False
    skip_until_line = -1
    
    for i, line in enumerate(lines):
        if i < skip_until_line:
            continue
            
        # Add config import after other imports
        if not import_added and 'import' in line and 'from' not in line and i > 5:
            new_lines.append(line)
            new_lines.append('\n# Import shared configuration\n')
            new_lines.append('from config import YFINANCE_TICKERS, CSV_FILE\n')
            new_lines.append('\n')
            import_added = True
            continue
        
        # Skip duplicate YFINANCE_TICKERS definition
        if 'YFINANCE_TICKERS = {' in line:
            # Find the end of this dict
            depth = 1
            j = i + 1
            while j < len(lines) and depth > 0:
                if '{' in lines[j]:
                    depth += 1
                if '}' in lines[j]:
                    depth -= 1
                j += 1
            skip_until_line = j
            continue
        
        # Skip CSV_FILE definition
        if "CSV_FILE = 'dataset.csv'" in line:
            continue
            
        new_lines.append(line)
    
    with open('execution/backfill_yfinance_history.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print("[OK] Updated backfill_yfinance_history.py")

def update_draw_charts():
    """Update draw_charts.py to use config"""
    with open('execution/draw_charts.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add import after other imports
    content = re.sub(
        r'(import matplotlib\.pyplot as plt.*?\n)',
        r'\1\n# Import shared configuration\nfrom config import CATEGORY_MAP\n',
        content
    )
    
    # Remove CATEGORY_MAP definition
    content = re.sub(r"# Category mapping for grouping\s*\nCATEGORY_MAP = \{[^}]+\}\s*\n", "", content)
    
    with open('execution/draw_charts.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("[OK] Updated draw_charts.py")

def update_create_dashboard():
    """Update create_dashboard.py to use config"""
    with open('execution/create_dashboard.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add import after other imports
    content = re.sub(
        r'(import csv.*?\n)',
        r'\1\n# Import shared configuration\nfrom config import CATEGORY_MAP, CSV_FILE\n',
        content
    )
    
    # Remove CSV_FILE definition
    content = re.sub(r"CSV_FILE = 'dataset\.csv'\s*\n", "", content)
    
    # Remove CATEGORY_MAP definition
    content = re.sub(r"# Category mapping \(must match draw_charts\.py\)\s*\nCATEGORY_MAP = \{[^}]+\}\s*\n", "", content)
    
    with open('execution/create_dashboard.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("[OK] Updated create_dashboard.py")

if __name__ == "__main__":
    print("Removing duplicate definitions...")
    remove_duplicates_from_market_crawler()
    update_backfill_script()
    update_draw_charts()
    update_create_dashboard()
    print("\n[SUCCESS] All files updated successfully!")
