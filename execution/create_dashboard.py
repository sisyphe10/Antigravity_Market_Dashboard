
import os
import glob
import subprocess
from datetime import datetime, timezone, timedelta
import csv
import json
from pathlib import Path
import pandas as pd

KST = timezone(timedelta(hours=9))

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

        # 포트폴리오 최근 업데이트 시각 (KST 기준)
        portfolio_mtime = os.path.getmtime(portfolio_file)
        portfolio_updated = datetime.fromtimestamp(portfolio_mtime, tz=timezone.utc).astimezone(KST).strftime('%Y-%m-%d %H:%M')

        html = ""

        for portfolio_name, stocks in portfolio_data.items():
            if portfolio_name.startswith('_'):
                continue
            # 포트폴리오별 테이블 생성
            html += f"""
            <div class="portfolio-section">
                <h3 class="portfolio-title">{portfolio_name} <span class="update-time">({portfolio_updated})</span></h3>
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
                is_today_new = stock.get('is_today_new', False)
                total_weight += weight

                if is_today_new:
                    today_return_str = "-"
                    today_color_class = ""
                elif today_return is not None:
                    today_return_str = f"{today_return:+.1f}%"
                    today_color_class = "positive" if today_return > 0 else "negative" if today_return < 0 else ""
                    weighted_return_sum += today_return * weight / 100
                    valid_returns_count += 1
                else:
                    today_return_str = "N/A"
                    today_color_class = ""

                # 기여도 포맷
                contribution = stock.get('contribution')
                if is_today_new:
                    contribution_str = "-"
                    contribution_color_class = ""
                elif contribution is not None:
                    contribution_str = f"{contribution:+.1f}"
                    contribution_color_class = "positive" if contribution > 0 else "negative" if contribution < 0 else ""
                    total_contribution += contribution
                else:
                    contribution_str = "N/A"
                    contribution_color_class = ""

                # 누적 수익률 포맷
                cumulative_return = stock.get('cumulative_return')
                if is_today_new:
                    cumulative_return_str = "-"
                    cumulative_color_class = ""
                elif cumulative_return is not None:
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

def load_kodex_data():
    """kodex_sectors.json 전체 데이터 로드"""
    try:
        if not os.path.exists('kodex_sectors.json'):
            return {}
        with open('kodex_sectors.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading kodex_sectors.json: {e}")
        return {}


def read_portfolio_sectors(stock_sector_map):
    """Wrap_NAV.xlsx NEW 시트에서 포트폴리오별 섹터 비중 계산
    종목코드 → KRX 표준 업종명 매핑 사용 (stock_sector_map)
    """
    try:
        nav_file = 'Wrap_NAV.xlsx'
        if not os.path.exists(nav_file):
            return {}

        nav_df = pd.read_excel(nav_file, sheet_name='NEW')
        nav_df['날짜'] = pd.to_datetime(nav_df['날짜'])

        portfolio_map = {
            '트루밸류': '삼성 트루밸류',
            '목표전환형': 'DB 목표전환형',
        }

        today = pd.Timestamp.now().normalize()
        portfolio_sectors = {}

        for portfolio_name, display_name in portfolio_map.items():
            df_p = nav_df[nav_df['상품명'] == portfolio_name].copy()
            if df_p.empty:
                continue

            available_dates = sorted(df_p['날짜'].unique())
            # 23:00 이전에는 당일 주문 제외 (결제는 익일 반영)
            _now = pd.Timestamp.now()
            _date_cutoff = _now.normalize() if _now.hour >= 23 else _now.normalize() - pd.Timedelta(days=1)
            prev_dates = [d for d in available_dates if d <= _date_cutoff]
            latest_date = prev_dates[-1] if prev_dates else available_dates[-1]

            df_latest = df_p[df_p['날짜'] == latest_date].copy()
            df_latest = df_latest[df_latest['비중'] > 0]

            # 종목코드로 KRX 표준 업종명 조회
            # stock_sector_map이 있으면 사용, 없으면 '업종' 컬럼 fallback
            def lookup_sector(row):
                try:
                    code = str(int(float(row['코드']))).zfill(6)
                    return stock_sector_map.get(code, None)
                except Exception:
                    return None

            if stock_sector_map:
                df_latest['_krx_sector'] = df_latest.apply(lookup_sector, axis=1)
                # 매핑 안 된 종목은 '업종' 컬럼으로 fallback
                if '업종' in df_latest.columns:
                    mask = df_latest['_krx_sector'].isna()
                    df_latest.loc[mask, '_krx_sector'] = df_latest.loc[mask, '업종'].fillna('기타')
                df_latest['_krx_sector'] = df_latest['_krx_sector'].fillna('기타')
                sector_col = '_krx_sector'
            elif '업종' in df_latest.columns:
                df_latest['업종'] = df_latest['업종'].fillna('기타').astype(str)
                sector_col = '업종'
            else:
                continue

            sector_weights = (
                df_latest.groupby(sector_col)['비중']
                .sum()
                .sort_values(ascending=False)
                .round(1)
                .to_dict()
            )

            # 섹터별 보유 종목명 (비중 상위 3개)
            name_col = next((c for c in ['종목명', '종목', '회사명'] if c in df_latest.columns), None)
            stocks_per_sector = {}
            if name_col:
                for sector, grp in df_latest.groupby(sector_col):
                    top3 = grp.nlargest(3, '비중')[name_col].tolist()
                    stocks_per_sector[str(sector)] = [str(n) for n in top3]

            portfolio_sectors[display_name] = {
                'sectors': sector_weights,
                'date': latest_date.strftime('%Y-%m-%d'),
                'stocks_per_sector': stocks_per_sector,
            }

        return portfolio_sectors

    except Exception as e:
        print(f"Error reading portfolio sectors: {e}")
        return {}


def _sector_comparison_card(portfolio_name, portfolio_info, kodex_sectors, kodex_updated, sector_1m_returns=None, bm_top_stocks=None):
    """단일 포트폴리오 vs 시장 벤치마크 섹터 비중 비교 카드 HTML (두 패널)"""
    portfolio_sectors = portfolio_info['sectors']
    portfolio_date = portfolio_info['date']
    stocks_per_sector = portfolio_info.get('stocks_per_sector', {})
    sector_1m_returns = sector_1m_returns or {}
    bm_top_stocks = bm_top_stocks or {}

    # 보유/미보유 구분
    held = {s: w for s, w in portfolio_sectors.items() if w > 0}
    not_held = {s: w for s, w in kodex_sectors.items() if s not in held}

    # ── 왼쪽: 보유 업종 (bm_1m 계산 후에 실행) ──
    # bm_1m은 아래에서 계산되므로 left_rows 생성을 지연
    _left_rows_data = []
    for sector in sorted(held, key=lambda s: held[s], reverse=True):
        p_w = held[sector]
        k_w = kodex_sectors.get(sector, 0)
        diff = p_w - k_w
        my_stocks = stocks_per_sector.get(sector, [])
        bm_stocks = bm_top_stocks.get(sector, [])
        detail_my = ', '.join(my_stocks) if my_stocks else '—'
        detail_bm = ', '.join(bm_stocks) if bm_stocks else '—'
        _left_rows_data.append((sector, p_w, k_w, diff, detail_my, detail_bm))

    # BM 전체 1M 수익률 = 섹터 수익률의 BM 비중 가중 평균
    bm_1m = sum(
        sector_1m_returns.get(s, 0) * w / 100
        for s, w in kodex_sectors.items()
        if s in sector_1m_returns
    )
    not_held_excess = {
        s: sector_1m_returns[s] - bm_1m
        for s in not_held if s in sector_1m_returns
    }
    # 보유 업종 초과 수익률 (held 섹터도 동일 공식)
    held_excess = {
        s: sector_1m_returns[s] - bm_1m
        for s in held if s in sector_1m_returns
    }

    # ── 왼쪽: 보유 업종 rows 완성 ──
    left_rows = ""
    for (sector, p_w, k_w, diff, detail_my, detail_bm) in _left_rows_data:
        ex = held_excess.get(sector)
        ex_str = f"{ex:+.1f}%" if ex is not None else "—"
        ex_cls = ('sect-over' if ex > 0 else 'sect-under') if ex is not None else 'sect-neutral'
        left_rows += f"""                    <tr>
                        <td class="sect-name">{sector}</td>
                        <td class="sect-num">{p_w:.1f}%</td>
                        <td class="sect-num">{k_w:.1f}%</td>
                        <td class="sect-diff">{diff:+.1f}%</td>
                        <td class="sect-diff {ex_cls}">{ex_str}</td>
                    </tr>
                    <tr class="sect-detail-row">
                        <td colspan="5" class="sect-detail">
                            <span class="sect-detail-mine">{detail_my}</span>
                            <span class="sect-detail-sep"> &nbsp;|&nbsp; </span>
                            <span class="sect-detail-bm">{detail_bm}</span>
                        </td>
                    </tr>
"""

    # ── 오른쪽 상단: 미보유 업종 BM 비중 상위 5 (업종 | BM 비중 | 초과 수익률) ──
    top5_bench = sorted(not_held, key=lambda s: not_held[s], reverse=True)[:5]
    bench_rows = ""
    for s in top5_bench:
        bm_s = bm_top_stocks.get(s, [])
        stocks_str = ', '.join(bm_s) if bm_s else ''
        ex = not_held_excess.get(s)
        ex_str = f"{ex:+.1f}%" if ex is not None else "—"
        ex_cls = ('sect-over' if ex > 0 else 'sect-under') if ex is not None else ''
        bench_rows += f"""                    <tr>
                        <td class="sect-name">{s}</td>
                        <td class="sect-right-val">{not_held[s]:.1f}%</td>
                        <td class="sect-right-val {ex_cls}">{ex_str}</td>
                    </tr>
"""
        if stocks_str:
            bench_rows += f"""                    <tr>
                        <td colspan="3" class="sect-right-stocks">{stocks_str}</td>
                    </tr>
"""

    # ── 오른쪽 하단: 미보유 업종 1M 초과 수익률 상위 5 (업종 | BM 비중 | 초과 수익률) ──
    top5_1m = sorted(not_held_excess, key=lambda s: not_held_excess[s], reverse=True)[:5]
    ret_rows = ""
    if top5_1m:
        for s in top5_1m:
            ex = not_held_excess[s]
            r_cls = 'sect-over' if ex > 0 else 'sect-under'
            bm_s = bm_top_stocks.get(s, [])
            stocks_str = ', '.join(bm_s) if bm_s else ''
            bm_w = not_held.get(s, kodex_sectors.get(s, 0))
            ret_rows += f"""                    <tr>
                        <td class="sect-name">{s}</td>
                        <td class="sect-right-val">{bm_w:.1f}%</td>
                        <td class="sect-right-val {r_cls}">{ex:+.1f}%</td>
                    </tr>
"""
            if stocks_str:
                ret_rows += f"""                    <tr>
                        <td colspan="3" class="sect-right-stocks">{stocks_str}</td>
                    </tr>
"""
    else:
        ret_rows = '<tr><td colspan="3" class="sect-no-data">데이터 없음</td></tr>'

    kodex_note = f" <span class='sect-kodex-date'>({kodex_updated})</span>" if kodex_updated else ""
    bm_1m_str = f"{bm_1m:+.1f}%" if sector_1m_returns else "—"

    card = f"""
        <div class="sector-card">
            <h3 class="sector-card-title">
                {portfolio_name}
                <span class="sect-portfolio-date">({portfolio_date})</span>
                <span class="sect-vs">vs</span>
                KOSPI 200 + KOSDAQ 150{kodex_note}
                <span class="sect-bm-1m">BM 1M <span class="{'sect-over' if bm_1m > 0 else 'sect-under'}">{bm_1m_str}</span></span>
            </h3>
            <div class="sector-header-bar">
                <div class="sector-legend">
                    <span class="legend-item"><span class="legend-dot portfolio-dot"></span> 포트폴리오</span>
                    <span class="legend-item"><span class="legend-dot kodex-dot"></span> 벤치마크</span>
                </div>
                <div class="sect-not-held-label">미보유</div>
            </div>
            <div class="sector-three-panel">
                <div class="sector-left-panel">
                    <h4 class="sect-panel-title">보유 업종</h4>
                    <div class="sector-table-wrap">
                        <table class="sector-table">
                            <thead>
                                <tr>
                                    <th>업종</th>
                                    <th>포트폴리오</th>
                                    <th>벤치마크</th>
                                    <th>차이</th>
                                    <th>vs BM 1M</th>
                                </tr>
                            </thead>
                            <tbody>
{left_rows}
                            </tbody>
                        </table>
                    </div>
                </div>
                <div class="sect-right-block">
                    <h4 class="sect-panel-title">BM 비중 상위 5개</h4>
                    <table class="sector-table">
                        <thead>
                            <tr><th>업종</th><th>비중</th><th>vs BM 1M</th></tr>
                        </thead>
                        <tbody>
{bench_rows}
                        </tbody>
                    </table>
                </div>
                <div class="sect-right-block">
                    <h4 class="sect-panel-title">1M 초과 수익률 상위 5개</h4>
                    <table class="sector-table">
                        <thead>
                            <tr><th>업종</th><th>비중</th><th>vs BM 1M</th></tr>
                        </thead>
                        <tbody>
{ret_rows}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
"""
    return card


def create_sector_section_html():
    """섹터 비중 비교 섹션 전체 HTML"""
    try:
        kodex_data = load_kodex_data()
        kodex_sectors = kodex_data.get('sectors', {})
        kodex_updated = kodex_data.get('updated', '')
        stock_sector_map = kodex_data.get('stock_sector_map', {})
        sector_1m_returns = kodex_data.get('sector_1m_returns', {})
        bm_top_stocks = kodex_data.get('sector_top_stocks', {})

        portfolio_sectors = read_portfolio_sectors(stock_sector_map)

        if not portfolio_sectors:
            return ""

        html = ""
        for portfolio_name, portfolio_info in portfolio_sectors.items():
            html += _sector_comparison_card(
                portfolio_name, portfolio_info, kodex_sectors, kodex_updated, sector_1m_returns, bm_top_stocks
            )

        return html

    except Exception as e:
        print(f"Error creating sector section: {e}")
        return ""


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
        wrap_html   = ""   # WRAP page: Wrap charts + Portfolio + Sector

        # Define category order for better organization
        category_order = ['Wrap', 'Portfolio', 'SECTOR', 'INDEX_KOREA', 'INDEX_US', 'EXCHANGE RATE',
                         'INTEREST RATES', 'CRYPTOCURRENCY', 'MEMORY', 'COMMODITIES']

        for category in category_order:
            # Portfolio는 차트가 아니라 테이블이므로 특별 처리
            if category == 'SECTOR':
                sector_html = create_sector_section_html()
                if sector_html:
                    wrap_html += f"""
            <div class="category-section">
                <h2 class="category-title">SECTOR WEIGHT</h2>
                <div class="portfolio-section-wrapper">
                    {sector_html}
                </div>
            </div>
            """
                continue

            if category == 'Portfolio':
                # Portfolio 테이블 HTML 생성
                portfolio_html = create_portfolio_tables_html()
                if portfolio_html:
                    wrap_html += f"""
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

            # Wrap 카테고리는 git 커밋 날짜로 날짜 표시 (git pull 시 mtime이 바뀌므로)
            if category == 'Wrap' and charts:
                try:
                    sample_file = os.path.join(CHARTS_DIR, charts[0]['filename'])
                    git_log = subprocess.run(
                        ['git', 'log', '-1', '--format=%ci', sample_file],
                        capture_output=True, text=True
                    )
                    wrap_date = git_log.stdout.strip()[:10] if git_log.stdout.strip() else datetime.now().strftime('%Y-%m-%d')
                except Exception:
                    wrap_date = datetime.now().strftime('%Y-%m-%d')
                category_label = f'WRAP <span class="category-date">({wrap_date})</span>'
            else:
                category_label = category

            # Add category header
            target = wrap_html if category == 'Wrap' else charts_html
            section = f"""
            <div class="category-section">
                <h2 class="category-title">{category_label}</h2>
                <div class="dashboard-grid">
            """
            for chart in charts:
                section += f"""
                <div class="chart-card">
                    <a href="{chart['path']}" target="_blank">
                        <img src="{chart['path']}" alt="{chart['title']}" loading="lazy">
                    </a>
                </div>
                """
            section += """
                </div>
            </div>
            """
            if category == 'Wrap':
                wrap_html += section
            else:
                charts_html += section

    # Generate full HTML
    now = datetime.now(tz=KST).strftime("%Y-%m-%d %H:%M:%S KST")
    
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
            --accent-color: #2d7a3a;
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

        .nav-group {{
            display: flex;
            gap: 8px;
            margin-top: 14px;
            flex-wrap: wrap;
        }}

        .nav-button {{
            display: inline-block;
            padding: 8px 20px;
            background-color: #2d7a3a;
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

        .update-time {{
            font-size: 0.75rem;
            font-weight: bold;
            color: #555;
        }}

        .category-date {{
            font-size: 1rem;
            font-weight: bold;
            color: #555;
            text-transform: none;
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

        /* Sector Weight Chart Styles */
        .sector-card {{
            background: var(--card-bg);
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.08);
        }}

        .sector-card-title {{
            font-size: 1.2rem;
            color: #111;
            margin: 0 0 10px 0;
            padding-bottom: 8px;
            border-bottom: 1px solid #ddd;
        }}

        .sect-portfolio-date {{
            font-size: 0.75rem;
            font-weight: 700;
            color: #555;
        }}

        .sect-kodex-date {{
            font-size: 0.75rem;
            font-weight: 700;
            color: #555;
        }}

        .sect-bm-1m {{
            font-size: 0.78rem;
            font-weight: 600;
            color: #111;
            margin-left: 10px;
        }}

        .sect-vs {{
            color: #111;
            font-weight: 400;
            font-size: 0.95rem;
            margin: 0 4px;
        }}

        .sect-note {{
            font-size: 0.75rem;
            font-weight: 400;
            color: #666;
        }}

        .sector-legend {{
            display: flex;
            align-items: center;
            gap: 16px;
            font-size: 0.82rem;
            color: #333;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 5px;
        }}

        .legend-dot {{
            width: 12px;
            height: 12px;
            border-radius: 2px;
            display: inline-block;
            flex-shrink: 0;
        }}

        .portfolio-dot {{ background: #2d7a3a; }}
        .kodex-dot {{ background: #444; }}

        .sector-table-wrap {{
            overflow-x: auto;
        }}

        .sector-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.88rem;
        }}

        .sector-table th {{
            padding: 8px 12px;
            text-align: left;
            font-weight: 600;
            color: #111;
            border-bottom: 2px solid #111;
            background: #f0f0f0;
            white-space: nowrap;
        }}

        .sector-table td {{
            padding: 5px 12px;
            border-bottom: 1px solid #eee;
            vertical-align: middle;
        }}

        .sect-name {{
            min-width: 90px;
            font-weight: 500;
            white-space: nowrap;
        }}

        .sect-num {{
            text-align: center;
            font-size: 0.85rem;
            white-space: nowrap;
            width: 64px;
        }}

        .sector-table thead th {{
            text-align: center;
        }}

        .sect-diff {{
            text-align: center;
            font-weight: 600;
            white-space: nowrap;
            width: 44px;
            min-width: 44px;
            max-width: 44px;
        }}

        .sect-over {{ color: #cc0000; }}
        .sect-under {{ color: #0055cc; }}
        .sect-neutral {{ color: #777; }}

        .sector-header-bar {{
            display: grid;
            grid-template-columns: 3fr 2fr;
            gap: 0 24px;
            align-items: center;
            margin-bottom: 10px;
        }}

        .sect-not-held-label {{
            font-size: 0.85rem;
            font-weight: 700;
            color: #111;
            text-align: center;
            padding-bottom: 4px;
            border-bottom: 1px solid #ddd;
        }}

        .sector-three-panel {{
            display: grid;
            grid-template-columns: 3fr 1fr 1fr;
            gap: 24px;
            align-items: start;
        }}

        .sect-panel-title {{
            font-size: 0.82rem;
            font-weight: 600;
            color: #111;
            text-align: center;
            margin: 0 0 8px 0;
            padding-bottom: 4px;
            border-bottom: 1px solid #ddd;
        }}

        .sect-right-val {{
            text-align: right;
            font-weight: 600;
            white-space: nowrap;
            min-width: 60px;
            font-size: 0.85rem;
            padding-right: 8px !important;
        }}

        .sect-no-data {{
            color: #aaa;
            font-size: 0.82rem;
            text-align: center;
            padding: 8px !important;
        }}

        .sect-right-stocks {{
            font-size: 0.72rem;
            color: #444;
            font-weight: 500;
            padding: 0 8px 5px 12px !important;
            border-bottom: 1px solid #eee;
        }}

        .sect-detail-row td {{
            padding: 0 12px 6px 12px !important;
            border-bottom: 1px solid #eee;
        }}

        .sect-detail {{
            font-size: 0.75rem;
            color: #888;
            line-height: 1.4;
        }}

        .sect-detail-mine {{ color: #2d7a3a; font-weight: 700; }}
        .sect-detail-bm   {{ color: #444; font-weight: 500; }}
        .sect-detail-sep  {{ color: #ccc; }}

        @media (max-width: 800px) {{
            .sector-header-bar,
            .sector-three-panel {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <header>
        <h1>📊 Market Data Dashboard</h1>
        <div class="last-updated">Last Updated: {now}</div>
        <div class="nav-group">
            <a href="wrap.html" target="_blank" class="nav-button" style="background-color:#1e40af">📈 WRAP</a>
            <a href="market_alert.html" target="_blank" class="nav-button" style="background-color:#c2410c">🚦 투자유의종목</a>
            <a href="architecture.html" target="_blank" class="nav-button">🗂️ Architecture</a>
        </div>
    </header>

    {charts_html}

    <footer>
        <p>Auto-generated by Antigravity Agent</p>
    </footer>
</body>
</html>
"""

    # Write index.html
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"Dashboard generated: {OUTPUT_FILE}")

    # ── Generate wrap.html (WRAP + Portfolio + Sector) ──
    wrap_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WRAP</title>
    <style>
        :root {{ --bg-color: #f8f9fa; --card-bg: #ffffff; --text-color: #333333; }}
        body {{ font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: var(--bg-color); color: var(--text-color); margin: 0; padding: 20px; }}
        header {{ text-align: center; margin-bottom: 40px; padding: 20px; background-color: #000000; border-radius: 12px; }}
        h1 {{ margin: 0; font-size: 2.5rem; color: #ffffff; }}
        .last-updated {{ margin-top: 10px; color: #6c757d; font-style: italic; }}
        .nav-group {{ display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; justify-content: center; }}
        .nav-button {{ display: inline-block; padding: 8px 20px; background-color: #2d7a3a; color: #ffffff; text-decoration: none; border-radius: 8px; font-size: 0.95rem; font-weight: 600; transition: background-color 0.2s; }}
        .nav-button:hover {{ background-color: #357abd; }}
        .category-section {{ margin-bottom: 50px; }}
        .category-title {{ font-size: 1.8rem; color: #000000; margin-bottom: 20px; padding: 10px 16px; background-color: #e0e0e0; border-left: 4px solid #000000; border-radius: 4px; text-transform: uppercase; }}
        .category-date {{ font-size: 1rem; font-weight: bold; color: #555; text-transform: none; }}
        .dashboard-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(600px, 1fr)); gap: 20px; max-width: 1600px; margin: 0 auto; }}
        @media (max-width: 768px) {{ .dashboard-grid {{ grid-template-columns: 1fr; }} }}
        .chart-card {{ background-color: var(--card-bg); border-radius: 12px; padding: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: transform 0.2s ease; text-align: center; }}
        .chart-card:hover {{ transform: translateY(-5px); }}
        .chart-card img {{ max-width: 100%; height: auto; border-radius: 8px; }}
        footer {{ text-align: center; margin-top: 50px; color: #6c757d; font-size: 0.9rem; }}
        /* Portfolio */
        .portfolio-section {{ margin-bottom: 40px; }}
        .portfolio-title {{ font-size: 1.4rem; color: #333; margin-bottom: 15px; padding-bottom: 8px; border-bottom: 1px solid #dee2e6; }}
        .update-time {{ font-size: 0.75rem; font-weight: bold; color: #555; }}
        .table-container {{ overflow-x: auto; background-color: var(--card-bg); border-radius: 8px; padding: 15px; }}
        .portfolio-table {{ width: 100%; border-collapse: collapse; font-size: 0.95rem; }}
        .portfolio-table thead {{ background-color: #e9ecef; }}
        .portfolio-table th {{ padding: 12px 10px; text-align: center; font-weight: 600; color: #000; border-bottom: 2px solid #000; }}
        .portfolio-table td {{ padding: 10px; border-bottom: 1px solid #dee2e6; color: #333; text-align: center; }}
        .portfolio-table tbody tr:hover {{ background-color: #f5f5f5; }}
        .portfolio-table .number {{ text-align: right; }}
        .portfolio-table th:first-child, .portfolio-table td:first-child {{ width: 50px; text-align: center; }}
        .portfolio-section-wrapper {{ max-width: 1600px; margin: 0 auto; }}
        .portfolio-table .positive {{ color: #cc0000; font-weight: 600; }}
        .portfolio-table .negative {{ color: #0055cc; font-weight: 600; }}
        .portfolio-table .total-row {{ background-color: #e9ecef; border-top: 2px solid #000; }}
        .portfolio-table .total-row td {{ font-weight: 600; padding: 12px 10px; }}
        /* Sector */
        .sector-card {{ background: var(--card-bg); border-radius: 8px; padding: 20px; margin-bottom: 30px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); }}
        .sector-card-title {{ font-size: 1.2rem; color: #111; margin: 0 0 10px 0; padding-bottom: 8px; border-bottom: 1px solid #ddd; }}
        .sect-portfolio-date, .sect-kodex-date {{ font-size: 0.75rem; font-weight: 700; color: #555; }}
        .sect-bm-1m {{ font-size: 0.78rem; font-weight: 600; color: #111; margin-left: 10px; }}
        .sect-vs {{ color: #111; font-weight: 400; font-size: 0.95rem; margin: 0 4px; }}
        .sect-note {{ font-size: 0.75rem; font-weight: 400; color: #666; }}
        .sector-legend {{ display: flex; align-items: center; gap: 16px; font-size: 0.82rem; color: #333; }}
        .legend-item {{ display: flex; align-items: center; gap: 5px; }}
        .legend-dot {{ width: 12px; height: 12px; border-radius: 2px; display: inline-block; flex-shrink: 0; }}
        .portfolio-dot {{ background: #2d7a3a; }}
        .kodex-dot {{ background: #444; }}
        .sector-table-wrap {{ overflow-x: auto; }}
        .sector-table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
        .sector-table th {{ padding: 8px 12px; text-align: left; font-weight: 600; color: #111; border-bottom: 2px solid #111; background: #f0f0f0; white-space: nowrap; }}
        .sector-table td {{ padding: 5px 12px; border-bottom: 1px solid #eee; vertical-align: middle; }}
        .sect-name {{ min-width: 90px; font-weight: 500; white-space: nowrap; }}
        .sect-num {{ text-align: center; font-size: 0.85rem; white-space: nowrap; width: 64px; }}
        .sector-table thead th {{ text-align: center; }}
        .sect-diff {{ text-align: center; font-weight: 600; white-space: nowrap; width: 44px; min-width: 44px; max-width: 44px; }}
        .sect-over {{ color: #cc0000; }}
        .sect-under {{ color: #0055cc; }}
        .sect-neutral {{ color: #777; }}
        .sector-header-bar {{ display: grid; grid-template-columns: 3fr 2fr; gap: 0 24px; align-items: center; margin-bottom: 10px; }}
        .sect-not-held-label {{ font-size: 0.85rem; font-weight: 700; color: #111; text-align: center; padding-bottom: 4px; border-bottom: 1px solid #ddd; }}
        .sector-three-panel {{ display: grid; grid-template-columns: 3fr 1fr 1fr; gap: 24px; align-items: start; }}
        .sect-panel-title {{ font-size: 0.82rem; font-weight: 600; color: #111; text-align: center; margin: 0 0 8px 0; padding-bottom: 4px; border-bottom: 1px solid #ddd; }}
        .sect-right-val {{ text-align: right; font-weight: 600; white-space: nowrap; min-width: 60px; font-size: 0.85rem; padding-right: 8px !important; }}
        .sect-no-data {{ color: #aaa; font-size: 0.82rem; text-align: center; padding: 8px !important; }}
        .sect-right-stocks {{ font-size: 0.72rem; color: #444; font-weight: 500; padding: 0 8px 5px 12px !important; border-bottom: 1px solid #eee; }}
        .sect-detail-row td {{ padding: 0 12px 6px 12px !important; border-bottom: 1px solid #eee; }}
        .sect-detail {{ font-size: 0.75rem; color: #888; line-height: 1.4; }}
        .sect-detail-mine {{ color: #2d7a3a; font-weight: 700; }}
        .sect-detail-bm {{ color: #444; font-weight: 500; }}
        .sect-detail-sep {{ color: #ccc; }}
        @media (max-width: 800px) {{ .sector-header-bar, .sector-three-panel {{ grid-template-columns: 1fr; }} }}
    </style>
</head>
<body>
    <header>
        <h1>📈 WRAP</h1>
        <div class="last-updated">Updated: {now}</div>
        <div class="nav-group">
            <a href="index.html" class="nav-button">← Dashboard</a>
        </div>
    </header>

    {wrap_html}

    <footer><p>Auto-generated by Antigravity Agent</p></footer>
</body>
</html>"""

    with open('wrap.html', 'w', encoding='utf-8') as f:
        f.write(wrap_page)
    print("WRAP page generated: wrap.html")

if __name__ == "__main__":
    create_dashboard()
