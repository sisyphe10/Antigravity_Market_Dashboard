
import os
import glob
import subprocess
from datetime import datetime, timezone, timedelta
import csv
import json
import html as _html
from pathlib import Path
import pandas as pd

KST = timezone(timedelta(hours=9))

# Import shared configuration
from config import CATEGORY_MAP, CSV_FILE

# Version 3.0 - Added category grouping
CHARTS_DIR = 'charts'
OUTPUT_FILE = 'market.html'

# ── Top navigation (shared across all pages) ──────────────────────────────
# Main tabs: WRAP / Market (dropdown) / Architecture
# Market dropdown children: Market / 투자유의종목 / Universe / SEIBro / Featured / ETF
# Each entry: (key, href, label, children) — children is list of (sub_key, sub_href, sub_label) or None
TOP_NAV_MAIN = [
    ('wrap',         'wrap.html',          'WRAP',         [
        ('wrap_dashboard',    'wrap.html#dashboard',    'Dashboard'),
        ('wrap_contribution', 'wrap.html#contribution', '기여도'),
        ('wrap_disclosures',  'wrap.html#disclosures',  '공시'),
        ('wrap_order',        'wrap.html#order',        'Order'),
        ('wrap_fee',          'wrap.html#fee',          '수수료'),
    ]),
    ('market',       'market.html',        'Market',       [
        ('market',        'market.html',        'Index'),
        ('universe',      'universe.html',      'Universe'),
        ('featured',      'featured.html',      'Featured'),
        ('market_alert',  'market_alert.html',  '투자유의종목'),
        ('etf',           'etf.html',           'ETF'),
        ('seibro',        'seibro.html',        'SEIBro'),
    ]),
    ('architecture', 'architecture.html',  'Architecture', None),
]

# Standard Pretendard font stack (use everywhere)
PRETENDARD_LINK = '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">'
PRETENDARD_STACK = "'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif"

TOP_NAV_CSS = """
.topnav { background: #fff; border-bottom: 1px solid #e5e7eb; position: sticky; top: 0; z-index: 100; }
.topnav-inner { max-width: 1400px; margin: 0 auto; padding: 0 28px; display: flex; align-items: center; height: 72px; gap: 32px; }
.topnav-brand { font-size: 1.3rem; font-weight: 800; letter-spacing: 1.5px; color: #111; white-space: nowrap; text-decoration: none; font-family: PRETENDARD_STACK_PLACEHOLDER; }
.topnav-brand:hover { color: #2d7a3a; }
.topnav-tabs { display: flex; gap: 12px; flex: 1; align-items: center; }
.topnav-item { position: relative; }
.topnav-tab { box-sizing: border-box; min-width: 180px; justify-content: center; padding: 10px 24px; display: inline-flex; align-items: center; gap: 6px; color: #444; text-decoration: none; font-size: 1rem; font-weight: 600; border: 1.5px solid #d1d5db; border-radius: 999px; white-space: nowrap; background: #fff; transition: all 0.15s; font-family: PRETENDARD_STACK_PLACEHOLDER; cursor: pointer; }
.topnav-tab:hover { color: #111; border-color: #2d7a3a; background: #f0f7f2; }
.topnav-tab.active { color: #fff; border-color: #2d7a3a; background: #2d7a3a; }
.topnav-tab .caret { font-size: 0.7rem; opacity: 0.7; }
.topnav-dropdown { box-sizing: border-box; position: absolute; top: calc(100% + 8px); left: 0; min-width: 180px; width: 100%; background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.10); padding: 6px; opacity: 0; visibility: hidden; transform: translateY(-4px); transition: opacity 0.15s, transform 0.15s, visibility 0.15s; z-index: 200; }
.topnav-item:hover .topnav-dropdown,
.topnav-item:focus-within .topnav-dropdown { opacity: 1; visibility: visible; transform: translateY(0); }
.topnav-sub { display: block; padding: 9px 14px; color: #333; text-decoration: none; font-size: 0.9rem; font-weight: 500; border-radius: 8px; white-space: nowrap; text-align: center; font-family: PRETENDARD_STACK_PLACEHOLDER; }
.topnav-sub:hover { background: #f3f4f6; color: #111; }
.topnav-sub.active { background: #f0f7f2; color: #2d7a3a; font-weight: 700; }
@media (max-width: 800px) {
    .topnav-inner { padding: 0 12px; gap: 12px; height: 52px; }
    .topnav-brand { font-size: 0.95rem; }
    .topnav-tab { padding: 6px 14px; font-size: 0.85rem; }
    .topnav-tabs { gap: 6px; }
}

/* Left sidebar — used only on Market-group pages. Sits ABOVE the topnav so its top corner doubles as the AoE brand badge. */
.sidebar { position: fixed; top: 0; left: 0; bottom: 0; width: 200px; padding: 144px 10px 18px 10px; background: #fff; border-right: 1px solid #e5e7eb; overflow-y: auto; z-index: 150; box-sizing: border-box; }
.sidebar-brand { position: absolute; top: 0; left: 0; right: 0; height: 72px; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; font-weight: 800; letter-spacing: 2px; color: #1a1a1a; border-bottom: 1px solid #e5e7eb; background: #fff; text-decoration: none; font-family: PRETENDARD_STACK_PLACEHOLDER; }
.sidebar-brand:hover { color: #2d7a3a; }
.sidebar-link { display: block; padding: 12px 11px; margin-bottom: 7px; color: #444; text-decoration: none; font-size: 0.94rem; font-weight: 600; border-radius: 999px; border: 1.5px solid transparent; transition: all 0.12s; font-family: PRETENDARD_STACK_PLACEHOLDER; text-align: center; }
.sidebar-link:hover { background: #f0f7f2; color: #2d7a3a; border-color: #2d7a3a; }
.sidebar-link.active { background: transparent; color: #2d7a3a; border-color: #2d7a3a; }
/* Override per-page body styles so all sidebar pages align identically next to the sidebar */
.has-sidebar { padding-left: 224px !important; padding-right: 24px !important; padding-top: 0 !important; padding-bottom: 24px !important; max-width: none !important; margin: 0 !important; }
.has-sidebar .topnav { margin-left: -224px; margin-right: -24px; }
.has-sidebar .topnav-inner { padding-left: 228px; }
@media (max-width: 900px) {
    .sidebar { display: none; }
    .has-sidebar { padding-left: 24px !important; }
    .has-sidebar .topnav { margin-left: -24px; margin-right: -24px; }
    .has-sidebar .topnav-inner { padding-left: 12px; }
}
""".replace('PRETENDARD_STACK_PLACEHOLDER', PRETENDARD_STACK)


def _resolve_main_key(active):
    """Given an active page key, return the main tab key it belongs to."""
    for main_key, _, _, children in TOP_NAV_MAIN:
        if main_key == active:
            return main_key
        if children:
            for ck, _, _ in children:
                if ck == active:
                    return main_key
    return ''


def is_market_group(active):
    """True if the given page key belongs to the Market group (has sidebar)."""
    return _resolve_main_key(active) == 'market'


def body_class(active=''):
    """Return body class attribute for pages that need a left sidebar."""
    return ' class="has-sidebar"' if is_market_group(active) else ''


def sidebar_html(active=''):
    """Render the left sidebar for Market group pages. Returns '' for others."""
    if not is_market_group(active):
        return ''
    children = None
    for key, _, _, ch in TOP_NAV_MAIN:
        if key == 'market':
            children = ch
            break
    if not children:
        return ''
    links = ''.join(
        f'<a href="{href}" class="sidebar-link{" active" if k == active else ""}">{label}</a>'
        for k, href, label in children
    )
    return f'<aside class="sidebar"><a href="index.html" class="sidebar-brand">AoE</a>{links}</aside>'


def wrap_sidebar_html():
    """Render the WRAP-specific sidebar (Dashboard / 공시 / Order / 수수료, JS tab switcher)."""
    items = [
        ('dashboard',    'Dashboard'),
        ('contribution', '기여도'),
        ('disclosures',  '공시'),
        ('order',        'Order'),
        ('fee',          '수수료'),
    ]
    links = ''.join(
        f'<a href="#" onclick="wrapSwitchTab(\'{tab}\');return false;" '
        f'data-wrap-tab="{tab}" '
        f'class="sidebar-link{" active" if tab == "dashboard" else ""}">{label}</a>'
        for tab, label in items
    )
    return f'<aside class="sidebar"><a href="index.html" class="sidebar-brand">AoE</a>{links}</aside>'


def top_nav_html(active=''):
    """Render the shared top navigation. `active` matches a page key
    (e.g. 'market', 'wrap', 'universe', 'architecture')."""
    main_active = _resolve_main_key(active)
    parts = []
    for key, href, label, children in TOP_NAV_MAIN:
        cls = 'topnav-tab active' if key == main_active else 'topnav-tab'
        tab_html = f'<a href="{href}" class="{cls}">{label}</a>'
        if children:
            sub_links = ''.join(
                f'<a href="{ch_href}" class="topnav-sub{" active" if ch_key == active else ""}">{ch_label}</a>'
                for ch_key, ch_href, ch_label in children
            )
            tab_html += f'<div class="topnav-dropdown">{sub_links}</div>'
        parts.append(f'<div class="topnav-item">{tab_html}</div>')
    return (
        '<nav class="topnav"><div class="topnav-inner">'
        '<div class="topnav-tabs">' + ''.join(parts) + '</div>'
        '</div></nav>'
    )

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
                <h3 class="portfolio-title">{portfolio_name}</h3>
                <div class="table-container">
                    <table class="portfolio-table holdings-table" style="table-layout:fixed;">
                        <colgroup>
                            <col style="width:3.5%"><col style="width:6.5%"><col style="width:11%"><col style="width:10%"><col style="width:9%"><col style="width:7%"><col style="width:8%"><col style="width:7%"><col style="width:8.5%"><col style="width:8.5%"><col style="width:8%"><col style="width:7%"><col style="width:6%">
                        </colgroup>
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
                                <th style="border-left:2px solid #000;">현재가</th>
                                <th>ATH</th>
                                <th>DD</th>
                                <th>RSI</th>
                            </tr>
                        </thead>
                        <tbody>
            """

            # 합계 계산용 변수
            total_weight = 0
            weighted_return_sum = 0
            total_contribution = 0
            valid_returns_count = 0

            # 표시 비중 = weight_prev(D-1). 당일 finalize된 주문은 다음 거래일부터 반영.
            # (평소엔 weight_prev == weight. weight_prev 키 없으면 구버전 → weight로 fallback)
            def _disp_w(s):
                wp = s.get('weight_prev')
                return (s.get('weight', 0) or 0) if wp is None else wp
            disp_stocks = [s for s in stocks if (_disp_w(s) or 0) > 0]

            # 각 종목 행 추가
            for idx, stock in enumerate(disp_stocks, 1):
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
                weight = _disp_w(stock)
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

                # 현재가, ATH, DD
                current_price = stock.get('current_price')
                ath_price = stock.get('ath_price')
                dd = stock.get('dd')
                current_price_str = f"{current_price:,.0f}" if current_price is not None else "-"
                ath_price_str = f"{ath_price:,.0f}" if ath_price is not None else "-"
                if dd is not None:
                    dd_str = f"{dd:.1f}%"
                    dd_color_class = "negative" if dd < -20 else ""
                else:
                    dd_str = "-"
                    dd_color_class = ""

                # RSI: 편입 이후 종목 수익률 − 동일 기간 시장 지수 수익률 (%p). 양수 = 시장 대비 초과.
                rsi = stock.get('rsi')
                if rsi is not None:
                    rsi_str = f"{rsi:+.1f}%"
                    rsi_color_class = "positive" if rsi > 0 else "negative" if rsi < 0 else ""
                else:
                    rsi_str = "-"
                    rsi_color_class = ""

                html += f"""
                            <tr>
                                <td>{idx}</td>
                                <td>{stock['code']}</td>
                                <td>{stock['name']}</td>
                                <td>{stock['sector']}</td>
                                <td>{market_cap_str}</td>
                                <td>{weight:g}%</td>
                                <td class="{today_color_class}">{today_return_str}</td>
                                <td class="{contribution_color_class}">{contribution_str}</td>
                                <td class="{cumulative_color_class}">{cumulative_return_str}</td>
                                <td style="border-left:2px solid #000;">{current_price_str}</td>
                                <td>{ath_price_str}</td>
                                <td class="{dd_color_class}">{dd_str}</td>
                                <td class="{rsi_color_class}">{rsi_str}</td>
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
                                <td style="border-left:2px solid #000;">-</td>
                                <td>-</td>
                                <td>-</td>
                                <td>-</td>
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
        return 'Memory'

    # Special handling for S&P 500 related items (should be in US Indices)
    # Handle all variations: "S&P 500", "S_P_500", "S P 500"
    if 'S&P 500' in item_name or 'S_P_500' in item_name or 'S P 500' in item_name:
        return 'INDEX_US'

    # Special handling for Uranium ETF (should be in Commodities)
    if 'Uranium' in item_name or 'URA' in item_name:
        return 'COMMODITIES'

    # KRX GOLD / ETS
    if 'KRX' in item_name and ('GOLD' in item_name or 'ETS' in item_name):
        return 'COMMODITIES'

    # Special handling for Wrap portfolios
    wrap_keywords = ['트루밸류', '삼성 트루밸류', 'Value ESG', 'NH Value ESG',
                     '개방형', 'DB 개방형',
                     '목표전환형 4호', 'NH 목표전환형 4호',
                     '목표전환형 5차', 'DB 목표전환형 5차']
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
        }

        today = pd.Timestamp.now().normalize()
        portfolio_sectors = {}

        for portfolio_name, display_name in portfolio_map.items():
            df_p = nav_df[nav_df['상품명'] == portfolio_name].copy()
            if df_p.empty:
                continue

            available_dates = sorted(df_p['날짜'].unique())
            # NEW 시트 가장 최근 날짜 사용 (사용자가 최종 저장한 시점에 즉시 반영)
            from datetime import timezone, timedelta as _td
            _today_kst = pd.Timestamp.now(tz=timezone(_td(hours=9))).normalize().tz_localize(None)
            past_or_today = [d for d in available_dates if d <= _today_kst]
            latest_date = past_or_today[-1] if past_or_today else available_dates[-1]

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

    bm_1m_str = f"{bm_1m:+.1f}%" if sector_1m_returns else "—"

    card = f"""
        <div class="sector-card">
            <h3 class="sector-card-title">
                {portfolio_name}
                <span class="sect-vs">vs</span>
                KOSPI 200 + KOSDAQ 150
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


def create_monthly_returns_table():
    """monthly_returns.json → 월별 수익률 테이블 HTML (한국식 색상: 양수 빨강, 음수 파랑)."""
    json_path = 'monthly_returns.json'
    if not os.path.exists(json_path):
        return ''
    try:
        with open(json_path, encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f'monthly_returns.json 로드 실패: {e}')
        return ''

    indices = data.get('indices', [])
    rows = data.get('rows', [])
    if not indices or not rows:
        return ''
    # 컬럼 표시 순서 고정 (monthly_returns.json 순서와 무관). 미정의 항목은 뒤에 보존.
    _DISPLAY_ORDER = ['KOSPI', 'KOSDAQ', 'S&P500', 'NASDAQ', 'RUSSELL', 'NIKKEI', 'TAIEX',
                      'BTC', 'ETH', 'GOLD', 'SILVER']
    indices = [x for x in _DISPLAY_ORDER if x in indices] + [x for x in indices if x not in _DISPLAY_ORDER]

    # 컬럼 너비 (비율 %, 표 width와 무관하게 자동 스케일 — 표 1000px):
    #   연도/월 각 6.6667% (=60/900), 인덱스 11개 각 7.8788% (=780/11/900). 합 100%.
    YEAR_MONTH_COL_W = f'{60 / 900 * 100:.4f}%'
    IDX_COL_W = f'{780 / 11 / 900 * 100:.4f}%'

    def col_width_for(name):
        return YEAR_MONTH_COL_W if name in ('연도', '월') else IDX_COL_W
    # 그룹 구분선 분리:
    #   DARK   = 월↔KOSPI (시점 vs 데이터 경계, 기존 유지)
    #   HEAVY  = KOSDAQ↔S&P500(한국↔해외주식), TAIEX↔BTC(주식↔크립토), ETH↔GOLD(크립토↔금속) (자산군 경계, 더 진하게)
    #   NO_RIGHT = 연도 (연도↔월 사이 구분선 제거)
    DARK_AFTER = {'월'}
    HEAVY_AFTER = {'KOSDAQ', 'TAIEX', 'ETH'}
    NO_RIGHT = {'연도'}

    # border-collapse:separate 모드 — 셀마다 독립 테두리 (right + bottom만)
    LIGHT = '1px solid #e5e7eb'           # 가로선 (행 사이)
    LIGHT_VERT = '1px solid #6b7280'      # 일반 세로선 (gray-500)
    DARK = '1.5px solid #374151'          # 기존 그룹 구분 (gray-700)
    DARK_HEAVY = '2px solid #1f2937'      # 강조 그룹 구분 + 외곽 (gray-800)

    def right_border_for(name):
        if name in NO_RIGHT: return 'none'
        if name in HEAVY_AFTER: return DARK_HEAVY
        if name in DARK_AFTER: return DARK
        return LIGHT_VERT

    def cell_borders(name, bottom_style=LIGHT, is_header=False):
        return f'border-right:{right_border_for(name)};border-bottom:{bottom_style};'

    def th_style_for(name):
        return (f'padding:8px 6px;background:#f3f4f6;font-weight:700;text-align:center;'
                f'width:{col_width_for(name)};{cell_borders(name, True)}')

    head_cells = f'<th style="{th_style_for("연도")}">연도</th>'
    head_cells += f'<th style="{th_style_for("월")}">월</th>'
    for name in indices:
        head_cells += f'<th style="{th_style_for(name)}">{_html.escape(name)}</th>'

    def color_bg(pct):
        abs_pct = abs(pct)
        if pct > 0:
            sign = '+'
            bg = '#ffe8e8' if abs_pct <= 5 else ('#ffb8b8' if abs_pct <= 10 else '#ff7a7a')
        elif pct < 0:
            sign = ''
            bg = '#e8edff' if abs_pct <= 5 else ('#b8c5ff' if abs_pct <= 10 else '#7a90ff')
        else:
            sign = ''
            bg = 'transparent'
        return sign, bg

    # YTD 행 (현재 연도 누적 수익률 = 최근 종가 / 작년 12월 종가 - 1)
    # fetch JSON에 ytd 필드가 있으면 사용, 없으면 rows에서 (1+r1)*(1+r2)*...-1 로 계산
    ytd_returns = (data.get('ytd') or {}).get('returns', {})
    if not ytd_returns and rows:
        current_year = max((r.get('year') for r in rows if r.get('year') is not None), default=None)
        if current_year is not None:
            ytd_returns = {}
            for name in indices:
                cumul = 1.0
                has_data = False
                for r in rows:
                    if r.get('year') == current_year:
                        v = r.get('returns', {}).get(name)
                        if v is not None:
                            cumul *= (1 + v)
                            has_data = True
                ytd_returns[name] = round(cumul - 1, 6) if has_data else None
    has_ytd = bool(ytd_returns)

    body_rows_html = ''
    n_rows = len(rows)

    def make_ytd_row(returns_map, bottom_style):
        """'- | YTD | ...' 강조 행 (연간/누적 수익률, border-top=DARK)."""
        def cb(name):
            return f'border-top:{DARK};border-right:{right_border_for(name)};border-bottom:{bottom_style};'
        c = f'<td style="padding:6px 12px;text-align:center;font-weight:700;{cb("연도")}">-</td>'
        c += f'<td style="padding:6px 12px;text-align:center;font-weight:700;{cb("월")}">YTD</td>'
        for name in indices:
            v = returns_map.get(name)
            b = cb(name)
            if v is None:
                c += f'<td style="padding:6px 12px;text-align:center;{b}">&nbsp;</td>'
            else:
                pct = v * 100
                sign, bg = color_bg(pct)
                c += (f'<td style="padding:6px 12px;text-align:center;font-weight:700;background:{bg};'
                      f'color:#000;font-variant-numeric:tabular-nums;{b}">{sign}{pct:.1f}%</td>')
        return f'<tr>{c}</tr>\n'

    def annual_returns_for(year):
        """그 해 월수익률 복리 누적 = 연간 수익률 (= 12월/전년12월 - 1)."""
        res = {}
        for name in indices:
            cumul, has = 1.0, False
            for rr in rows:
                if rr.get('year') == year:
                    v = rr.get('returns', {}).get(name)
                    if v is not None:
                        cumul *= (1 + v)
                        has = True
            res[name] = (cumul - 1) if has else None
        return res

    for i, r in enumerate(rows):
        y = r.get('year')
        m = r.get('month')
        returns = r.get('returns', {})
        month_label = f'{m}월'
        is_last_body = (i == n_rows - 1)
        next_year_changes = (not is_last_body) and rows[i + 1].get('year') != y
        # 완료된 연도(다음 행이 다른 연도)면 그 해 12월 다음에 연간 YTD 행 삽입
        annual_after = annual_returns_for(y) if next_year_changes else None
        if annual_after is not None and not any(v is not None for v in annual_after.values()):
            annual_after = None
        if is_last_body and has_ytd:
            bottom = 'none'  # 아래 YTD 행의 border-top:DARK만 보이게
        elif annual_after is not None:
            bottom = 'none'  # 아래 연간 YTD 행의 border-top:DARK만 보이게
        elif next_year_changes:
            bottom = DARK  # 연도 경계
        else:
            bottom = LIGHT
        cells = f'<td style="padding:6px 12px;text-align:center;font-variant-numeric:tabular-nums;{cell_borders("연도", bottom)}">{y}</td>'
        cells += f'<td style="padding:6px 12px;text-align:center;font-variant-numeric:tabular-nums;{cell_borders("월", bottom)}">{month_label}</td>'
        for name in indices:
            v = returns.get(name)
            borders = cell_borders(name, bottom)
            if v is None:
                cells += f'<td style="padding:6px 12px;text-align:center;{borders}">&nbsp;</td>'
            else:
                pct = v * 100
                sign, bg = color_bg(pct)
                cells += f'<td style="padding:6px 12px;text-align:center;background:{bg};color:#000;font-variant-numeric:tabular-nums;{borders}">{sign}{pct:.1f}%</td>'
        body_rows_html += f'<tr>{cells}</tr>\n'
        if annual_after is not None:
            body_rows_html += make_ytd_row(annual_after, DARK_HEAVY)  # 연간 행 → 아래 굵은 선(2px)으로 다음 연도와 분리

    if ytd_returns:
        body_rows_html += make_ytd_row(ytd_returns, LIGHT)

    html = f"""
        <div class="category-section">
            <h2 class="category-title">MONTHLY RETURNS</h2>
            <div style="display:flex;justify-content:flex-end;width:1000px;max-width:100%;margin:0 auto 8px;">
                <button onclick="downloadElementImage('mrTableWrap','Monthly_Returns')" style="font-family:inherit;font-size:13px;font-weight:600;padding:6px 14px;background:#dc2626;color:#fff;border:none;border-radius:8px;cursor:pointer;">Download</button>
            </div>
            <div id="mrTableWrap" style="overflow-x:auto;background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.05);padding:16px;width:fit-content;max-width:100%;margin:0 auto;">
                <table style="width:1000px;max-width:100%;border-collapse:separate;border-spacing:0;font-size:14px;font-family:inherit;table-layout:fixed;margin:0 auto;border:2px solid #1f2937;box-sizing:border-box;">
                    <thead><tr>{head_cells}</tr></thead>
                    <tbody>
{body_rows_html}                    </tbody>
                </table>
            </div>
        </div>
        {_element_download_helper_js()}
"""
    return html


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


def _chart_download_helper_js():
    """차트 canvas → PNG 다운로드 (흰 배경 합성). 페이지에 여러 번 inject되어도 1회만 등록."""
    return """
        <script>
        if (typeof window.downloadChartImage !== 'function') {
            window.downloadChartImage = function(canvasId, baseName, legendId, extraCanvasId) {
                var src = document.getElementById(canvasId);
                if (!src) { console.warn('canvas not found:', canvasId); return; }
                // ── 고해상도 저장: 클릭 순간에만 차트를 DL_DPR로 재렌더 (화면 해상도는 그대로) ──
                var DL_DPR = 4;
                var _getCh = (window.Chart && Chart.getChart) ? function(t){ return Chart.getChart(t); } : function(){ return null; };
                var _mainChart = _getCh(canvasId);
                var _extraEl = extraCanvasId ? document.getElementById(extraCanvasId) : null;
                var _extraChart = (_extraEl && _extraEl.offsetParent !== null) ? _getCh(_extraEl) : null;
                var _prevMainDpr = _mainChart ? (_mainChart.options.devicePixelRatio || (window.devicePixelRatio || 1)) : null;
                var _prevExtraDpr = _extraChart ? (_extraChart.options.devicePixelRatio || (window.devicePixelRatio || 1)) : null;
                if (_mainChart) { _mainChart.options.devicePixelRatio = DL_DPR; _mainChart.resize(); _mainChart.draw(); }
                if (_extraChart) { _extraChart.options.devicePixelRatio = DL_DPR; _extraChart.resize(); _extraChart.draw(); }
                try {
                var w = src.width, h = src.height;
                var scale = src.clientWidth ? (w / src.clientWidth) : 1;

                // 보조 캔버스(이격도 서브패널 등) — 보이는 경우에만 메인 아래에 세로 합성
                var extra = extraCanvasId ? document.getElementById(extraCanvasId) : null;
                if (extra && (extra.offsetParent === null || !extra.width)) extra = null;
                var extraH = extra ? Math.round(extra.height * (w / extra.width)) : 0;

                // 하단 범례 항목 수집 (컬러닷 + 라벨)
                var legendItems = [];
                var legendSuffix = '';
                if (legendId) {
                    var legendEl = document.getElementById(legendId);
                    if (legendEl) {
                        legendEl.querySelectorAll(':scope > span').forEach(function(span) {
                            var dot = span.querySelector('span[style*="background"]');
                            var text = (span.textContent || '').trim();
                            if (dot) {
                                legendItems.push({ color: dot.style.background || dot.style.backgroundColor || '#888', text: text });
                            } else if (text) {
                                legendSuffix = text;  // 예: "/ USD"
                            }
                        });
                    }
                }

                var legendH = legendItems.length ? Math.round(44 * scale) : 0;
                var tmp = document.createElement('canvas');
                tmp.width = w; tmp.height = h + extraH + legendH;
                var ctx = tmp.getContext('2d');
                ctx.fillStyle = '#ffffff';
                ctx.fillRect(0, 0, tmp.width, tmp.height);
                ctx.drawImage(src, 0, 0);
                if (extra) ctx.drawImage(extra, 0, h, w, extraH);

                if (legendItems.length) {
                    var fontPx = Math.round(13 * scale);
                    var fontItem = fontPx + "px Pretendard, system-ui, sans-serif";
                    var fontSuffix = '600 ' + fontPx + "px Pretendard, system-ui, sans-serif";
                    ctx.textBaseline = 'middle';
                    var dotR = Math.round(5 * scale);
                    var gapDotText = Math.round(7 * scale);
                    var gapItems = Math.round(18 * scale);
                    var suffixGap = Math.round(6 * scale);
                    var totalW = 0;
                    ctx.font = fontItem;
                    legendItems.forEach(function(it, i) {
                        totalW += dotR * 2 + gapDotText + ctx.measureText(it.text).width;
                        if (i < legendItems.length - 1) totalW += gapItems;
                    });
                    if (legendSuffix) { ctx.font = fontSuffix; totalW += suffixGap + ctx.measureText(legendSuffix).width; }
                    var x = Math.max(Math.round((w - totalW) / 2), Math.round(10 * scale));
                    var y = h + extraH + Math.round(legendH / 2);
                    ctx.font = fontItem;
                    legendItems.forEach(function(it, i) {
                        ctx.beginPath();
                        ctx.fillStyle = it.color;
                        ctx.arc(x + dotR, y, dotR, 0, Math.PI * 2);
                        ctx.fill();
                        x += dotR * 2 + gapDotText;
                        ctx.fillStyle = '#222';
                        ctx.fillText(it.text, x, y);
                        x += ctx.measureText(it.text).width;
                        if (i < legendItems.length - 1) x += gapItems;
                    });
                    if (legendSuffix) {
                        x += suffixGap;
                        ctx.font = fontSuffix;
                        ctx.fillStyle = '#555';
                        ctx.fillText(legendSuffix, x, y);
                    }
                }
                var d = new Date();
                var pad = function(n){return n<10?'0'+n:''+n;};
                var stamp = d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate());
                var a = document.createElement('a');
                a.href = tmp.toDataURL('image/png');
                a.download = (baseName || 'chart') + '_' + stamp + '.png';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                } finally {
                    if (_mainChart) { _mainChart.options.devicePixelRatio = _prevMainDpr; _mainChart.resize(); _mainChart.draw(); }
                    if (_extraChart) { _extraChart.options.devicePixelRatio = _prevExtraDpr; _extraChart.resize(); _extraChart.draw(); }
                }
            };
        }
        </script>
    """


def _element_download_helper_js():
    """DOM 요소(테이블 등) → PNG 다운로드 (html2canvas). 페이지에 여러 번 inject되어도 1회만 등록."""
    return """
        <script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
        <script>
        if (typeof window.downloadElementImage !== 'function') {
            window.downloadElementImage = function(elementId, baseName) {
                var el = document.getElementById(elementId);
                if (!el) { console.warn('element not found:', elementId); return; }
                if (typeof html2canvas !== 'function') { alert('이미지 라이브러리 로딩 중입니다. 잠시 후 다시 시도해주세요.'); return; }
                html2canvas(el, { scale: 2, backgroundColor: '#ffffff', scrollX: 0, scrollY: -window.scrollY }).then(function(canvas) {
                    var d = new Date();
                    var pad = function(n){ return n<10 ? '0'+n : ''+n; };
                    var stamp = d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate());
                    var a = document.createElement('a');
                    a.href = canvas.toDataURL('image/png');
                    a.download = (baseName || 'table') + '_' + stamp + '.png';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                });
            };
        }
        </script>
    """


def _build_indices_chart_section(category_label='Indices'):
    """글로벌 지수 동적 비교 차트 (KOSPI/KOSDAQ/NIKKEI/TSEC/S&P500/NASDAQ/RUSSELL 2000).
    좌 사이드바 시리즈 토글 + 우 Chart.js 라인. Local/USD 모드 토글로 통화 환산 보기.
    WRAP CHART 패턴(_build_wrap_chart_section)과 동일한 UX."""
    try:
        df = pd.read_csv(CSV_FILE, encoding='utf-8-sig')
        df['날짜'] = pd.to_datetime(df['날짜'])
        df['가격'] = pd.to_numeric(df['가격'].astype(str).str.replace(',', ''), errors='coerce')

        # 시리즈 정의: display name, local 컬럼, USD 컬럼, 색
        series_config = [
            {'display': 'KOSPI',         'local': 'KOSPI',         'usd': 'KOSPI/USD',    'color': '#000000'},
            {'display': 'KOSDAQ',        'local': 'KOSDAQ',        'usd': 'KOSDAQ/USD',   'color': '#666666'},
            {'display': 'NIKKEI',        'local': 'NIKKEI',        'usd': 'NIKKEI/USD',   'color': '#DC2626'},
            {'display': 'TSEC',          'local': 'TSEC',          'usd': 'TSEC/USD',     'color': '#1976D2'},
            {'display': 'S&P 500',       'local': 'S&P 500',       'usd': 'S&P 500',      'color': '#2E7D32'},
            {'display': 'NASDAQ',        'local': 'NASDAQ',        'usd': 'NASDAQ',       'color': '#7B1FA2'},
            {'display': 'RUSSELL 2000',  'local': 'RUSSELL 2000',  'usd': 'RUSSELL 2000', 'color': '#F57C00'},
        ]

        # 최근 6개월 범위
        latest = df['날짜'].max()
        start = latest - timedelta(days=180)
        df = df[(df['날짜'] >= start) & (df['날짜'] <= latest)]

        # 모든 시리즈를 wide table로 결합 (날짜 인덱스)
        all_names = set()
        for s in series_config:
            all_names.add(s['local'])
            all_names.add(s['usd'])
        sub = df[df['제품명'].isin(all_names)].copy()
        sub = sub.drop_duplicates(subset=['날짜', '제품명'], keep='last')
        wide = sub.pivot(index='날짜', columns='제품명', values='가격').sort_index()

        # 거래일 합집합으로 dates 정렬 (값이 모두 NaN인 row는 제외)
        wide = wide.dropna(how='all')
        dates = [d.strftime('%Y-%m-%d') for d in wide.index]

        # JSON export: { dates, local: {시리즈: [...]}, usd: {시리즈: [...]}, colors: {...} }
        local_data = {}
        usd_data = {}
        colors = {}
        for s in series_config:
            colors[s['display']] = s['color']
            if s['local'] in wide.columns:
                local_data[s['display']] = [
                    None if pd.isna(v) else round(float(v), 4) for v in wide[s['local']].tolist()
                ]
            else:
                local_data[s['display']] = [None] * len(dates)
            if s['usd'] in wide.columns:
                usd_data[s['display']] = [
                    None if pd.isna(v) else round(float(v), 4) for v in wide[s['usd']].tolist()
                ]
            else:
                usd_data[s['display']] = [None] * len(dates)

        export = {
            'dates': dates,
            'local': local_data,
            'usd': usd_data,
        }
        export_json = json.dumps(export, ensure_ascii=False)
        colors_json = json.dumps(colors, ensure_ascii=False)

        # 좌측 시리즈 리스트 행
        rows_html = ''
        defaults_active = {'KOSPI', 'KOSDAQ', 'S&P 500', 'NASDAQ'}
        for s in series_config:
            display = s['display']
            color = s['color']
            active = ' active' if display in defaults_active else ''
            rows_html += (
                f'<tr class="idx-chart-item{active}" data-series="{display}" '
                f'onclick="toggleIdxSeries(this)">'
                f'<td style="width:12px;padding:0;text-align:center;vertical-align:middle;">'
                f'<div class="idx-color-bar" style="display:inline-block;width:4px;height:18px;background:{color};border-radius:2px;vertical-align:middle;"></div></td>'
                f'<td>{display}</td></tr>\n'
            )
        mode_html = (
            '<style>'
            '.idx-mode-btn{font-family:inherit;font-size:12px;font-weight:600;padding:4px 14px;'
            'border:1px solid #d1d5db;border-radius:6px;background:#f3f4f6;color:#444;cursor:pointer;transition:all 0.15s;}'
            '.idx-mode-btn.active{background:#1e3a8a;color:#fff;border-color:#1e3a8a;}'
            '</style>'
            '<div style="display:flex;gap:4px;margin-bottom:8px;">'
            '<button class="idx-mode-btn active" data-mode="local" onclick="switchIdxMode(this)">Local</button>'
            '<button class="idx-mode-btn" data-mode="usd" onclick="switchIdxMode(this)">USD</button>'
            '</div>'
        )
        list_html = mode_html + '<style>.idx-chart-item:not(.active) .idx-color-bar{visibility:hidden;}</style>' + f'<table class="portfolio-table" style="max-width:500px;margin:0 auto;"><tbody>{rows_html}</tbody></table>'

        ytd_start = '2025-12-30'
        first_date = ytd_start if dates and dates[0] <= ytd_start else (dates[0] if dates else '')
        last_date = dates[-1] if dates else ''

        js_code = """
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script>Chart.defaults.font.family = "'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif"; Chart.defaults.devicePixelRatio = 2 * (window.devicePixelRatio || 1); Chart.defaults.elements.line.borderJoinStyle = 'round'; Chart.defaults.elements.line.borderCapStyle = 'round';</script>
        <script>function formatDateInput(el){var v=el.value.replace(/[^0-9]/g,'');if(v.length===8){el.value=v.slice(0,4)+'-'+v.slice(4,6)+'-'+v.slice(6,8);}}</script>
        <script>
        (function() {
            var idxData = IDX_DATA_PLACEHOLDER;
            var idxColors = IDX_COLORS_PLACEHOLDER;
            var idxChart = null;
            var idxMode = 'local';

            // 십자선(crosshair) — 세로선은 가장 가까운 날짜(index)에 스냅, 가로선은 커서 위치.
            // cmbCrosshairPlugin(DATA 차트)과 동일 스타일의 단일 차트 버전.
            var idxHoverState = { idx: null, yPx: null };
            // 스냅된 날짜의 툴팁(데이터값) 표시.
            // tooltip.setActiveElements가 내부에서 tooltip.update까지 수행하므로 이후 draw()만 하면 됨.
            function idxSyncTooltip(chart, idx) {
                if (!chart || !chart.tooltip) return;
                var els = [];
                if (idx !== null) {
                    chart.data.datasets.forEach(function(ds, di) {
                        var v = ds.data[idx];
                        if (v !== null && v !== undefined) els.push({ datasetIndex: di, index: idx });
                    });
                }
                var area = chart.chartArea;
                var pos = { x: 0, y: 0 };
                if (els.length && area) {
                    pos.x = chart.scales.x.getPixelForValue(idx);
                    pos.y = (area.top + area.bottom) / 2;
                }
                chart.tooltip.setActiveElements(els, pos);
                if (chart.setActiveElements) chart.setActiveElements(els);
            }
            var idxCrosshairPlugin = {
                id: 'idxCrosshair',
                afterEvent: function(chart, args) {
                    var e = args.event;
                    var area = chart.chartArea;
                    if (!area) return;
                    var inside = e.x !== null && e.y !== null &&
                        e.x >= area.left && e.x <= area.right && e.y >= area.top && e.y <= area.bottom;
                    if (e.type === 'mouseout' || !inside) {
                        if (idxHoverState.idx !== null) {
                            idxHoverState.idx = null;
                            idxSyncTooltip(chart, null);
                            args.changed = true;
                            chart.draw();
                        }
                        return;
                    }
                    if (e.type !== 'mousemove') return;
                    var idx = Math.round(chart.scales.x.getValueForPixel(e.x));
                    var maxIdx = chart.data.labels.length - 1;
                    if (idx < 0) idx = 0;
                    if (idx > maxIdx) idx = maxIdx;
                    // 약한 마그넷: 현재 날짜(idx)의 데이터 점이 커서에서 12px 이내면 가로선을 그 점에 스냅
                    var yPx = e.y;
                    var snapRadius = 12;
                    var bestDist = null;
                    chart.data.datasets.forEach(function(ds, di) {
                        var v = ds.data[idx];
                        if (v === null || v === undefined) return;
                        var meta = chart.getDatasetMeta(di);
                        if (meta.hidden || !meta.data[idx]) return;
                        var py = meta.data[idx].y;
                        if (py === null || py === undefined || isNaN(py)) return;
                        var dist = Math.abs(py - e.y);
                        if (dist <= snapRadius && (bestDist === null || dist < bestDist)) {
                            bestDist = dist;
                            yPx = py;
                        }
                    });
                    var moved = idxHoverState.idx !== idx;
                    idxHoverState.idx = idx;
                    idxHoverState.yPx = yPx;
                    args.changed = true;
                    if (moved) idxSyncTooltip(chart, idx);
                    chart.draw();
                },
                afterDraw: function(chart) {
                    if (idxHoverState.idx === null) return;
                    var area = chart.chartArea;
                    var xs = chart.scales.x;
                    if (!area || !xs) return;
                    var xPx = xs.getPixelForValue(idxHoverState.idx);
                    if (xPx < area.left || xPx > area.right) return;
                    var ctx = chart.ctx;
                    ctx.save();
                    ctx.strokeStyle = '#888';
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    ctx.moveTo(xPx, area.top);
                    ctx.lineTo(xPx, area.bottom);
                    ctx.stroke();
                    if (idxHoverState.yPx >= area.top && idxHoverState.yPx <= area.bottom) {
                        ctx.beginPath();
                        ctx.moveTo(area.left, idxHoverState.yPx);
                        ctx.lineTo(area.right, idxHoverState.yPx);
                        ctx.stroke();
                    }
                    ctx.restore();
                }
            };

            function buildIdxChart() {
                var selected = [];
                document.querySelectorAll('.idx-chart-item.active').forEach(function(el){ selected.push(el.getAttribute('data-series')); });
                var startDate = document.getElementById('idxStartDate').value;
                var endDate = document.getElementById('idxEndDate').value;
                var sourceSet = (idxMode === 'usd') ? idxData.usd : idxData.local;

                // Pass 1: 시리즈별 (date,value) 추출
                var perSeries = [];
                selected.forEach(function(name) {
                    var arr = sourceSet[name];
                    if (!arr) return;
                    var lookup = {};
                    var firstDate = '';
                    for (var i = 0; i < idxData.dates.length; i++) {
                        var d = idxData.dates[i];
                        if (d >= startDate && d <= endDate && arr[i] !== null && arr[i] !== undefined) {
                            lookup[d] = arr[i];
                            if (!firstDate) firstDate = d;
                        }
                    }
                    if (!firstDate) return;
                    perSeries.push({ name: name, lookup: lookup, firstDate: firstDate });
                });

                // Pass 2: 공통 시작일 = 가장 늦은 첫 데이터일자 (선택 시리즈 모두에 데이터가 있는 첫 날)
                var commonStart = '';
                perSeries.forEach(function(s) {
                    if (s.firstDate > commonStart) commonStart = s.firstDate;
                });

                // Pass 3: 공통 날짜축 = commonStart 이후 모든 선택 시리즈의 거래일 합집합
                // 시장별 휴일이 달라도 한 차트에서 같은 x축으로 정렬됨
                var dateSet = {};
                perSeries.forEach(function(s) {
                    Object.keys(s.lookup).forEach(function(d) {
                        if (d >= commonStart) dateSet[d] = true;
                    });
                });
                var commonDates = Object.keys(dateSet).sort();

                // Pass 4: 각 시리즈를 공통축에 정렬 + forward-fill (휴장일은 직전 종가 유지)
                // base = 시리즈의 commonStart 시점 값. 거기 데이터가 없으면 ffill 후 첫 값.
                var datasets = [];
                perSeries.forEach(function(s) {
                    var aligned = [];
                    var lastVal = null;
                    for (var i = 0; i < commonDates.length; i++) {
                        var d = commonDates[i];
                        if (s.lookup.hasOwnProperty(d)) lastVal = s.lookup[d];
                        aligned.push(lastVal);
                    }
                    var base = null;
                    for (var j = 0; j < aligned.length; j++) {
                        if (aligned[j] !== null) { base = aligned[j]; break; }
                    }
                    if (base === null) return;
                    var pct = aligned.map(function(v) {
                        if (v === null) return null;
                        return Math.round((v / base - 1) * 10000) / 100;
                    });
                    datasets.push({
                        label: s.name,
                        data: pct,
                        borderColor: idxColors[s.name] || '#888',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.3,
                        spanGaps: true
                    });
                });

                var endLabelPlugin = {
                    id: 'idxEndLabels',
                    afterDatasetsDraw: function(chart) {
                        var ctx = chart.ctx;
                        chart.data.datasets.forEach(function(ds, i) {
                            var meta = chart.getDatasetMeta(i);
                            if (meta.hidden) return;
                            // 끝에 null이 있을 수 있음 — 마지막 non-null 값/포인트 찾기
                            var lastIdx = -1;
                            for (var k = ds.data.length - 1; k >= 0; k--) {
                                if (ds.data[k] !== null && ds.data[k] !== undefined) { lastIdx = k; break; }
                            }
                            if (lastIdx < 0) return;
                            var last = meta.data[lastIdx];
                            if (!last) return;
                            var val = ds.data[lastIdx];
                            var rounded = Math.sign(val) * Math.round(Math.abs(val));
                            var sign = rounded >= 0 ? '+' : '';
                            ctx.save();
                            ctx.font = 'bold 12px sans-serif';
                            ctx.fillStyle = ds.borderColor;
                            ctx.textBaseline = 'middle';
                            ctx.fillText(sign + rounded + '%', last.x + 6, last.y);
                            ctx.restore();
                        });
                    }
                };

                // 하단 컬러닷 범례 (선택된 시리즈만)
                var legendEl = document.getElementById('idxChartLegend');
                if (legendEl) {
                    var legendHTML = datasets.map(function(ds) {
                        var c = ds.borderColor;
                        return '<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px;font-size:13px;">' +
                            '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + c + ';"></span>' +
                            ds.label + '</span>';
                    }).join('');
                    if (idxMode === 'usd' && datasets.length > 0) {
                        legendHTML += '<span style="font-size:13px;color:#555;font-weight:600;margin-left:4px;">/ USD</span>';
                    }
                    legendEl.innerHTML = legendHTML;
                }

                if (idxChart) idxChart.destroy();
                idxChart = new Chart(document.getElementById('idxDynamicChart'), {
                    type: 'line',
                    data: { labels: commonDates, datasets: datasets },
                    plugins: [endLabelPlugin, idxCrosshairPlugin],
                    options: {
                        responsive: true, maintainAspectRatio: false,
                        layout: { padding: { right: 60 } },
                        interaction: { mode: 'index', intersect: false },
                        plugins: {
                            legend: { display: false },
                            // animation:false — 스냅 툴팁이 draw()만으로 위치 갱신되도록 (애니메이션 속성이면 제자리에 멈춤)
                            tooltip: { animation: false, callbacks: { label: function(ctx){ return ctx.dataset.label + ': ' + (ctx.parsed.y === null ? '-' : ctx.parsed.y.toFixed(1) + '%'); } } }
                        },
                        scales: {
                            x: { type: 'category', display: datasets.length > 0, ticks: { maxTicksLimit: 6, callback: function(val){ var d = this.getLabelForValue(val); if(!d) return ''; return d.slice(2,4) + '/' + d.slice(5,7); }, maxRotation: 0, font: { size: 11 }, color: '#000' }, grid: { color: '#eee', display: true }, border: { color: '#000' } },
                            y: { ticks: { callback: function(v){ return v + '%'; }, font: { size: 11 }, color: '#000' }, grid: { color: '#eee' }, border: { color: '#000' } }
                        }
                    }
                });
            }

            window.toggleIdxSeries = function(el) { el.classList.toggle('active'); buildIdxChart(); };
            window.updateIdxChart = buildIdxChart;
            window.switchIdxMode = function(el) {
                document.querySelectorAll('.idx-mode-btn').forEach(function(b){ b.classList.remove('active'); });
                el.classList.add('active');
                idxMode = el.getAttribute('data-mode');
                buildIdxChart();
            };
            buildIdxChart();
        })();
        </script>
        """.replace('IDX_DATA_PLACEHOLDER', export_json).replace('IDX_COLORS_PLACEHOLDER', colors_json)

        return f"""
        <div class="category-section">
            <h2 class="category-title">{category_label}</h2>
            <div style="display:flex;gap:16px;align-items:flex-start;max-width:1800px;margin:0 auto;justify-content:center;">
                <div style="min-width:180px;">{list_html}</div>
                <div style="width:1000px;">
                    <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;font-size:13px;">
                        <span style="color:#555;font-weight:600;">기간</span>
                        <input type="text" id="idxStartDate" value="{first_date}" onchange="formatDateInput(this);updateIdxChart()" style="font-family:inherit;font-size:13px;padding:4px 8px;border:1px solid #d1d5db;border-radius:6px;background:#f9fafb;color:#222;width:110px;text-align:center;" placeholder="YYYY-MM-DD">
                        <span style="color:#888;">~</span>
                        <input type="text" id="idxEndDate" value="{last_date}" onchange="formatDateInput(this);updateIdxChart()" style="font-family:inherit;font-size:13px;padding:4px 8px;border:1px solid #d1d5db;border-radius:6px;background:#f9fafb;color:#222;width:110px;text-align:center;" placeholder="YYYY-MM-DD">
                        <button onclick="downloadChartImage('idxDynamicChart','AoE_Indice','idxChartLegend')" style="margin-left:auto;font-family:inherit;font-size:13px;font-weight:600;padding:6px 14px;background:#dc2626;color:#fff;border:none;border-radius:8px;cursor:pointer;">Download</button>
                    </div>
                    <div id="idxChartCard" style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 4px 6px rgba(0,0,0,0.1);">
                        <div style="position:relative;height:500px;">
                            <canvas id="idxDynamicChart"></canvas>
                        </div>
                        <div id="idxChartLegend" style="margin-top:12px;text-align:center;color:#222;"></div>
                    </div>
                </div>
            </div>
        </div>
        {js_code}
        {_chart_download_helper_js()}
        """
    except Exception as e:
        print(f"Error building indices chart section: {e}")
        import traceback; traceback.print_exc()
        return ""


def _build_combined_chart_section():
    """7개 카테고리(INDEX_KOREA/INDEX_US/EXCHANGE RATE/INTEREST RATES/CRYPTOCURRENCY/Memory/COMMODITIES)
    를 단일 동적 Chart.js 차트로 통합. 좌 사이드바는 카테고리 그룹 헤더 + 토글 항목,
    우는 % change 정규화 라인 차트 (Indices 패턴)."""
    try:
        groups = [
            {'label': 'INDEX_KOREA', 'series': [
                {'display': 'KOSPI',              'csv': 'KOSPI',              'color': '#000000', 'default': True},
                {'display': 'KOSPI/USD',          'csv': 'KOSPI/USD',          'color': '#444444'},
                {'display': 'KOSPI Market Cap',   'csv': 'KOSPI Market Cap',   'color': '#888888'},
                {'display': 'KOSDAQ',             'csv': 'KOSDAQ',             'color': '#1976D2'},
                {'display': 'KOSDAQ/USD',         'csv': 'KOSDAQ/USD',         'color': '#5294D8'},
                {'display': 'KOSDAQ Market Cap',  'csv': 'KOSDAQ Market Cap',  'color': '#7BAEDF'},
                # 증시 유동성 (금투협 KOFIA → dataset.csv DEPOSIT). DATA 일반 차트로 개별 시리즈 표시.
                {'display': '고객예탁금',         'csv': '고객예탁금',         'color': '#2E7D32'},
                {'display': '신용잔고',           'csv': '신용잔고',           'color': '#C2185B'},
            ]},
            {'label': 'INDEX_US', 'series': [
                {'display': 'S&P 500',            'csv': 'S&P 500',            'color': '#2E7D32'},
                {'display': 'S&P 500 PER',        'csv': 'S&P 500 PER',        'color': '#4CAF50'},
                {'display': 'S&P 500 PBR',        'csv': 'S&P 500 PBR',        'color': '#81C784'},
                {'display': 'NASDAQ',             'csv': 'NASDAQ',             'color': '#7B1FA2'},
                {'display': 'NASDAQ PER',         'csv': 'NASDAQ PER',         'color': '#9C27B0'},
                {'display': 'NASDAQ PBR',         'csv': 'NASDAQ PBR',         'color': '#BA68C8'},
                {'display': 'RUSSELL 2000',       'csv': 'RUSSELL 2000',       'color': '#F57C00'},
                {'display': 'RUSSELL 2000 PER',   'csv': 'RUSSELL 2000 PER',   'color': '#FF9800'},
                {'display': 'RUSSELL 2000 PBR',   'csv': 'RUSSELL 2000 PBR',   'color': '#FFB74D'},
                {'display': 'VIX Index',          'csv': 'VIX Index',          'color': '#D32F2F'},
            ]},
            {'label': 'EXCHANGE RATE', 'series': [
                {'display': 'Dollar Index (DXY)', 'csv': 'Dollar Index (DXY)', 'color': '#1565C0'},
                {'display': 'KRW/USD',            'csv': 'KRW/USD',            'color': '#0277BD'},
                {'display': 'CNY/USD',            'csv': 'CNY/USD',            'color': '#0288D1'},
                {'display': 'JPY/USD',            'csv': 'JPY/USD',            'color': '#039BE5'},
                {'display': 'TWD/USD',            'csv': 'TWD/USD',            'color': '#03A9F4'},
                {'display': 'EUR/USD',            'csv': 'EUR/USD',            'color': '#29B6F6'},
                # 미국 달러인덱스 광의 (FRED 일별, fetch_fred_data.py)
                {'display': '달러인덱스 (광의)',  'csv': '달러인덱스 (광의)',  'color': '#4FC3F7'},
            ]},
            {'label': 'INTEREST RATES', 'series': [
                {'display': 'US03M', 'csv': 'US 13 Week Treasury Yield', 'color': '#B71C1C'},
                {'display': 'US02Y', 'csv': 'US 2 Year Treasury Yield',  'color': '#D50000'},
                {'display': 'US05Y', 'csv': 'US 5 Year Treasury Yield',  'color': '#C62828'},
                {'display': 'US10Y', 'csv': 'US 10 Year Treasury Yield', 'color': '#D32F2F'},
                {'display': 'US30Y', 'csv': 'US 30 Year Treasury Yield', 'color': '#E53935'},
                # 한국 금리 (ECOS 일별, fetch_ecos_data.py)
                {'display': '한국 기준금리',          'csv': '한국 기준금리',          'color': '#7F0000'},
                {'display': '국고채 3년',             'csv': '국고채 3년',             'color': '#8E0000'},
                {'display': '국고채 10년',            'csv': '국고채 10년',            'color': '#9A0007'},
                {'display': 'CD 91일',                'csv': 'CD 91일',                'color': '#BF360C'},
                {'display': 'CP 91일',                'csv': 'CP 91일',                'color': '#D84315'},
                {'display': '회사채 3년 AA-',         'csv': '회사채 3년 AA-',         'color': '#E64A19'},
                {'display': '장단기 스프레드 10Y-3Y', 'csv': '장단기 스프레드 10Y-3Y', 'color': '#F4511E'},
                {'display': '신용 스프레드 AA-3Y',    'csv': '신용 스프레드 AA-3Y',    'color': '#FF7043'},
                # 미국 금리·스프레드 (FRED 일별, fetch_fred_data.py)
                {'display': '미 기준금리 상단',        'csv': '미 기준금리 상단',        'color': '#1A237E'},
                {'display': '미 장단기 금리차 10Y-2Y', 'csv': '미 장단기 금리차 10Y-2Y', 'color': '#283593'},
                {'display': '미 장단기 금리차 10Y-3M', 'csv': '미 장단기 금리차 10Y-3M', 'color': '#303F9F'},
                {'display': '미 BBB 스프레드',         'csv': '미 BBB 스프레드',         'color': '#3949AB'},
                {'display': '미 하이일드 스프레드',    'csv': '미 하이일드 스프레드',    'color': '#3F51B5'},
                {'display': '미 실질금리 10Y',         'csv': '미 실질금리 10Y',         'color': '#5C6BC0'},
                {'display': '미 기대인플레 BEI 10Y',   'csv': '미 기대인플레 BEI 10Y',   'color': '#7986CB'},
                {'display': '미 기대인플레 5Y5Y',      'csv': '미 기대인플레 5Y5Y',      'color': '#9FA8DA'},
                {'display': 'SOFR',                    'csv': 'SOFR',                    'color': '#304FFE'},
            ]},
            {'label': 'MACRO KOREA', 'series': [
                # ECOS 월별 매크로 (5년 임베드 창, fetch_ecos_data.py)
                {'display': 'CPI 전년동월비',        'csv': 'CPI 전년동월비',        'color': '#004D40'},
                {'display': 'PPI 전년동월비',        'csv': 'PPI 전년동월비',        'color': '#00695C'},
                {'display': '기대인플레이션 1년',    'csv': '기대인플레이션 1년',    'color': '#00796B'},
                {'display': 'M2 전년동월비',         'csv': 'M2 전년동월비',         'color': '#00897B'},
                {'display': 'BSI 업황실적 (전산업)', 'csv': 'BSI 업황실적 (전산업)', 'color': '#006064'},
                {'display': 'BSI 업황전망 (전산업)', 'csv': 'BSI 업황전망 (전산업)', 'color': '#00838F'},
                {'display': '소비자심리지수 CSI',    'csv': '소비자심리지수 CSI',    'color': '#0097A7'},
                {'display': '경제심리지수 ESI',      'csv': '경제심리지수 ESI',      'color': '#00ACC1'},
                {'display': '선행지수 순환변동치',   'csv': '선행지수 순환변동치',   'color': '#26A69A'},
                {'display': '제조업 가동률',         'csv': '제조업 가동률',         'color': '#26C6DA'},
                {'display': '수출금액 전년동월비',   'csv': '수출금액 전년동월비',   'color': '#00BFA5'},
                {'display': '경상수지',              'csv': '경상수지',              'color': '#4DB6AC'},
                {'display': '외환보유액',            'csv': '외환보유액',            'color': '#4DD0E1'},
            ]},
            {'label': 'MACRO US', 'series': [
                # FRED 미국 매크로 (fetch_fred_data.py; 월·분기 FRED_MACRO는 5년 임베드 창,
                # 일·주간 FRED_RATE는 기존 365일 창)
                {'display': '미 역레포 잔고',               'csv': '미 역레포 잔고',               'color': '#0D47A1'},
                {'display': '미 신규 실업수당청구',         'csv': '미 신규 실업수당청구',         'color': '#1A5BB8'},
                {'display': '미 연속 실업수당청구',         'csv': '미 연속 실업수당청구',         'color': '#2A6BC9'},
                {'display': '미 금융여건지수 NFCI',         'csv': '미 금융여건지수 NFCI',         'color': '#3A7BD5'},
                {'display': '미 연준 총자산',               'csv': '미 연준 총자산',               'color': '#4A8BE0'},
                {'display': '미 CPI 전년동월비',            'csv': '미 CPI 전년동월비',            'color': '#5B99E8'},
                {'display': '미 근원 CPI 전년동월비',       'csv': '미 근원 CPI 전년동월비',       'color': '#6CA7EF'},
                {'display': '미 근원 PCE 전년동월비',       'csv': '미 근원 PCE 전년동월비',       'color': '#7DB5F4'},
                {'display': '미 PPI 전년동월비',            'csv': '미 PPI 전년동월비',            'color': '#8FC2F8'},
                {'display': '미 시간당임금 전년동월비',     'csv': '미 시간당임금 전년동월비',     'color': '#A0CFFB'},
                {'display': '미 비농업고용 증감',           'csv': '미 비농업고용 증감',           'color': '#263238'},
                {'display': '미 실업률',                    'csv': '미 실업률',                    'color': '#37474F'},
                {'display': '미 JOLTS 구인',                'csv': '미 JOLTS 구인',                'color': '#455A64'},
                {'display': '미 소매판매 전년동월비',       'csv': '미 소매판매 전년동월비',       'color': '#546E7A'},
                {'display': '미 산업생산 전년동월비',       'csv': '미 산업생산 전년동월비',       'color': '#607D8B'},
                {'display': '미 근원자본재 수주 전년동월비','csv': '미 근원자본재 수주 전년동월비','color': '#78909C'},
                {'display': '미시간 소비자심리',            'csv': '미시간 소비자심리',            'color': '#90A4AE'},
                {'display': '미 Sahm Rule 침체지표',        'csv': '미 Sahm Rule 침체지표',        'color': '#A7B8C2'},
                {'display': '미 GDPNow 성장률',             'csv': '미 GDPNow 성장률',             'color': '#BCC9D1'},
            ]},
            {'label': 'CREDIT & HOUSING', 'series': [
                # ECOS 신용·부동산 (5년 임베드 창, fetch_ecos_data.py)
                {'display': '은행 대출금리 (신규취급)',       'csv': '은행 대출금리 (신규취급)',       'color': '#3E2723'},
                {'display': '은행 저축성수신금리 (신규취급)', 'csv': '은행 저축성수신금리 (신규취급)', 'color': '#4E342E'},
                {'display': '예대금리차 (신규)',              'csv': '예대금리차 (신규)',              'color': '#5D4037'},
                {'display': '가계대출 잔액',                  'csv': '가계대출 잔액',                  'color': '#6D4C41'},
                {'display': '가계신용',                       'csv': '가계신용',                       'color': '#795548'},
                {'display': '은행 대출태도지수 (종합)',       'csv': '은행 대출태도지수 (종합)',       'color': '#8D6E63'},
                {'display': '은행 신용위험지수 (종합)',       'csv': '은행 신용위험지수 (종합)',       'color': '#A1887F'},
                {'display': '은행 대출수요지수 (종합)',       'csv': '은행 대출수요지수 (종합)',       'color': '#BCAAA4'},
                {'display': 'KB 주택매매지수 (전국)',         'csv': 'KB 주택매매지수 (전국)',         'color': '#827717'},
                {'display': 'KB 아파트지수 (서울)',           'csv': 'KB 아파트지수 (서울)',           'color': '#9E9D24'},
                {'display': '아파트 실거래지수 (전국)',       'csv': '아파트 실거래지수 (전국)',       'color': '#AFB42B'},
                {'display': '아파트 실거래지수 (서울)',       'csv': '아파트 실거래지수 (서울)',       'color': '#C0CA33'},
            ]},
            {'label': 'CREDIT & HOUSING US', 'series': [
                # FRED 미국 신용·부동산 (fetch_fred_data.py; 월·분기 FRED_SECTOR는 5년 임베드 창,
                # 모기지(주간 FRED_RATE)는 기존 365일 창)
                {'display': '미 모기지 30년 금리',                'csv': '미 모기지 30년 금리',                'color': '#5D2E0D'},
                {'display': '미 주택착공',                        'csv': '미 주택착공',                        'color': '#7A3E11'},
                {'display': '미 건축허가',                        'csv': '미 건축허가',                        'color': '#965016'},
                {'display': '미 기존주택판매',                    'csv': '미 기존주택판매',                    'color': '#B3621B'},
                {'display': '미 케이스-실러 주택가격 전년동월비', 'csv': '미 케이스-실러 주택가격 전년동월비', 'color': '#CF7420'},
                {'display': '미 은행 대출태도 (C&I)',             'csv': '미 은행 대출태도 (C&I)',             'color': '#E98A2B'},
            ]},
            {'label': 'CRYPTOCURRENCY', 'series': [
                {'display': 'BTC', 'csv': 'BTC', 'color': '#F7931A'},
                {'display': 'ETH', 'csv': 'ETH', 'color': '#627EEA'},
                {'display': 'BNB', 'csv': 'BNB', 'color': '#F0B90B'},
                {'display': 'XRP', 'csv': 'XRP', 'color': '#23292F'},
                {'display': 'SOL', 'csv': 'SOL', 'color': '#9945FF'},
            ]},
            {'label': 'COMMODITIES', 'series': [
                {'display': 'Gold',                       'csv': 'Gold',                       'color': '#FFD700'},
                {'display': 'KRX GOLD Trading Volume',    'csv': 'KRX GOLD Trading Volume',    'color': '#DAA520'},
                {'display': 'Silver',                     'csv': 'Silver',                     'color': '#C0C0C0'},
                {'display': 'Copper',                     'csv': 'Copper',                     'color': '#B87333'},
                {'display': 'WTI',                        'csv': 'WTI Crude Oil',              'color': '#2C3E50'},
                {'display': 'Brent',                      'csv': 'Brent Crude Oil',            'color': '#34495E'},
                {'display': 'Natural Gas',                'csv': 'Natural Gas',                'color': '#16A085'},
                {'display': 'Wheat',                      'csv': 'Wheat',                      'color': '#F39C12'},
                {'display': 'Uranium',                    'csv': 'Uranium',                    'color': '#27AE60'},
                {'display': 'Lithium Carbonate',          'csv': 'Lithium Carbonate',          'color': '#8E44AD'},
                {'display': 'Lithium Hydroxide',          'csv': 'Lithium Hydroxide',          'color': '#9B59B6'},
                {'display': 'Poly Silicon',               'csv': 'Poly Silicon',               'color': '#3498DB'},
                {'display': 'SCFI',                       'csv': 'SCFI Comprehensive Index',   'color': '#E74C3C'},
                {'display': 'KRX ETS (KAU25)',            'csv': 'KRX ETS (KAU25)',            'color': '#1ABC9C'},
                {'display': 'KRX ETS Trading Volume',     'csv': 'KRX ETS Trading Volume',     'color': '#117A65'},
                {'display': 'SMP',                        'csv': 'SMP',                        'color': '#2d7a3a'},
            ]},
            {'label': 'MEMORY', 'series': [
                {'display': '삼성 DDR5 소매가', 'csv': '삼성 DDR5 소매가', 'color': '#AD1457'},
                {'display': 'SK하이닉스 DDR5 소매가', 'csv': 'SK하이닉스 DDR5 소매가', 'color': '#6A1B9A'},
                {'display': 'DDR5 16Gb', 'csv': 'DDR5 16G (2Gx8) 4800/5600', 'color': '#E91E63'},
                {'display': 'DDR4 8Gb',  'csv': 'DDR4 8Gb (1Gx8) 3200',      'color': '#F48FB1'},
                {'display': 'SLC 2Gb',   'csv': 'SLC 2Gb 256MBx8',           'color': '#00897B'},
                {'display': 'SLC 1Gb',   'csv': 'SLC 1Gb 128MBx8',           'color': '#26A69A'},
                {'display': 'MLC 64Gb',  'csv': 'MLC 64Gb 8GBx8',            'color': '#4DB6AC'},
                {'display': 'MLC 32Gb',  'csv': 'MLC 32Gb 4GBx8',            'color': '#80CBC4'},
            ]},
            {'label': 'HOTELS', 'series': [
                # hotel_adr.csv의 도시별 일별 평균 ADR (모든 호텔×lead 평균)
                {'display': 'Hotel 서울', 'csv': 'Hotel 서울', 'color': '#1976D2'},
                {'display': 'Hotel 부산', 'csv': 'Hotel 부산', 'color': '#388E3C'},
                {'display': 'Hotel 제주', 'csv': 'Hotel 제주', 'color': '#F57C00'},
                {'display': 'Hotel 경주', 'csv': 'Hotel 경주', 'color': '#7B1FA2'},
            ]},
        ]

        df = pd.read_csv(CSV_FILE, encoding='utf-8-sig')
        df['날짜'] = pd.to_datetime(df['날짜'])
        df['가격'] = pd.to_numeric(df['가격'].astype(str).str.replace(',', ''), errors='coerce')

        # 단위 변환: KRX ETS/GOLD Trading Volume은 원 단위(수십~수백억 원) → 억원 단위로 환산.
        # Y축 라벨은 별도로 안 적음 (사용자 명시).
        _volume_mask = df['제품명'].isin(['KRX ETS Trading Volume', 'KRX GOLD Trading Volume'])
        df.loc[_volume_mask, '가격'] = df.loc[_volume_mask, '가격'] / 1e8

        # Hotel ADR 도시별 일별 평균을 dataset에 inject (hotel_adr.csv → 도시별 모든 호텔×lead 평균).
        # dataset.csv를 영구히 안 건드리고 차트 빌드 시점에만 append.
        hotels_by_city: dict[str, list[str]] = {}
        try:
            if os.path.exists('hotel_adr.csv'):
                hdf = pd.read_csv('hotel_adr.csv')
                hdf['date'] = pd.to_datetime(hdf['collected_at'].str[:10])
                # 도시별 일별 평균 (모든 호텔 × 모든 lead_days)
                city_avg = hdf.groupby(['date', 'city'])['price_krw'].mean().round(0).reset_index()
                city_avg['제품명'] = 'Hotel ' + city_avg['city']
                city_avg = city_avg.rename(columns={'date': '날짜', 'price_krw': '가격'})
                df = pd.concat([df, city_avg[['날짜', '제품명', '가격']]], ignore_index=True)
                # 사이드바 호버 tooltip용 — 도시별 수집 호텔 리스트 (최신 collected_at 기준)
                latest_ct = hdf['collected_at'].max()
                latest_df = hdf[hdf['collected_at'] == latest_ct]
                for city, grp in latest_df.groupby('city'):
                    hotels_by_city[city] = sorted(grp['hotel'].unique().tolist())
        except Exception as e:
            print(f"  Warning: Hotel ADR city inject 실패: {e}")

        all_csv_names = set()
        for g in groups:
            for s in g['series']:
                all_csv_names.add(s['csv'])

        latest = df['날짜'].max()
        # MA200 표시를 위해 데이터 범위 확장 (24개월: MA200은 약 280캘린더일 선행 데이터 필요.
        # 연말 YTD 화면·12개월 수동 조회에서도 MA200이 채워지려면 730일 필요)
        start = latest - timedelta(days=730)
        # ECOS/FRED 월·분기 시리즈(ECOS_MACRO/ECOS_SECTOR/FRED_MACRO/FRED_SECTOR)는
        # 포인트가 적어 5년 창 적용. FRED_RATE(일·주간)는 기존 365일 창 유지 (설계 핵심).
        # '데이터 타입'이 NaN인 빌드타임 inject 행(hotel 등)은 기존 365일 창 유지.
        long_start = latest - timedelta(days=365 * 5)
        if '데이터 타입' in df.columns:
            long_mask = df['데이터 타입'].isin(['ECOS_MACRO', 'ECOS_SECTOR', 'FRED_MACRO', 'FRED_SECTOR'])
        else:
            long_mask = pd.Series(False, index=df.index)
        df = df[(df['날짜'] <= latest)
                & ((df['날짜'] >= start) | (long_mask & (df['날짜'] >= long_start)))]

        sub = df[df['제품명'].isin(all_csv_names)].copy()
        sub = sub.drop_duplicates(subset=['날짜', '제품명'], keep='last')
        wide = sub.pivot(index='날짜', columns='제품명', values='가격').sort_index()
        wide = wide.dropna(how='all')
        dates = [d.strftime('%Y-%m-%d') for d in wide.index]

        data_export = {}
        rows_html = ''
        for g in groups:
            visible = []
            for s in g['series']:
                if s['csv'] not in wide.columns:
                    continue
                values = [
                    None if pd.isna(v) else round(float(v), 4)
                    for v in wide[s['csv']].tolist()
                ]
                if all(v is None for v in values):
                    continue
                visible.append((s, values))
            if not visible:
                continue
            last_idx = len(visible) - 1
            group_label = _html.escape(g['label'])
            # 아코디언 초기 상태: default(기본 선택) 시리즈가 있는 그룹만 펼침
            group_expanded = any(s.get('default') for s, _ in visible)
            arrow_char = '▾' if group_expanded else '▸'
            row_display = '' if group_expanded else 'display:none;'
            default_count = sum(1 for s, _ in visible if s.get('default'))
            badge_style = 'margin-left:6px;color:#0055cc;font-size:11px;'
            if default_count:
                badge_html = f'<span class="cmb-group-badge" style="{badge_style}">● {default_count}</span>'
            else:
                badge_html = f'<span class="cmb-group-badge" style="{badge_style}display:none;"></span>'
            rows_html += (
                f'<tr class="cmb-group-header" data-group="{group_label}" '
                f'onclick="toggleCmbGroup(this)">'
                f'<td style="background:#f0f0f0;font-weight:700;font-size:12px;color:#333;'
                f'padding:8px 10px;text-align:left;cursor:pointer;user-select:none;'
                f'text-transform:uppercase;letter-spacing:0.5px;'
                f'border-top:1px solid #000;border-bottom:1px solid #000;'
                f'white-space:nowrap;">'
                f'<span class="cmb-group-arrow" style="display:inline-block;width:14px;">{arrow_char}</span>'
                f'{group_label} <span style="font-weight:400;color:#888;">({len(visible)})</span>'
                f'{badge_html}</td></tr>\n'
            )
            for idx, (s, values) in enumerate(visible):
                data_export[s['display']] = values
                active = ' active' if s.get('default') else ''
                extra_border = 'border-bottom:1px solid #000;' if idx == last_idx else ''
                # Hotel {city} 시리즈에는 수집 호텔 리스트를 native tooltip(title)으로 표시
                tooltip_attr = ''
                if s['display'].startswith('Hotel '):
                    city = s['display'].replace('Hotel ', '', 1)
                    hotels = hotels_by_city.get(city, [])
                    if hotels:
                        tooltip_attr = f' title="{_html.escape(", ".join(hotels))}"'
                series_cell = (
                    f'<td class="cmb-chart-item{active}" data-series="{_html.escape(s["display"])}"{tooltip_attr} '
                    f'onclick="toggleCmbSeries(this, event)" '
                    f'style="cursor:pointer;text-align:left;padding-left:24px;position:relative;{extra_border}">'
                    f'<div class="cmb-color-bar" style="position:absolute;left:8px;top:50%;'
                    f'transform:translateY(-50%);width:4px;height:18px;'
                    f'border-radius:2px;"></div>'
                    f'{_html.escape(s["display"])}</td>'
                )
                rows_html += (
                    f'<tr class="cmb-series-row" data-group="{group_label}" '
                    f'style="{row_display}">{series_cell}</tr>\n'
                )

        export = {'dates': dates, 'data': data_export}
        # compact separators: 시리즈 92개 × 날짜 414개 기준 공백만 ~38KB 절약
        export_json = json.dumps(export, ensure_ascii=False, separators=(',', ':'))

        list_html = (
            '<style>'
            '.cmb-chart-item:not(.active) .cmb-color-bar{display:none;}'
            '.cmb-group-header td:hover{background:#e4e4e4 !important;}'
            '</style>'
            f'<table class="portfolio-table" style="max-width:500px;margin:0 auto;">'
            f'<tbody>{rows_html}</tbody></table>'
        )

        ytd_start = '2025-12-30'
        first_date = ytd_start if dates and dates[0] <= ytd_start else (dates[0] if dates else '')
        last_date = dates[-1] if dates else ''

        js_code = """
        <script>
        (function() {
            var cmbData = CMB_DATA_PLACEHOLDER;
            var cmbChart = null;
            var cmbClickOrder = [];
            var clickPalette = ['#000000','#0055cc','#cc0000','#006633','#6a0dad','#cc6600','#008080','#990066'];
            var seriesScale = { 'KOSPI Market Cap': 1e12, 'KOSDAQ Market Cap': 1e12 };

            var expandedGroups = new Set();

            // MA/이격도 토글 상태 — 시리즈 전환·기간 변경에도 유지 (새로고침 시 초기화, 기본 전부 OFF)
            var MA_DEFS = [
                { win: 20,  color: '#d32f2f' },
                { win: 60,  color: '#f57c00' },
                { win: 120, color: '#1b5e20' },
                { win: 200, color: '#1565c0' }
            ];
            var maActive = { 20: false, 60: false, 120: false, 200: false };
            var dispActive = { 20: false, 60: false, 120: false, 200: false };
            var cmbDispChart = null;

            // 십자선(crosshair) — 세로선은 메인+이격도 패널 동기(같은 날짜 index),
            // 가로선은 커서가 올라가 있는 차트에만. 두 차트가 같은 labels 배열을 공유해 x 정렬 보장.
            var cmbHoverState = { idx: null, yPx: null, activeId: null };
            // 반대편 차트에도 같은 날짜의 툴팁(데이터값) 표시.
            // tooltip.setActiveElements가 내부에서 tooltip.update까지 수행하므로 이후 draw()만 하면 됨.
            function cmbSyncTooltip(other, idx) {
                if (!other || !other.tooltip) return;
                var els = [];
                if (idx !== null) {
                    other.data.datasets.forEach(function(ds, di) {
                        var v = ds.data[idx];
                        if (v !== null && v !== undefined) els.push({ datasetIndex: di, index: idx });
                    });
                }
                var area = other.chartArea;
                var pos = { x: 0, y: 0 };
                if (els.length && area) {
                    pos.x = other.scales.x.getPixelForValue(idx);
                    pos.y = (area.top + area.bottom) / 2;
                }
                other.tooltip.setActiveElements(els, pos);
                if (other.setActiveElements) other.setActiveElements(els);
            }
            var cmbCrosshairPlugin = {
                id: 'cmbCrosshair',
                afterEvent: function(chart, args) {
                    var e = args.event;
                    var area = chart.chartArea;
                    if (!area) return;
                    var other = (chart.canvas.id === 'cmbDynamicChart') ? cmbDispChart : cmbChart;
                    var inside = e.x !== null && e.y !== null &&
                        e.x >= area.left && e.x <= area.right && e.y >= area.top && e.y <= area.bottom;
                    if (e.type === 'mouseout' || !inside) {
                        if (cmbHoverState.idx !== null) {
                            cmbHoverState.idx = null;
                            cmbHoverState.activeId = null;
                            args.changed = true;
                            if (other) {
                                cmbSyncTooltip(other, null);
                                other.draw();
                            }
                        }
                        return;
                    }
                    if (e.type !== 'mousemove') return;
                    var idx = Math.round(chart.scales.x.getValueForPixel(e.x));
                    var maxIdx = chart.data.labels.length - 1;
                    if (idx < 0) idx = 0;
                    if (idx > maxIdx) idx = maxIdx;
                    // 약한 마그넷: 현재 날짜(idx)의 데이터 점이 커서에서 12px 이내면 가로선을 그 점에 스냅
                    var yPx = e.y;
                    var snapRadius = 12;
                    var bestDist = null;
                    chart.data.datasets.forEach(function(ds, di) {
                        var v = ds.data[idx];
                        if (v === null || v === undefined) return;
                        var meta = chart.getDatasetMeta(di);
                        if (meta.hidden || !meta.data[idx]) return;
                        var py = meta.data[idx].y;
                        if (py === null || py === undefined || isNaN(py)) return;
                        var dist = Math.abs(py - e.y);
                        if (dist <= snapRadius && (bestDist === null || dist < bestDist)) {
                            bestDist = dist;
                            yPx = py;
                        }
                    });
                    var moved = cmbHoverState.idx !== idx;
                    cmbHoverState.idx = idx;
                    cmbHoverState.yPx = yPx;
                    cmbHoverState.activeId = chart.canvas.id;
                    args.changed = true;
                    if (other) {
                        if (moved) cmbSyncTooltip(other, idx);
                        other.draw();
                    }
                },
                afterDraw: function(chart) {
                    if (cmbHoverState.idx === null) return;
                    var area = chart.chartArea;
                    var xs = chart.scales.x;
                    if (!area || !xs) return;
                    var xPx = xs.getPixelForValue(cmbHoverState.idx);
                    if (xPx < area.left || xPx > area.right) return;
                    var ctx = chart.ctx;
                    ctx.save();
                    ctx.strokeStyle = '#888';
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    ctx.moveTo(xPx, area.top);
                    ctx.lineTo(xPx, area.bottom);
                    ctx.stroke();
                    if (cmbHoverState.activeId === chart.canvas.id &&
                        cmbHoverState.yPx >= area.top && cmbHoverState.yPx <= area.bottom) {
                        ctx.beginPath();
                        ctx.moveTo(area.left, cmbHoverState.yPx);
                        ctx.lineTo(area.right, cmbHoverState.yPx);
                        ctx.stroke();
                    }
                    ctx.restore();
                }
            };

            function colorForIndex(i) { return clickPalette[i % clickPalette.length]; }

            function fmtNum(v) {
                if (v === null || v === undefined) return '-';
                return Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
            }

            function cmbSearchQuery() {
                var inp = document.getElementById('cmbSeriesSearch');
                return inp ? inp.value.trim().toLowerCase() : '';
            }

            function groupOfItem(el) {
                var row = el.closest('tr');
                return row ? row.getAttribute('data-group') : null;
            }

            // 그룹 아코디언 + 검색 필터 상태를 DOM에 반영.
            // 검색 중: 매칭 시리즈만 표시 + 그룹 자동 펼침 + 매칭 0개 그룹은 헤더째 숨김.
            // 검색 비었으면: expandedGroups Set 기준으로 펼침 상태 복원.
            function refreshCmbList() {
                var q = cmbSearchQuery();
                document.querySelectorAll('.cmb-group-header').forEach(function(header) {
                    var label = header.getAttribute('data-group') || '';
                    var groupMatch = q !== '' && label.toLowerCase().indexOf(q) !== -1;
                    var anyMatch = false;
                    document.querySelectorAll('.cmb-series-row').forEach(function(row) {
                        if (row.getAttribute('data-group') !== label) return;
                        if (q !== '') {
                            var item = row.querySelector('.cmb-chart-item');
                            var name = item ? (item.getAttribute('data-series') || '').toLowerCase() : '';
                            var match = groupMatch || name.indexOf(q) !== -1;
                            row.style.display = match ? '' : 'none';
                            if (match) anyMatch = true;
                        } else {
                            row.style.display = expandedGroups.has(label) ? '' : 'none';
                        }
                    });
                    var arrow = header.querySelector('.cmb-group-arrow');
                    if (q !== '') {
                        header.style.display = anyMatch ? '' : 'none';
                        if (arrow) arrow.textContent = '▾';
                    } else {
                        header.style.display = '';
                        if (arrow) arrow.textContent = expandedGroups.has(label) ? '▾' : '▸';
                    }
                });
            }

            // 그룹 헤더 배지(● N = 그룹 내 active 시리즈 수) 재계산 — 중앙화 함수.
            // active 토글이 일어나는 모든 경로가 buildCmbChart()를 거치므로 거기서 호출.
            function updateCmbGroupBadges() {
                var counts = {};
                document.querySelectorAll('.cmb-series-row .cmb-chart-item.active').forEach(function(el) {
                    var g = groupOfItem(el);
                    if (g) counts[g] = (counts[g] || 0) + 1;
                });
                document.querySelectorAll('.cmb-group-header').forEach(function(header) {
                    var label = header.getAttribute('data-group') || '';
                    var badge = header.querySelector('.cmb-group-badge');
                    if (!badge) return;
                    var n = counts[label] || 0;
                    if (n > 0) {
                        badge.textContent = '● ' + n;
                        badge.style.display = '';
                    } else {
                        badge.textContent = '';
                        badge.style.display = 'none';
                    }
                });
            }

            function applyMarkerColors() {
                document.querySelectorAll('.cmb-chart-item').forEach(function(el) {
                    var bar = el.querySelector('.cmb-color-bar');
                    if (!bar) return;
                    var idx = cmbClickOrder.indexOf(el.getAttribute('data-series'));
                    bar.style.background = idx >= 0 ? colorForIndex(idx) : '';
                });
            }

            function buildCmbChart() {
                var activeSet = {};
                document.querySelectorAll('.cmb-chart-item.active').forEach(function(el){
                    activeSet[el.getAttribute('data-series')] = true;
                });
                cmbClickOrder = cmbClickOrder.filter(function(n){ return activeSet[n]; });
                Object.keys(activeSet).forEach(function(n){
                    if (cmbClickOrder.indexOf(n) === -1) cmbClickOrder.push(n);
                });
                var selected = cmbClickOrder.slice();
                applyMarkerColors();
                updateCmbGroupBadges();

                var startDate = document.getElementById('cmbStartDate').value;
                var endDate = document.getElementById('cmbEndDate').value;

                var perSeries = [];
                selected.forEach(function(name) {
                    var arr = cmbData.data[name];
                    if (!arr) return;
                    var lookup = {};
                    var firstDate = '';
                    for (var i = 0; i < cmbData.dates.length; i++) {
                        var d = cmbData.dates[i];
                        if (d >= startDate && d <= endDate && arr[i] !== null && arr[i] !== undefined) {
                            lookup[d] = arr[i];
                            if (!firstDate) firstDate = d;
                        }
                    }
                    if (!firstDate) return;
                    perSeries.push({ name: name, lookup: lookup, firstDate: firstDate });
                });

                var commonStart = '';
                perSeries.forEach(function(s) {
                    if (s.firstDate > commonStart) commonStart = s.firstDate;
                });

                var dateSet = {};
                perSeries.forEach(function(s) {
                    Object.keys(s.lookup).forEach(function(d) {
                        if (d >= commonStart) dateSet[d] = true;
                    });
                });
                var commonDates = Object.keys(dateSet).sort();

                var mode = perSeries.length === 1 ? 'raw1' : (perSeries.length === 2 ? 'raw2' : 'pct');

                // 단일 선택(raw1)일 때만 MA/이격도 버튼 활성 (상태 값은 보존)
                var maRow = document.getElementById('cmbMaRow');
                if (maRow) maRow.classList.toggle('cmb-ma-disabled', mode !== 'raw1');

                var datasets = [];
                var dispDatasets = [];
                perSeries.forEach(function(s, idx) {
                    var aligned = [];
                    var lastVal = null;
                    for (var i = 0; i < commonDates.length; i++) {
                        var d = commonDates[i];
                        if (s.lookup.hasOwnProperty(d)) lastVal = s.lookup[d];
                        aligned.push(lastVal);
                    }
                    var data;
                    if (mode === 'pct') {
                        var base = null;
                        for (var j = 0; j < aligned.length; j++) {
                            if (aligned[j] !== null) { base = aligned[j]; break; }
                        }
                        // base가 0/음수인 시리즈(스프레드, 경상수지, 대출태도지수 등)는
                        // % 정규화가 무의미(Infinity/부호반전) → 3개 이상 선택 시 제외
                        if (base === null || base <= 0) return;
                        data = aligned.map(function(v) {
                            if (v === null) return null;
                            return Math.round((v / base - 1) * 10000) / 100;
                        });
                    } else {
                        var scale = seriesScale[s.name] || 1;
                        data = aligned.map(function(v) {
                            if (v === null) return null;
                            var sv = v / scale;
                            return scale > 1 ? Math.round(sv) : sv;
                        });
                    }
                    var yAxisID = (mode === 'raw2' && idx === 1) ? 'y1' : 'y';
                    var clickIdx = cmbClickOrder.indexOf(s.name);
                    datasets.push({
                        label: s.name,
                        data: data,
                        borderColor: colorForIndex(clickIdx >= 0 ? clickIdx : 0),
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        borderJoinStyle: 'round',
                        borderCapStyle: 'round',
                        pointRadius: 0,
                        tension: 0.4,
                        cubicInterpolationMode: 'monotone',
                        spanGaps: true,
                        yAxisID: yAxisID
                    });

                    // 단일 선택일 때 토글된 MA / 이격도 추가
                    // 표시 윈도우만으로 MA 계산하면 긴 윈도우가 안 채워지므로,
                    // 전체 보유 데이터(24개월)로 MA를 먼저 계산한 뒤 가시 영역에 매핑한다.
                    if (mode === 'raw1') {
                        function computeMA(arr, win) {
                            var out = [];
                            for (var i = 0; i < arr.length; i++) {
                                if (i < win - 1) { out.push(null); continue; }
                                var sum = 0, cnt = 0;
                                for (var k = i - win + 1; k <= i; k++) {
                                    if (arr[k] !== null && arr[k] !== undefined) { sum += arr[k]; cnt++; }
                                }
                                out.push(cnt === win ? sum / cnt : null);
                            }
                            return out;
                        }
                        var fullArr = cmbData.data[s.name];
                        var fullDates = cmbData.dates;
                        var fullFilled = [];
                        var lvf = null;
                        for (var fi = 0; fi < fullArr.length; fi++) {
                            if (fullArr[fi] !== null && fullArr[fi] !== undefined) lvf = fullArr[fi];
                            fullFilled.push(lvf);
                        }
                        var dateIdxMap = {};
                        for (var di = 0; di < fullDates.length; di++) dateIdxMap[fullDates[di]] = di;
                        // MA도 본 라인과 같은 scale 적용 (KOSPI/KOSDAQ Market Cap은 1e12로 조 단위)
                        function scaledMA(fullMA) {
                            return commonDates.map(function(d) {
                                var ix = dateIdxMap[d];
                                if (ix === undefined) return null;
                                var v = fullMA[ix];
                                if (v === null || v === undefined) return null;
                                var sv = v / scale;
                                return scale > 1 ? Math.round(sv) : sv;
                            });
                        }
                        MA_DEFS.forEach(function(def) {
                            if (!maActive[def.win] && !dispActive[def.win]) return;
                            var fullMA = computeMA(fullFilled, def.win);
                            if (maActive[def.win]) {
                                var maVisible = scaledMA(fullMA);
                                // 전 구간 null(데이터 부족)이면 범례 유령 항목 방지를 위해 생략
                                if (maVisible.some(function(v){ return v !== null; })) datasets.push({
                                    label: 'MA' + def.win,
                                    data: maVisible,
                                    borderColor: def.color,
                                    backgroundColor: 'transparent',
                                    borderWidth: 2,
                                    borderJoinStyle: 'round',
                                    borderCapStyle: 'round',
                                    pointRadius: 0,
                                    tension: 0.4,
                                    cubicInterpolationMode: 'monotone',
                                    spanGaps: true,
                                    yAxisID: yAxisID
                                });
                            }
                            if (dispActive[def.win]) {
                                // 이격도 = 가격/MA×100 (비율이라 단위 scale 자동 소거)
                                var dispVisible = commonDates.map(function(d) {
                                    var ix = dateIdxMap[d];
                                    if (ix === undefined) return null;
                                    var ma = fullMA[ix], pv = fullFilled[ix];
                                    if (ma === null || ma === undefined || ma === 0) return null;
                                    if (pv === null || pv === undefined) return null;
                                    return Math.round(pv / ma * 10000) / 100;
                                });
                                if (dispVisible.some(function(v){ return v !== null; })) dispDatasets.push({
                                    label: '이격도' + def.win,
                                    data: dispVisible,
                                    borderColor: def.color,
                                    backgroundColor: 'transparent',
                                    borderWidth: 1.8,
                                    borderJoinStyle: 'round',
                                    borderCapStyle: 'round',
                                    pointRadius: 0,
                                    tension: 0.4,
                                    cubicInterpolationMode: 'monotone',
                                    spanGaps: true
                                });
                            }
                        });
                    }
                });

                if (mode === 'raw2') {
                    var padCount = 3;
                    for (var p = 0; p < padCount; p++) commonDates.push('');
                    datasets.forEach(function(ds) {
                        for (var q = 0; q < padCount; q++) ds.data.push(null);
                    });
                }

                var endLabelPlugin = {
                    id: 'cmbEndLabels',
                    afterDatasetsDraw: function(chart) {
                        var ctx = chart.ctx;
                        var entries = [];
                        chart.data.datasets.forEach(function(ds, i) {
                            if (ds._skipEndLabel) return;
                            var meta = chart.getDatasetMeta(i);
                            if (meta.hidden) return;
                            var lastIdx = -1;
                            for (var k = ds.data.length - 1; k >= 0; k--) {
                                if (ds.data[k] !== null && ds.data[k] !== undefined) { lastIdx = k; break; }
                            }
                            if (lastIdx < 0) return;
                            var last = meta.data[lastIdx];
                            if (!last) return;
                            var val = ds.data[lastIdx];
                            var label;
                            if (mode === 'pct') {
                                var rounded = Math.sign(val) * Math.round(Math.abs(val));
                                var sign = rounded >= 0 ? '+' : '';
                                label = sign + rounded + '%';
                            } else {
                                label = fmtNum(val);
                            }
                            entries.push({ x: last.x + 6, origY: last.y, y: last.y, label: label, color: ds.borderColor });
                        });
                        if (entries.length === 0) return;
                        // y 오름차순 정렬 후 minGap 강제 (위→아래 충돌 시 아래로 밀기)
                        entries.sort(function(a, b) { return a.origY - b.origY; });
                        var minGap = 14;
                        for (var i = 1; i < entries.length; i++) {
                            if (entries[i].y - entries[i-1].y < minGap) {
                                entries[i].y = entries[i-1].y + minGap;
                            }
                        }
                        // 차트 영역 밖으로 밀려나갔으면 위쪽으로 역보정
                        var area = chart.chartArea;
                        if (area) {
                            var maxY = area.bottom - 4;
                            for (var j = entries.length - 1; j > 0; j--) {
                                if (entries[j].y > maxY) entries[j].y = maxY;
                                if (entries[j-1].y > entries[j].y - minGap) entries[j-1].y = entries[j].y - minGap;
                            }
                        }
                        ctx.save();
                        ctx.font = 'bold 12px sans-serif';
                        ctx.textBaseline = 'middle';
                        entries.forEach(function(e) {
                            ctx.fillStyle = e.color;
                            ctx.fillText(e.label, e.x, e.y);
                        });
                        ctx.restore();
                    }
                };

                var legendEl = document.getElementById('cmbChartLegend');
                if (legendEl) {
                    var legendHTML = datasets.map(function(ds) {
                        var c = ds.borderColor;
                        // 설정 기간 변화율: pct 모드는 정규화된 값이라 last 자체가 변화율,
                        // raw 모드는 (last/first - 1)*100. 첫/마지막 non-null 값으로 계산.
                        var vals = ds.data.filter(function(v) { return v !== null && v !== undefined && !isNaN(v); });
                        var pctStr = '';
                        if (vals.length >= 2) {
                            var first = vals[0];
                            var last = vals[vals.length - 1];
                            var pct;
                            if (mode === 'pct') {
                                pct = last - first;
                            } else if (first !== 0) {
                                pct = (last / first - 1) * 100;
                            } else {
                                pct = 0;
                            }
                            pctStr = '<span>' + (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%</span>';
                        }
                        return '<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px;font-size:13px;">' +
                            '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + c + ';"></span>' +
                            ds.label + pctStr + '</span>';
                    }).join('');
                    // 이격도는 기간 변화율 대신 마지막 값 표시 (100 기준 과열/침체 지표)
                    legendHTML += dispDatasets.map(function(ds) {
                        var vals = ds.data.filter(function(v) { return v !== null && v !== undefined && !isNaN(v); });
                        var lastStr = vals.length ? '<span>' + vals[vals.length - 1].toFixed(1) + '</span>' : '';
                        return '<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px;font-size:13px;">' +
                            '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + ds.borderColor + ';"></span>' +
                            ds.label + lastStr + '</span>';
                    }).join('');
                    legendEl.innerHTML = legendHTML;
                }

                var yType = (mode === 'pct') ? 'linear' : 'logarithmic';
                var scalesConfig = {
                    x: { type: 'category', display: datasets.length > 0, ticks: { maxTicksLimit: 6, callback: function(val){ var d = this.getLabelForValue(val); if(!d) return ''; return d.slice(2,4) + '/' + d.slice(5,7); }, maxRotation: 0, font: { size: 11 }, color: '#000' }, grid: { color: '#eee', display: true }, border: { color: '#000' } },
                    y: {
                        type: yType,
                        position: 'left',
                        grace: '8%',
                        ticks: { callback: function(v){ return mode === 'pct' ? v + '%' : fmtNum(v); }, font: { size: 11 }, color: '#000' },
                        grid: { color: '#eee' },
                        border: { color: '#000' }
                    }
                };
                if (mode === 'raw2' && datasets[1]) {
                    scalesConfig.y1 = {
                        type: 'logarithmic',
                        position: 'right',
                        grace: '8%',
                        ticks: { callback: function(v){ return fmtNum(v); }, font: { size: 11 }, color: '#000' },
                        grid: { drawOnChartArea: false },
                        border: { color: '#000' }
                    };
                }

                var tooltipLabel = function(ctx) {
                    if (ctx.parsed.y === null || ctx.parsed.y === undefined) return ctx.dataset.label + ': -';
                    if (mode === 'pct') return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) + '%';
                    return ctx.dataset.label + ': ' + fmtNum(ctx.parsed.y);
                };

                if (cmbChart) cmbChart.destroy();
                cmbChart = new Chart(document.getElementById('cmbDynamicChart'), {
                    type: 'line',
                    data: { labels: commonDates, datasets: datasets },
                    plugins: [endLabelPlugin, cmbCrosshairPlugin],
                    options: {
                        responsive: true, maintainAspectRatio: false,
                        devicePixelRatio: 2 * (window.devicePixelRatio || 1),
                        layout: { padding: { right: 60 } },
                        interaction: { mode: 'index', intersect: false },
                        plugins: {
                            legend: { display: false },
                            // animation:false — 동기 툴팁이 draw()만으로 위치 갱신되도록 (애니메이션 속성이면 제자리에 멈춤)
                            tooltip: { animation: false, callbacks: { label: tooltipLabel } }
                        },
                        scales: scalesConfig
                    }
                });

                // 이격도 서브패널 — 100 기준선 점선 + 메인 y축 폭에 맞춰 x축 정렬
                var dispPanel = document.getElementById('cmbDispPanel');
                if (cmbDispChart) { cmbDispChart.destroy(); cmbDispChart = null; }
                if (dispPanel) {
                    if (dispDatasets.length > 0) {
                        dispPanel.style.display = '';
                        var disp100Plugin = {
                            id: 'cmbDisp100',
                            beforeDatasetsDraw: function(chart) {
                                var ys = chart.scales.y;
                                var area = chart.chartArea;
                                if (!ys || !area) return;
                                var y100 = ys.getPixelForValue(100);
                                if (y100 < area.top || y100 > area.bottom) return;
                                var c = chart.ctx;
                                c.save();
                                c.strokeStyle = '#999';
                                c.setLineDash([4, 4]);
                                c.lineWidth = 1;
                                c.beginPath();
                                c.moveTo(area.left, y100);
                                c.lineTo(area.right, y100);
                                c.stroke();
                                c.restore();
                            }
                        };
                        var mainYWidth = (cmbChart.scales && cmbChart.scales.y) ? cmbChart.scales.y.width : 0;
                        cmbDispChart = new Chart(document.getElementById('cmbDispChart'), {
                            type: 'line',
                            data: { labels: commonDates, datasets: dispDatasets },
                            plugins: [endLabelPlugin, disp100Plugin, cmbCrosshairPlugin],
                            options: {
                                responsive: true, maintainAspectRatio: false,
                                devicePixelRatio: 2 * (window.devicePixelRatio || 1),
                                layout: { padding: { right: 60 } },
                                interaction: { mode: 'index', intersect: false },
                                plugins: {
                                    legend: { display: false },
                                    tooltip: { animation: false, callbacks: { label: function(ctx) {
                                        if (ctx.parsed.y === null || ctx.parsed.y === undefined) return ctx.dataset.label + ': -';
                                        return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1);
                                    } } }
                                },
                                scales: {
                                    x: { type: 'category', ticks: { maxTicksLimit: 6, callback: function(val){ var d = this.getLabelForValue(val); if(!d) return ''; return d.slice(2,4) + '/' + d.slice(5,7); }, maxRotation: 0, font: { size: 11 }, color: '#000' }, grid: { color: '#eee', display: true }, border: { color: '#000' } },
                                    y: {
                                        type: 'linear',
                                        position: 'left',
                                        grace: '8%',
                                        afterFit: function(scale) { if (mainYWidth > 0) scale.width = mainYWidth; },
                                        ticks: { callback: function(v){ return fmtNum(v); }, font: { size: 11 }, color: '#000' },
                                        grid: { color: '#eee' },
                                        border: { color: '#000' }
                                    }
                                }
                            }
                        });
                    } else {
                        dispPanel.style.display = 'none';
                    }
                }
            }

            window.toggleCmbSeries = function(el, ev) {
                var multi = ev && (ev.shiftKey || ev.ctrlKey || ev.metaKey);
                if (multi) {
                    // 다중 선택 모드: 기존 동작 (토글)
                    el.classList.toggle('active');
                } else {
                    // 단일 선택 모드: 다른 항목 모두 해제 + 현재만 active
                    var key = el.getAttribute('data-series');
                    document.querySelectorAll('.cmb-chart-item.active').forEach(function(x) {
                        if (x !== el) x.classList.remove('active');
                    });
                    el.classList.add('active');
                    cmbClickOrder = [key];
                }
                // 선택된 시리즈의 그룹은 펼침 상태로 유지 (검색 해제 후에도 보이도록)
                var grp = groupOfItem(el);
                if (grp && el.classList.contains('active')) expandedGroups.add(grp);
                buildCmbChart();
            };
            window.toggleCmbGroup = function(el) {
                if (cmbSearchQuery() !== '') return; // 검색 중에는 자동 펼침 상태 — 토글 무시
                var label = el.getAttribute('data-group') || '';
                if (expandedGroups.has(label)) expandedGroups.delete(label);
                else expandedGroups.add(label);
                refreshCmbList();
            };
            window.filterCmbSeries = function() { refreshCmbList(); };
            window.toggleCmbMA = function(win, el) {
                maActive[win] = !maActive[win];
                el.classList.toggle('active', maActive[win]);
                buildCmbChart();
            };
            window.toggleCmbDisp = function(win, el) {
                dispActive[win] = !dispActive[win];
                el.classList.toggle('active', dispActive[win]);
                buildCmbChart();
            };
            window.updateCmbChart = buildCmbChart;
            window.clearCmbSelections = function() {
                document.querySelectorAll('.cmb-chart-item.active').forEach(function(el){ el.classList.remove('active'); });
                cmbClickOrder = [];
                buildCmbChart();
            };

            // 화살표 위/아래 키로 시리즈 단일 선택 네비 (input 포커스 시 무시)
            document.addEventListener('keydown', function(e) {
                if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
                var ae = document.activeElement;
                var tag = ae && ae.tagName;
                if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (ae && ae.isContentEditable)) return;
                var items = Array.prototype.slice.call(document.querySelectorAll('.cmb-chart-item'));
                // 검색 중이면 필터 매칭(보이는) 항목 사이에서만 내비
                if (cmbSearchQuery() !== '') {
                    items = items.filter(function(el) {
                        var row = el.closest('tr');
                        return !row || row.style.display !== 'none';
                    });
                }
                if (items.length === 0) return;
                e.preventDefault();
                var activeIdx = -1;
                for (var i = 0; i < items.length; i++) {
                    if (items[i].classList.contains('active')) { activeIdx = i; break; }
                }
                var nextIdx;
                if (activeIdx < 0) {
                    nextIdx = (e.key === 'ArrowDown') ? 0 : items.length - 1;
                } else {
                    nextIdx = activeIdx + (e.key === 'ArrowDown' ? 1 : -1);
                    if (nextIdx < 0) nextIdx = items.length - 1;
                    if (nextIdx >= items.length) nextIdx = 0;
                }
                document.querySelectorAll('.cmb-chart-item.active').forEach(function(el) { el.classList.remove('active'); });
                items[nextIdx].classList.add('active');
                cmbClickOrder = [items[nextIdx].getAttribute('data-series')];
                // 접힌 그룹의 시리즈로 이동했으면 해당 그룹 펼침
                var navGrp = groupOfItem(items[nextIdx]);
                if (navGrp && !expandedGroups.has(navGrp)) {
                    expandedGroups.add(navGrp);
                    refreshCmbList();
                }
                items[nextIdx].scrollIntoView({ block: 'nearest' });
                buildCmbChart();
            });

            // 초기 상태: active(기본 선택) 시리즈가 있는 그룹만 펼침 (서버 렌더와 동기화)
            document.querySelectorAll('.cmb-chart-item.active').forEach(function(el) {
                var g = groupOfItem(el);
                if (g) expandedGroups.add(g);
            });
            refreshCmbList();
            buildCmbChart();
        })();
        </script>
        """.replace('CMB_DATA_PLACEHOLDER', export_json)

        return f"""
        <div class="category-section">
            <h2 class="category-title">DATA</h2>
            <div style="display:flex;gap:16px;align-items:flex-start;max-width:1800px;margin:0 auto;justify-content:center;">
                <div style="min-width:240px;">
                    <input type="text" id="cmbSeriesSearch" placeholder="시리즈 검색..." oninput="filterCmbSeries()" autocomplete="off" style="font-family:inherit;font-size:13px;width:100%;box-sizing:border-box;padding:6px 10px;margin-bottom:8px;border:1px solid #d1d5db;border-radius:6px;background:#fff;color:#222;">
                    <div style="max-height:720px;overflow-y:auto;">{list_html}</div>
                </div>
                <div style="width:1000px;">
                    <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;font-size:13px;">
                        <span style="color:#555;font-weight:600;">기간</span>
                        <input type="text" id="cmbStartDate" value="{first_date}" onchange="formatDateInput(this);updateCmbChart()" style="font-family:inherit;font-size:13px;padding:4px 8px;border:1px solid #d1d5db;border-radius:6px;background:#f9fafb;color:#222;width:110px;text-align:center;" placeholder="YYYY-MM-DD">
                        <span style="color:#888;">~</span>
                        <input type="text" id="cmbEndDate" value="{last_date}" onchange="formatDateInput(this);updateCmbChart()" style="font-family:inherit;font-size:13px;padding:4px 8px;border:1px solid #d1d5db;border-radius:6px;background:#f9fafb;color:#222;width:110px;text-align:center;" placeholder="YYYY-MM-DD">
                        <button onclick="downloadChartImage('cmbDynamicChart','AoE_Data','cmbChartLegend','cmbDispChart')" style="margin-left:auto;font-family:inherit;font-size:13px;font-weight:600;padding:6px 14px;background:#dc2626;color:#fff;border:none;border-radius:8px;cursor:pointer;">Download</button>
                        <button onclick="clearCmbSelections()" style="font-family:inherit;font-size:13px;font-weight:600;padding:4px 14px;background:#f3f4f6;color:#444;border:1px solid #d1d5db;border-radius:6px;cursor:pointer;margin-left:8px;">전체 해제</button>
                    </div>
                    <style>
                        .cmb-ma-btn {{ font-family:inherit;font-size:12px;font-weight:600;padding:4px 12px;border:1px solid #d1d5db;border-radius:20px;background:#f3f4f6;color:#888;cursor:pointer; }}
                        .cmb-ma-btn.active {{ background:#222;color:#fff;border-color:#222; }}
                        .cmb-ma-disabled .cmb-ma-btn {{ opacity:0.35;pointer-events:none; }}
                    </style>
                    <div id="cmbMaRow" style="display:flex;gap:6px;align-items:center;margin-bottom:12px;font-size:13px;">
                        <span style="color:#555;font-weight:600;">이동평균</span>
                        <button class="cmb-ma-btn" onclick="toggleCmbMA(20,this)">MA20</button>
                        <button class="cmb-ma-btn" onclick="toggleCmbMA(60,this)">MA60</button>
                        <button class="cmb-ma-btn" onclick="toggleCmbMA(120,this)">MA120</button>
                        <button class="cmb-ma-btn" onclick="toggleCmbMA(200,this)">MA200</button>
                        <span style="color:#555;font-weight:600;margin-left:18px;">이격도</span>
                        <button class="cmb-ma-btn" onclick="toggleCmbDisp(20,this)">20</button>
                        <button class="cmb-ma-btn" onclick="toggleCmbDisp(60,this)">60</button>
                        <button class="cmb-ma-btn" onclick="toggleCmbDisp(120,this)">120</button>
                        <button class="cmb-ma-btn" onclick="toggleCmbDisp(200,this)">200</button>
                    </div>
                    <div id="cmbChartCard" style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 4px 6px rgba(0,0,0,0.1);">
                        <div style="position:relative;height:600px;">
                            <canvas id="cmbDynamicChart"></canvas>
                        </div>
                        <div id="cmbDispPanel" style="display:none;position:relative;height:160px;margin-top:8px;">
                            <canvas id="cmbDispChart"></canvas>
                        </div>
                        <div id="cmbChartLegend" style="margin-top:12px;text-align:center;color:#222;"></div>
                    </div>
                </div>
            </div>
        </div>
        {js_code}
        {_chart_download_helper_js()}
        """
    except Exception as e:
        print(f"Error building combined chart section: {e}")
        import traceback; traceback.print_exc()
        return ""


def _build_hotel_mini_summary():
    """DATA 카테고리용 호텔 ADR 축소 요약 — 4개 도시별 lead+7 평균 ADR 카드 + Hotels 페이지 링크."""
    try:
        if not os.path.exists('hotel_adr.csv'):
            return ''
        df = pd.read_csv('hotel_adr.csv')
        if df.empty:
            return ''
        # 최신 collected_at의 lead_days=7 만 사용
        latest = df['collected_at'].max()
        df_latest = df[(df['collected_at'] == latest) & (df['lead_days'] == 7)]
        if df_latest.empty:
            return ''
        city_avg = df_latest.groupby('city').agg(avg=('price_krw', 'mean'), n=('hotel', 'nunique'))
        cards = ''
        for city in ['서울', '부산', '제주', '경주']:
            if city in city_avg.index:
                avg = int(city_avg.loc[city, 'avg'])
                n = int(city_avg.loc[city, 'n'])
                cards += (
                    '<div style="flex:1;min-width:160px;background:#fff;padding:16px 20px;'
                    'border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,0.06);text-align:center;">'
                    f'<div style="font-size:13px;color:#888;font-weight:600;margin-bottom:6px;">{city}</div>'
                    f'<div style="font-size:24px;color:#111;font-weight:700;">₩{avg:,}</div>'
                    f'<div style="font-size:11px;color:#aaa;margin-top:4px;">{n} hotels · lead+7</div>'
                    '</div>'
                )
        if not cards:
            return ''
        return f'''
        <div style="max-width:1800px;margin:32px auto 0;padding:0 16px;">
            <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px;">
                <h3 style="margin:0;font-size:18px;color:#333;font-weight:700;">HOTEL ADR · lead+7 평균</h3>
                <a href="hotels.html" style="color:#2563eb;font-size:13px;text-decoration:none;font-weight:600;">Detail in Hotels →</a>
            </div>
            <div style="display:flex;gap:12px;flex-wrap:wrap;">{cards}</div>
        </div>
        '''
    except Exception as e:
        print(f"Hotel mini summary 생성 실패: {e}")
        return ''


def _build_wrap_chart_section(category_label):
    """동적 Chart.js 수익률 비교 차트 (멀티 셀렉트)"""
    try:
        df_nav = pd.read_excel('Wrap_NAV.xlsx', sheet_name='기준가')
        if 'Date' in df_nav.columns:
            df_nav['Date'] = pd.to_datetime(df_nav['Date'])
            df_nav = df_nav.set_index('Date')

        chart_series = [
            ('삼성 트루밸류', '트루밸류'),
            ('NH Value ESG', 'Value ESG'),
            ('DB 개방형', '개방형 랩'),
            ('NH 목표전환형 4호', '목표전환형 4호'),  # 운용 개시 2026-06-15 (DB 5차 페어, 동일 구성)
            ('DB 목표전환형 5차', '목표전환형 5차'),  # 운용 개시 2026-06-12 (NH 4호 페어)
            # ('NH 목표전환형 3호', '목표전환형 3호'),  # NH 3호 완료 (2026-05-27 청산, 목표달성)
            # ('DB 목표전환형 4차', '목표전환형 4차'),  # DB 4차 완료 (2026-05-27 청산, 목표달성)
            # ('NH 목표전환형 2호', '목표전환형 2호'),  # NH 2호 완료 (2026-05-06, +7.26%, 목표 6.5% 초과)
            ('KOSPI', 'KOSPI'),
            ('KOSDAQ', 'KOSDAQ'),
        ]
        chart_colors = {
            '삼성 트루밸류': '#1428A0',
            'NH Value ESG': '#0072CE',
            'DB 개방형': '#00854A',
            'NH 목표전환형 4호': '#0072CE',  # 운용 개시 2026-06-15
            'DB 목표전환형 5차': '#00854A',  # 운용 개시 2026-06-12
            # 'NH 목표전환형 3호': '#0072CE',  # NH 3호 완료 (2026-05-27 청산, 목표달성)
            # 'DB 목표전환형 4차': '#00854A',  # DB 4차 완료 (2026-05-27 청산, 목표달성)
            # 'NH 목표전환형 2호': '#0072CE',  # NH 2호 완료 (2026-05-06, +7.26%, 목표 6.5% 초과)
            'KOSPI': '#000000',
            'KOSDAQ': '#666666',
        }

        nav_export = {'dates': [d.strftime('%Y-%m-%d') for d in df_nav.index]}
        for display, col in chart_series:
            if col in df_nav.columns:
                vals = df_nav[col].tolist()
                base = None
                pcts = []
                for v in vals:
                    if pd.notna(v) and base is None:
                        base = v
                    if base is not None and pd.notna(v):
                        pcts.append(round((v / base - 1) * 100, 2))
                    else:
                        pcts.append(None)
                nav_export[display] = pcts

        # Raw NAV values (for period-based return calculation)
        raw_export = {'dates': nav_export['dates']}
        for display, col in chart_series:
            if col in df_nav.columns:
                vals = df_nav[col].tolist()
                raw_export[display] = [round(v, 2) if pd.notna(v) else None for v in vals]

        nav_data_json = json.dumps(nav_export, ensure_ascii=False)
        raw_data_json = json.dumps(raw_export, ensure_ascii=False)
        colors_json = json.dumps(chart_colors, ensure_ascii=False)

        benchmarks = {'KOSPI', 'KOSDAQ'}
        rows_html = ''
        added_separator = False
        for display, _ in chart_series:
            if display in benchmarks and not added_separator:
                rows_html += '<tr><td colspan="2" style="padding:0;border-bottom:2px solid #000;"></td></tr>\n'
                added_separator = True
            color = chart_colors.get(display, '#888')
            active = ' active' if display == '삼성 트루밸류' else ''
            rows_html += f'<tr class="wrap-chart-item{active}" data-series="{display}" onclick="toggleWrapSeries(this)"><td style="width:6px;padding:0;"><div style="width:4px;height:100%;background:{color};border-radius:2px;"></div></td><td>{display}</td></tr>\n'
        mode_html = '<div style="display:flex;gap:4px;margin-bottom:8px;"><button class="wrap-mode-btn active" data-mode="return" onclick="switchChartMode(this)">수익률</button><button class="wrap-mode-btn" data-mode="mdd" onclick="switchChartMode(this)">MDD</button></div>'
        list_html = mode_html + f'<table class="portfolio-table" style="max-width:500px;margin:0 auto;"><tbody>{rows_html}</tbody></table>'

        dates = nav_export['dates']
        first_date = dates[0] if dates else ''
        last_date = dates[-1] if dates else ''

        js_code = """
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script>Chart.defaults.font.family = "'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif"; Chart.defaults.devicePixelRatio = 2 * (window.devicePixelRatio || 1); Chart.defaults.elements.line.borderJoinStyle = 'round'; Chart.defaults.elements.line.borderCapStyle = 'round';</script>
        <script>function formatDateInput(el){var v=el.value.replace(/[^0-9]/g,'');if(v.length===8){el.value=v.slice(0,4)+'-'+v.slice(4,6)+'-'+v.slice(6,8);}}</script>
        <script>
        (function() {
            var navData = NAV_DATA_PLACEHOLDER;
            var rawData = RAW_DATA_PLACEHOLDER;
            var chartColors = COLORS_PLACEHOLDER;
            var wrapChart = null;
            var chartMode = 'return'; // 'return' or 'mdd'

            function calcMDD(vals) {
                var peak = vals[0];
                var ddList = [];
                for (var i = 0; i < vals.length; i++) {
                    if (vals[i] > peak) peak = vals[i];
                    ddList.push(Math.round((vals[i] / peak - 1) * 10000) / 100);
                }
                return ddList;
            }

            function buildChart() {
                var selected = [];
                document.querySelectorAll('.wrap-chart-item.active').forEach(function(el) { selected.push(el.getAttribute('data-series')); });
                var startDate = document.getElementById('wrapStartDate').value;
                var endDate = document.getElementById('wrapEndDate').value;

                // Pass 1: 시리즈별 필터링 데이터 수집
                var perSeries = [];
                selected.forEach(function(name) {
                    if (!rawData[name]) return;
                    var filteredDates = [];
                    var filteredVals = [];
                    for (var i = 0; i < navData.dates.length; i++) {
                        var d = navData.dates[i];
                        if (d >= startDate && d <= endDate && rawData[name][i] !== null) {
                            filteredDates.push(d);
                            filteredVals.push(rawData[name][i]);
                        }
                    }
                    if (filteredVals.length === 0) return;
                    perSeries.push({ name: name, dates: filteredDates, vals: filteredVals });
                });

                // Pass 3: dataset 빌드 — % return 모드는 각 시리즈를 '자기 개시일' 기준 0%로 표시한다.
                // (공통 시작점 정규화 안 함: 여러 시리즈를 함께 선택해도 각자 자기 개시일부터의 수익률을
                //  그대로 보여준다. 예: DB 5차 6/12개시·NH 4호 6/15개시를 함께 켜도 각자 개시일 기준. MDD도 독립.)
                // x축 라벨 = 선택된 모든 시리즈 날짜의 합집합(정렬). 시리즈마다 개시일이 달라도
                // x축을 더 긴 범위(가장 이른 개시일~)로 통일하고, 각 시리즈 data를 이 라벨에
                // 인덱스 정렬한 배열(없는 날짜=null)로 만든다.
                // ★{x,y} 객체 + category labels 혼용 시 호버(index 모드)가 데이터 배열 인덱스와
                //   라벨이 어긋나 엉뚱한 날짜 값을 표시("누운 V자"·호버 오표시) → 라벨 정렬 배열로
                //   세로(날짜 컬럼) 스냅 정상화.
                var allDates = Array.from(new Set(perSeries.reduce(function(a, s){ return a.concat(s.dates); }, []))).sort();

                var datasets = [];
                perSeries.forEach(function(s) {
                    var d_arr = s.dates;
                    var v_arr = s.vals;
                    if (v_arr.length === 0) return;

                    var yByDate = {};
                    if (chartMode === 'mdd') {
                        var mddVals = calcMDD(v_arr);
                        d_arr.forEach(function(d, j) { yByDate[d] = mddVals[j]; });
                    } else {
                        var base = v_arr[0];
                        d_arr.forEach(function(d, j) { yByDate[d] = Math.round((v_arr[j] / base - 1) * 10000) / 100; });
                    }
                    var data = allDates.map(function(d) { return Object.prototype.hasOwnProperty.call(yByDate, d) ? yByDate[d] : null; });

                    datasets.push({
                        label: s.name,
                        data: data,
                        borderColor: chartColors[s.name] || '#888',
                        backgroundColor: 'transparent',
                        borderWidth: (s.name === 'KOSPI' || s.name === 'KOSDAQ') ? 1.5 : 3,
                        pointRadius: 0,
                        tension: 0.3,
                        spanGaps: false
                    });
                });

                // 선 끝에 수익률 라벨을 그리는 커스텀 플러그인
                var endLabelPlugin = {
                    id: 'endLabels',
                    afterDatasetsDraw: function(chart) {
                        var ctx = chart.ctx;
                        chart.data.datasets.forEach(function(ds, i) {
                            var meta = chart.getDatasetMeta(i);
                            if (meta.hidden) return;
                            var last = meta.data[meta.data.length - 1];
                            if (!last) return;
                            var val = ds.data[ds.data.length - 1];
                            if (val === null || val === undefined) return;
                            var rounded = Math.sign(val) * Math.round(Math.abs(val));
                            var sign = rounded >= 0 ? '+' : '';
                            var label = sign + rounded + '%';
                            ctx.save();
                            ctx.font = 'bold 12px sans-serif';
                            ctx.fillStyle = ds.borderColor;
                            ctx.textBaseline = 'middle';
                            ctx.fillText(label, last.x + 6, last.y);
                            ctx.restore();
                        });
                    }
                };

                // 하단 컬러닷 범례 (선택된 시리즈만)
                var legendEl = document.getElementById('wrapChartLegend');
                if (legendEl) {
                    legendEl.innerHTML = datasets.map(function(ds) {
                        var c = ds.borderColor;
                        return '<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px;font-size:13px;">' +
                            '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + c + ';"></span>' +
                            ds.label + '</span>';
                    }).join('');
                }

                if (wrapChart) wrapChart.destroy();
                wrapChart = new Chart(document.getElementById('wrapDynamicChart'), {
                    type: 'line',
                    data: { labels: allDates, datasets: datasets },
                    plugins: [endLabelPlugin],
                    options: {
                        responsive: true, maintainAspectRatio: false,
                        layout: { padding: { right: 60 } },
                        interaction: { mode: 'index', intersect: false },
                        plugins: {
                            legend: { display: false },
                            tooltip: { callbacks: { label: function(ctx) { return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) + '%'; } } }
                        },
                        scales: {
                            x: { type: 'category', display: datasets.length > 0, ticks: { maxTicksLimit: 6, callback: function(val) { var d = this.getLabelForValue(val); if (!d) return ''; return d.slice(2,4) + '/' + d.slice(5,7); }, maxRotation: 0, font: { size: 11 }, color: '#000' }, grid: { color: '#eee', display: true }, border: { color: '#000' } },
                            y: { ticks: { callback: function(v) { return v + '%'; }, font: { size: 11 }, color: '#000' }, grid: { color: '#eee' }, border: { color: '#000' } }
                        }
                    }
                });
            }

            window.toggleWrapSeries = function(el) { el.classList.toggle('active'); buildChart(); };
            window.updateWrapChart = buildChart;
            window.switchChartMode = function(el) {
                document.querySelectorAll('.wrap-mode-btn').forEach(function(b) { b.classList.remove('active'); });
                el.classList.add('active');
                chartMode = el.getAttribute('data-mode');
                buildChart();
            };
            window.downloadWrapChart = function() {
                if (!wrapChart) return;
                var srcImg = new Image();
                srcImg.onload = function() {
                    var canvas = document.createElement('canvas');
                    canvas.width = srcImg.width;
                    canvas.height = srcImg.height;
                    var ctx = canvas.getContext('2d');
                    ctx.fillStyle = '#ffffff';
                    ctx.fillRect(0, 0, canvas.width, canvas.height);
                    ctx.drawImage(srcImg, 0, 0);
                    ctx.strokeStyle = '#000000';
                    ctx.lineWidth = 0.5;
                    ctx.strokeRect(0.25, 0.25, canvas.width - 0.5, canvas.height - 0.5);
                    canvas.toBlob(function(blob) {
                        var url = URL.createObjectURL(blob);
                        var a = document.createElement('a');
                        a.href = url;
                        a.download = 'wrap_chart_' + new Date().toISOString().slice(0,10) + '.png';
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        URL.revokeObjectURL(url);
                    }, 'image/png');
                };
                srcImg.src = wrapChart.toBase64Image('image/png', 1);
            };
            buildChart();
        })();
        </script>
        """.replace('NAV_DATA_PLACEHOLDER', nav_data_json).replace('COLORS_PLACEHOLDER', colors_json).replace('RAW_DATA_PLACEHOLDER', raw_data_json)

        return f"""
        <div class="category-section">
            <h2 class="category-title">{category_label}</h2>
            <div style="display:flex;gap:16px;align-items:flex-start;justify-content:center;max-width:1800px;margin:0 auto;">
                <div style="min-width:180px;">{list_html}</div>
                <div style="width:1000px;">
                    <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;font-size:13px;">
                        <span style="color:#555;font-weight:600;">기간</span>
                        <input type="text" id="wrapStartDate" value="{first_date}" onchange="formatDateInput(this);updateWrapChart()" style="font-family:inherit;font-size:13px;padding:4px 8px;border:1px solid #d1d5db;border-radius:6px;background:#f9fafb;color:#222;width:110px;text-align:center;" placeholder="YYYY-MM-DD">
                        <span style="color:#888;">~</span>
                        <input type="text" id="wrapEndDate" value="{last_date}" onchange="formatDateInput(this);updateWrapChart()" style="font-family:inherit;font-size:13px;padding:4px 8px;border:1px solid #d1d5db;border-radius:6px;background:#f9fafb;color:#222;width:110px;text-align:center;" placeholder="YYYY-MM-DD">
                        <button onclick="downloadWrapChart()" style="margin-left:auto;font-family:inherit;font-size:13px;font-weight:600;padding:6px 14px;background:#dc2626;color:#fff;border:none;border-radius:8px;cursor:pointer;">Download</button>
                    </div>
                    <div style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 4px 6px rgba(0,0,0,0.1);">
                        <div style="position:relative;height:500px;">
                            <canvas id="wrapDynamicChart"></canvas>
                        </div>
                        <div id="wrapChartLegend" style="margin-top:12px;text-align:center;color:#222;"></div>
                    </div>
                </div>
            </div>
        </div>
        {js_code}
        """
    except Exception as e:
        print(f"Error building wrap chart section: {e}")
        return ""


def _build_target_transform_chart_section():
    """NH 목표전환형 1호 수익률 차트 + 일자별 투자 비중."""
    try:
        df_nav = pd.read_excel('Wrap_NAV.xlsx', sheet_name='기준가')
        df_nav['Date'] = pd.to_datetime(df_nav['Date'])
        cols = ['Date', '목표전환형 1호', 'KOSPI', 'KOSDAQ']
        nav = df_nav[cols].dropna(subset=['목표전환형 1호']).copy().sort_values('Date')
        if len(nav) < 2:
            return ''

        dates = [d.strftime('%Y-%m-%d') for d in nav['Date']]

        def to_pct(series):
            vals = series.tolist()
            base = None
            out = []
            for v in vals:
                if pd.notna(v) and base is None:
                    base = v
                if base is not None and pd.notna(v):
                    out.append(round((v / base - 1) * 100, 2))
                else:
                    out.append(None)
            return out

        target_pct = to_pct(nav['목표전환형 1호'])
        kospi_pct = to_pct(nav['KOSPI'])
        kosdaq_pct = to_pct(nav['KOSDAQ'])

        # NEW 시트에서 '목표전환형 1호' 일자별 비중 합계
        df_new = pd.read_excel('Wrap_NAV.xlsx', sheet_name='NEW')
        mask = df_new['상품명'].astype(str).str.contains('목표전환형 1호', na=False)
        daily_w = {}
        if mask.sum() > 0:
            sub = df_new[mask].copy()
            sub['날짜'] = pd.to_datetime(sub['날짜'])
            grouped = sub.groupby(sub['날짜'].dt.strftime('%Y-%m-%d'))['비중'].sum()
            daily_w = {d: round(float(v), 2) for d, v in grouped.items()}

        # 라인차트 labels와 같은 순서로 weight series (없는 날짜는 None)
        weight_series = [daily_w.get(d) for d in dates]

        data_json = json.dumps({
            'dates': dates,
            'target': target_pct,
            'kospi': kospi_pct,
            'kosdaq': kosdaq_pct,
            'weights': weight_series,
        }, ensure_ascii=False)

        html = """
        <div class="category-section">
            <h2 class="category-title">NH 목표전환형 1호</h2>
            <div style="display:flex;justify-content:center;">
                <div style="width:1000px;">
                    <div style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 4px 6px rgba(0,0,0,0.1);">
                        <div style="position:relative;height:500px;">
                            <canvas id="targetTransformChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <script>
        (function() {
            var D = __DATA_JSON__;
            var stemPlugin = {
                id: 'weightStems',
                afterDatasetsDraw: function(chart) {
                    var meta = chart.getDatasetMeta(3);
                    if (!meta || !meta.data) return;
                    var yScale = chart.scales.y1;
                    if (!yScale) return;
                    var baseY = yScale.getPixelForValue(0);
                    chart.ctx.save();
                    chart.ctx.strokeStyle = 'rgba(150,150,150,0.5)';
                    chart.ctx.lineWidth = 1.5;
                    meta.data.forEach(function(pt) {
                        if (!pt || pt.skip) return;
                        chart.ctx.beginPath();
                        chart.ctx.moveTo(pt.x, pt.y);
                        chart.ctx.lineTo(pt.x, baseY);
                        chart.ctx.stroke();
                    });
                    chart.ctx.restore();
                }
            };
            var ctx = document.getElementById('targetTransformChart').getContext('2d');
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: D.dates,
                    datasets: [
                        { label: '목표전환형 1호', data: D.target, borderColor: '#e11d48', backgroundColor: 'transparent', borderWidth: 3, pointRadius: 0, tension: 0.3, yAxisID: 'y' },
                        { label: 'KOSPI', data: D.kospi, borderColor: '#000000', backgroundColor: 'transparent', borderWidth: 1.5, pointRadius: 0, tension: 0.3, yAxisID: 'y' },
                        { label: 'KOSDAQ', data: D.kosdaq, borderColor: '#666666', backgroundColor: 'transparent', borderWidth: 1.5, pointRadius: 0, tension: 0.3, yAxisID: 'y' },
                        { label: '투자 비중 (%)', data: D.weights, showLine: false, pointRadius: 6, pointHoverRadius: 8, pointBackgroundColor: '#dc2626', pointBorderColor: '#dc2626', yAxisID: 'y1', spanGaps: false }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    scales: {
                        y: { position: 'left', title: { display: true, text: '수익률 (%)' } },
                        y1: { position: 'right', title: { display: true, text: '투자 비중 (%)' }, min: 0, max: 100, grid: { drawOnChartArea: false } }
                    },
                    plugins: {
                        legend: { position: 'top' },
                        tooltip: { mode: 'index', intersect: false }
                    }
                },
                plugins: [stemPlugin]
            });
        })();
        </script>
        """
        return html.replace('__DATA_JSON__', data_json)
    except Exception as e:
        print(f"Error building target transform chart: {e}")
        return ''


def pick_weekly_last(date_strs):
    """각 ISO 주의 마지막 거래일 + 전체 최신일을 반환.

    상단/누적 AUM 차트가 공유 — 모든 거래일 대신 주봉(주 마지막 거래일)만 표시.
    입력: 'YYYY-MM-DD' 정렬된 문자열 리스트. 출력: 동일 형식 sparse 리스트.
    """
    if not date_strs:
        return []
    dts = pd.Series(pd.to_datetime(list(date_strs))).sort_values().reset_index(drop=True)
    iso = dts.dt.isocalendar()
    df_tmp = pd.DataFrame({'date': dts, 'year': iso['year'].values, 'week': iso['week'].values})
    last_each = df_tmp.groupby(['year', 'week'])['date'].max().tolist()
    selected = set(last_each)
    selected.add(dts.iloc[-1])  # 전체 최신일 보장
    return [d.strftime('%Y-%m-%d') for d in sorted(selected)]


def create_aum_table():
    """AUM 테이블 HTML 생성"""
    try:
        nav_file = 'Wrap_NAV.xlsx'
        if not os.path.exists(nav_file):
            return ""
        df = pd.read_excel(nav_file, sheet_name='AUM')
        if df.empty:
            return ""
        df['날짜'] = pd.to_datetime(df['날짜'])
        latest = df.sort_values('날짜').groupby('상품명').last().reset_index()
        # 상단 테이블: 최신 날짜 상품만 (가장 최근 거래일 기준)
        # 정렬: broker AUM 합 내림차순 → broker 안에서 일반형 → 목표전환형 → AUM 내림차순
        max_date = latest['날짜'].max()
        table_latest = latest[latest['날짜'] == max_date].copy()
        broker_total = table_latest.groupby('증권사')['AUM'].sum().sort_values(ascending=False)
        table_latest['broker_rank'] = table_latest['증권사'].map({b: i for i, b in enumerate(broker_total.index)})
        table_latest['is_target'] = table_latest['상품명'].str.contains('목표전환형').astype(int)
        table_latest = table_latest.sort_values(
            ['broker_rank', 'is_target', 'AUM'], ascending=[True, True, False]
        ).drop(columns=['broker_rank', 'is_target'])
        rows_html = ''
        total_aum = 0
        for _, row in table_latest.iterrows():
            aum = int(row['AUM'])
            total_aum += aum
            aum_억 = aum / 100_000_000
            date_str = row['날짜'].strftime('%m/%d')
            rows_html += f'<tr><td>{row["증권사"]}</td><td>{row["상품명"]}</td><td>{aum_억:,.0f}억</td><td>{date_str}</td></tr>\n'
        total_억 = total_aum / 100_000_000
        rows_html += f'<tr style="border-top:2px solid #000;font-weight:700;"><td colspan="2">합계</td><td>{total_억:,.0f}억</td><td></td></tr>'
        # 증권사별 색상
        broker_colors = {'삼성': '#1428A0', 'NH': '#0072CE', 'DB': '#00854A'}

        # 일자별 증권사+상품명 기준 AUM (stacked bar용)
        # 차트 구간은 누적 AUM 차트와 동일 (2026-03-20~), 봉은 주봉(주 마지막 거래일)만.
        # 활성 상품만 차트에 표시 (청산 회차는 누적 AUM 차트에서 broker 단위로 누적).
        chart_start = '2026-03-20'
        chart_active = latest[latest['날짜'] == max_date].copy()
        chart_names = set(chart_active['상품명'])
        chart_df = df[df['상품명'].isin(chart_names)].copy()
        chart_df = chart_df[chart_df['날짜'].dt.strftime('%Y-%m-%d') >= chart_start]
        chart_df['label'] = chart_df['증권사'] + ' ' + chart_df['상품명']
        daily = chart_df.groupby([chart_df['날짜'].dt.strftime('%Y-%m-%d'), 'label', '증권사'])['AUM'].sum().reset_index()
        daily.columns = ['date', 'label', 'broker', 'aum']
        all_daily_dates = sorted(daily['date'].unique())
        dates_sorted = pick_weekly_last(all_daily_dates)  # 주봉화

        # 일반형은 매일 데이터가 있으나 목표전환형은 가끔 빠질 수 있음.
        # 주 마지막 거래일에 해당 상품 데이터가 없으면 forward-fill (직전 거래일 값).
        def _ffill_aum(label):
            timeline = {}
            for _, r in daily[daily['label'] == label].sort_values('date').iterrows():
                timeline[r['date']] = r['aum']
            filled = []
            last_known = 0
            for d in all_daily_dates:
                if d in timeline:
                    last_known = timeline[d]
                filled.append((d, last_known))
            filled_map = dict(filled)
            return [filled_map.get(d, 0) for d in dates_sorted]

        # 차트 범례 순서 (증권사 그룹 + AUM 내림차순)
        chart_broker_total = chart_active.groupby('증권사')['AUM'].sum().sort_values(ascending=False)
        chart_active['broker_rank'] = chart_active['증권사'].map({b: i for i, b in enumerate(chart_broker_total.index)})
        chart_active = chart_active.sort_values(['broker_rank', 'AUM'], ascending=[True, False])
        all_labels = (chart_active.apply(lambda r: r['증권사'] + ' ' + r['상품명'], axis=1)).tolist()

        opacity_levels = [1.0, 0.6, 0.35]
        broker_idx = {}
        product_colors = {}
        for label in all_labels:
            broker = daily[daily['label'] == label]['broker'].iloc[0]
            idx = broker_idx.get(broker, 0)
            broker_idx[broker] = idx + 1
            base = broker_colors.get(broker, '#888888')
            r, g, b = int(base[1:3], 16), int(base[3:5], 16), int(base[5:7], 16)
            op = opacity_levels[min(idx, len(opacity_levels) - 1)]
            product_colors[label] = f'rgba({r},{g},{b},{op})'

        chart_datasets = []
        for label in all_labels:
            ffilled = _ffill_aum(label)
            vals = [round(v / 100_000_000) for v in ffilled]
            chart_datasets.append({
                'label': label,
                'data': vals,
                'backgroundColor': product_colors.get(label, '#888')
            })

        aum_chart_json = json.dumps({'dates': dates_sorted, 'datasets': chart_datasets}, ensure_ascii=False)

        aum_js = """
        <script>
        (function() {
            var aumData = AUM_DATA_PLACEHOLDER;
            var totalLabelPlugin = {
                id: 'totalLabels',
                afterDatasetsDraw: function(chart) {
                    var ctx = chart.ctx;
                    var datasets = chart.data.datasets;
                    var meta0 = chart.getDatasetMeta(0);
                    for (var i = 0; i < meta0.data.length; i++) {
                        var total = 0;
                        for (var d = 0; d < datasets.length; d++) {
                            total += datasets[d].data[i] || 0;
                        }
                        var lastMeta = chart.getDatasetMeta(datasets.length - 1);
                        var bar = lastMeta.data[i];
                        if (!bar) continue;
                        ctx.save();
                        ctx.font = 'bold 11px sans-serif';
                        ctx.fillStyle = '#000';
                        ctx.textAlign = 'center';
                        ctx.textBaseline = 'bottom';
                        ctx.fillText(Math.round(total), bar.x, bar.y - 4);
                        ctx.restore();
                    }
                }
            };
            new Chart(document.getElementById('aumStackedChart'), {
                type: 'bar',
                data: {
                    labels: aumData.dates.map(function(d) { return d.slice(5); }),
                    datasets: aumData.datasets.map(function(ds) {
                        return { label: ds.label, data: ds.data, backgroundColor: ds.backgroundColor };
                    })
                },
                plugins: [totalLabelPlugin],
                options: {
                    responsive: true, maintainAspectRatio: false,
                    layout: { padding: { top: 20 } },
                    plugins: {
                        legend: { position: 'bottom', labels: { font: { size: 11 }, color: '#000' } },
                        tooltip: { callbacks: {
                            title: function(ctxs) { return ctxs.length ? aumData.dates[ctxs[0].dataIndex] : ''; },
                            label: function(ctx) { return ctx.dataset.label + ': ' + Math.round(ctx.raw) + '억'; }
                        } }
                    },
                    scales: {
                        x: { stacked: true, ticks: { font: { size: 11 }, color: '#000' }, grid: { display: false } },
                        y: { stacked: true, ticks: { callback: function(v) { return v + '억'; }, font: { size: 11 }, color: '#000' }, grid: { color: '#eee' } }
                    }
                }
            });
        })();
        </script>
        """.replace('AUM_DATA_PLACEHOLDER', aum_chart_json)

        return f"""
        <div class="category-section">
            <h2 class="category-title" style="display:flex;align-items:center;max-width:1800px;margin-left:auto;margin-right:auto;">
                <span>AUM</span>
                <a href="https://raw.githubusercontent.com/sisyphe10/Antigravity_Market_Dashboard/main/Wrap_NAV.xlsx" download="Wrap_NAV.xlsx" target="_blank" style="margin-left:auto;text-transform:none;font-family:inherit;font-size:14px;font-weight:600;padding:6px 14px;background:#dc2626;color:#fff;text-decoration:none;border-radius:8px;">Wrap_NAV</a>
            </h2>
            <div style="display:flex;gap:100px;align-items:flex-start;max-width:1800px;margin:0 auto;">
                <div style="width:370px;">
                    <table class="portfolio-table aum-aligned" style="white-space:nowrap;width:370px;table-layout:fixed;">
                        <colgroup>
                            <col style="width:60px"><col style="width:160px"><col style="width:80px"><col style="width:70px">
                        </colgroup>
                        <thead><tr>
                            <th>증권사</th>
                            <th>상품명</th>
                            <th>AUM</th>
                            <th>기준일</th>
                        </tr></thead>
                        <tbody>{rows_html}</tbody>
                    </table>
                </div>
                <div style="flex:1;background:#fff;border-radius:12px;padding:20px;box-shadow:0 4px 6px rgba(0,0,0,0.1);">
                    <div style="position:relative;height:300px;"><canvas id="aumStackedChart"></canvas></div>
                </div>
            </div>
        </div>
        {aum_js}"""
    except Exception as e:
        print(f"Error creating AUM table: {e}")
        return ""


def create_cumulative_aum_chart():
    """누적 AUM 차트 - 일반형은 현재 AUM, 목표전환형은 회차별 AUM 누적 합산"""
    try:
        nav_file = 'Wrap_NAV.xlsx'
        if not os.path.exists(nav_file):
            return ""
        df = pd.read_excel(nav_file, sheet_name='AUM')
        if df.empty:
            return ""
        df['날짜'] = pd.to_datetime(df['날짜'])

        # 목표전환형 종료일/운용 개시일 결정: 기준가 시트에서 각 회차의 첫/마지막 유효 데이터.
        # 종료일 — 전체 최신 거래일과 같으면 활성(=빈칸), 빠르면 청산일(=MM/DD).
        # 시작일 — 기준가 첫 유효 = 운용 개시일 (AUM 시트보다 정확).
        end_dates = {}
        first_in_nav = {}
        last_in_nav = {}            # 회차별 마지막 유효 NAV 일자 (거래일 집계용)
        nav_trading_days = None     # 기준가 시트의 전체 거래일 인덱스 (공휴일 자동 제외)
        try:
            df_nav = pd.read_excel(nav_file, sheet_name='기준가')
            if 'Date' in df_nav.columns:
                df_nav['Date'] = pd.to_datetime(df_nav['Date'])
                df_nav = df_nav.set_index('Date')
            else:
                df_nav.index = pd.to_datetime(df_nav.iloc[:, 0])
                df_nav = df_nav.iloc[:, 1:]
            nav_latest = df_nav.index.max()
            nav_trading_days = df_nav.index.sort_values()
            for col in df_nav.columns:
                if '목표전환형' not in col:
                    continue
                valid = df_nav[col].dropna()
                if valid.empty:
                    continue
                first_in_nav[col] = valid.index[0]
                last_date = valid.index[-1]
                last_in_nav[col] = last_date
                end_dates[col] = '' if last_date >= nav_latest else last_date.strftime('%m/%d')
            # 별칭: 기준가 시트의 '목표전환형' (suffix 없음, DB 1차) → AUM 시트 '목표전환형 1차'
            if '목표전환형' in end_dates:
                end_dates.setdefault('목표전환형 1차', end_dates['목표전환형'])
            if '목표전환형' in first_in_nav:
                first_in_nav.setdefault('목표전환형 1차', first_in_nav['목표전환형'])
            if '목표전환형' in last_in_nav:
                last_in_nav.setdefault('목표전환형 1차', last_in_nav['목표전환형'])
        except Exception as e:
            print(f"Warning: 종료일 계산 실패: {e}")

        def _trading_days(start_ts, end_ts):
            """기준가 거래일 인덱스로 start~end 사이 실제 거래일 수 (양끝 포함)."""
            if start_ts is None or end_ts is None or nav_trading_days is None or len(nav_trading_days) == 0:
                return None
            try:
                mask = (nav_trading_days >= start_ts) & (nav_trading_days <= end_ts)
                n = int(mask.sum())
                return n if n > 0 else None
            except Exception:
                return None

        # 차트 표시는 3/20부터 (이전 데이터는 forward-fill 기준값으로만 사용)
        # 봉은 주봉(각 ISO 주의 마지막 거래일 + 전체 최신일)만 표시
        chart_start = '2026-03-20'
        all_dates_full_range = sorted(d for d in df['날짜'].dt.strftime('%Y-%m-%d').unique() if d >= chart_start)
        all_dates = pick_weekly_last(all_dates_full_range)

        is_target = df['상품명'].str.contains('목표전환형', na=False)
        regular_df = df[~is_target].copy()
        target_df = df[is_target].copy()

        broker_colors = {'삼성': '#1428A0', 'NH': '#0072CE', 'DB': '#00854A'}
        opacity_levels = [1.0, 0.6, 0.35]

        # 전체 날짜 (forward-fill 기준값 계산용, 차트 시작일 이전 포함)
        all_dates_full = sorted(df['날짜'].dt.strftime('%Y-%m-%d').unique())

        def forward_fill_aum(product_df, chart_dates):
            """전체 데이터에서 forward-fill 후 chart_dates에 해당하는 값만 반환"""
            timeline = {}
            for _, row in product_df.sort_values('날짜').iterrows():
                timeline[row['날짜'].strftime('%Y-%m-%d')] = row['AUM']
            # 전체 날짜로 forward-fill
            filled = {}
            last_known = 0
            for d in all_dates_full:
                if d in timeline:
                    last_known = timeline[d]
                filled[d] = last_known
            # chart_dates에 해당하는 값만 추출
            return [filled.get(d, 0) for d in chart_dates]

        datasets = []
        broker_idx = {}

        # 일반형: 개별 시리즈
        regular_df['label'] = regular_df['증권사'] + ' ' + regular_df['상품명']
        reg_latest = regular_df.sort_values('날짜').groupby('label').last().reset_index()
        broker_total = reg_latest.groupby(reg_latest['label'].str.split(' ').str[0])['AUM'].sum().sort_values(ascending=False)
        reg_latest['broker_rank'] = reg_latest['label'].str.split(' ').str[0].map({b: i for i, b in enumerate(broker_total.index)})
        reg_labels_sorted = reg_latest.sort_values(['broker_rank', 'AUM'], ascending=[True, False])['label'].tolist()

        for label in reg_labels_sorted:
            sub = regular_df[regular_df['label'] == label]
            broker = sub['증권사'].iloc[0]
            idx = broker_idx.get(broker, 0)
            broker_idx[broker] = idx + 1
            base = broker_colors.get(broker, '#888888')
            r, g, b = int(base[1:3], 16), int(base[3:5], 16), int(base[5:7], 16)
            op = opacity_levels[min(idx, len(opacity_levels) - 1)]
            vals = forward_fill_aum(sub, all_dates)
            datasets.append({
                'label': label,
                'data': [round(v / 1e8) for v in vals],
                'backgroundColor': f'rgba({r},{g},{b},{op})'
            })

        # 목표전환형: 증권사별 누적 합산 (모든 회차의 AUM forward-fill 후 합산)
        for broker in sorted(target_df['증권사'].unique()):
            broker_target = target_df[target_df['증권사'] == broker]
            iterations = broker_target['상품명'].unique()
            cumulative_vals = [0] * len(all_dates)
            for it in iterations:
                it_data = broker_target[broker_target['상품명'] == it]
                it_vals = forward_fill_aum(it_data, all_dates)
                for i in range(len(all_dates)):
                    cumulative_vals[i] += it_vals[i]

            idx = broker_idx.get(broker, 0)
            broker_idx[broker] = idx + 1
            base = broker_colors.get(broker, '#888888')
            r, g, b = int(base[1:3], 16), int(base[3:5], 16), int(base[5:7], 16)
            op = opacity_levels[min(idx, len(opacity_levels) - 1)]
            datasets.append({
                'label': f'{broker} 목표전환형 (누적)',
                'data': [round(v / 1e8) for v in cumulative_vals],
                'backgroundColor': f'rgba({r},{g},{b},{op})'
            })

        # 누적 AUM 표: 5행 고정 (broker별 일반형 → 목표전환형 통합 행).
        # 목표전환형 행은 활성 회차(없으면 가장 최근 청산) 데이터를 메인으로 표시하고,
        # 회차별 [회차명, 마지막 AUM, 시작일, 종료일]은 hover tooltip으로 노출.
        latest_per_product = df.sort_values('날짜').groupby('상품명').last().reset_index()
        first_per_product = df.sort_values('날짜').groupby('상품명').first()['날짜']
        max_date = latest_per_product['날짜'].max()

        # broker 순서: 최신 날짜의 broker AUM 합 내림차순
        active_all = latest_per_product[latest_per_product['날짜'] == max_date]
        broker_order = active_all.groupby('증권사')['AUM'].sum().sort_values(ascending=False).index.tolist()
        # 활성 일반형이 없지만 목표전환형 청산 이력만 있는 broker 포함 (안전망)
        for b in df['증권사'].unique():
            if b not in broker_order:
                broker_order.append(b)

        target_df_all = df[df['상품명'].str.contains('목표전환형', na=False)]

        def _target_summary(broker):
            broker_target = target_df_all[target_df_all['증권사'] == broker]
            if broker_target.empty:
                return None
            # 활성 회차: 최신 거래일에 데이터가 있는 회차 (있으면 1개)
            active_iter_rows = broker_target[broker_target['날짜'] == max_date]
            if not active_iter_rows.empty:
                iter_name = active_iter_rows.iloc[0]['상품명']
            else:
                # 활성 없음 → 가장 최근 청산 회차 (마지막 데이터 날짜 기준)
                last_per_iter = broker_target.sort_values('날짜').groupby('상품명').last()
                iter_name = last_per_iter.sort_values('날짜').index[-1]
            iter_rows = broker_target[broker_target['상품명'] == iter_name].sort_values('날짜')
            main_aum = int(iter_rows.iloc[-1]['AUM'])
            main_date = iter_rows.iloc[-1]['날짜']
            main_end = end_dates.get(iter_name, '')

            # 회차별 detail: 시작일 순으로 정렬
            # 시작일은 기준가 시트의 첫 유효 데이터 (= 운용 개시일) 우선, 없으면 AUM 시트 첫 데이터.
            iters = []
            last_per_iter_all = broker_target.sort_values('날짜').groupby('상품명').last()
            for it_name, it_row in last_per_iter_all.iterrows():
                start_d = first_in_nav.get(it_name) or first_per_product.get(it_name)
                end_d = last_in_nav.get(it_name)
                if end_d is None:
                    end_d = it_row['날짜']  # 기준가에 없으면 AUM 마지막 일자로 폴백
                iters.append({
                    'name': it_name,
                    'last_aum': int(it_row['AUM']),
                    'start': start_d,
                    'end': end_dates.get(it_name, ''),
                    'days': _trading_days(start_d, end_d),
                })
            iters.sort(key=lambda x: x['start'] if x['start'] is not None else pd.Timestamp('1970-01-01'))
            # 청산 회차 포함 broker 내 모든 회차 마지막 AUM 합 (차트 누적 합산과 동일 기준)
            cumulative_aum = sum(it['last_aum'] for it in iters)
            return {'aum': main_aum, 'date': main_date, 'end': main_end,
                    'iters': iters, 'cumulative_aum': cumulative_aum}

        def _tooltip_html(iters):
            tt_rows = ''
            for it in iters:
                aum_s = f"{it['last_aum']/1e8:,.0f}억"
                start_s = it['start'].strftime('%m/%d') if it['start'] is not None else '-'
                end_s = it['end'] if it['end'] else '운용 중'
                days_s = f"{it['days']}일" if it.get('days') is not None else '-'
                tt_rows += (f'<tr><td>{it["name"]}</td><td>{aum_s}</td>'
                            f'<td>{start_s}</td><td>{end_s}</td><td>{days_s}</td></tr>')
            return (
                '<div class="iter-tooltip">'
                '<table class="iter-table">'
                '<thead><tr><th>회차</th><th>AUM</th><th>시작일</th><th>종료일</th><th>거래일</th></tr></thead>'
                f'<tbody>{tt_rows}</tbody>'
                '</table></div>'
            )

        cum_rows_html = ''
        cum_total = 0
        for broker in broker_order:
            # 1) 그 broker의 활성 일반형 (AUM 내림차순)
            broker_regular = active_all[
                (active_all['증권사'] == broker) &
                (~active_all['상품명'].str.contains('목표전환형', na=False))
            ].sort_values('AUM', ascending=False)
            for _, r in broker_regular.iterrows():
                aum_val = int(r['AUM'])
                cum_total += aum_val
                date_str = r['날짜'].strftime('%m/%d')
                cum_rows_html += (
                    f'<tr><td>{broker}</td><td>{r["상품명"]}</td>'
                    f'<td>{aum_val/1e8:,.0f}억</td><td>{date_str}</td></tr>\n'
                )
            # 2) 그 broker의 목표전환형 통합 행 (활성 또는 가장 최근 청산)
            summary = _target_summary(broker)
            if summary is not None:
                cum_total += summary['cumulative_aum']
                date_str = summary['date'].strftime('%m/%d')
                cum_rows_html += (
                    f'<tr class="iter-row"><td>{broker}</td>'
                    f'<td style="position:relative;">목표전환형{_tooltip_html(summary["iters"])}</td>'
                    f'<td>{summary["cumulative_aum"]/1e8:,.0f}억</td>'
                    f'<td>{date_str}</td></tr>\n'
                )
        cum_rows_html += f'<tr style="border-top:2px solid #000;font-weight:700;"><td colspan="2">합계</td><td>{cum_total/1e8:,.0f}억</td><td></td></tr>'

        chart_json = json.dumps({'dates': all_dates, 'datasets': datasets}, ensure_ascii=False)

        chart_js = """
        <script>
        (function() {
            var cData = __CUMULATIVE_DATA__;
            var totalPlugin = {
                id: 'cumulativeTotals',
                afterDatasetsDraw: function(chart) {
                    var ctx = chart.ctx;
                    var ds = chart.data.datasets;
                    var meta0 = chart.getDatasetMeta(0);
                    for (var i = 0; i < meta0.data.length; i++) {
                        var total = 0;
                        for (var d = 0; d < ds.length; d++) total += ds[d].data[i] || 0;
                        var lastMeta = chart.getDatasetMeta(ds.length - 1);
                        var bar = lastMeta.data[i];
                        if (!bar) continue;
                        ctx.save();
                        ctx.font = 'bold 11px sans-serif';
                        ctx.fillStyle = '#000';
                        ctx.textAlign = 'center';
                        ctx.textBaseline = 'bottom';
                        ctx.fillText(Math.round(total), bar.x, bar.y - 4);
                        ctx.restore();
                    }
                }
            };
            new Chart(document.getElementById('cumulativeAumChart'), {
                type: 'bar',
                data: {
                    labels: cData.dates.map(function(d) { return d.slice(5); }),
                    datasets: cData.datasets.map(function(ds) {
                        return { label: ds.label, data: ds.data, backgroundColor: ds.backgroundColor };
                    })
                },
                plugins: [totalPlugin],
                options: {
                    responsive: true, maintainAspectRatio: false,
                    layout: { padding: { top: 20 } },
                    plugins: {
                        legend: { position: 'bottom', labels: { font: { size: 11 }, color: '#000' } },
                        tooltip: { callbacks: {
                            title: function(ctxs) { return ctxs.length ? cData.dates[ctxs[0].dataIndex] : ''; },
                            label: function(ctx) { return ctx.dataset.label + ': ' + Math.round(ctx.raw) + '억'; }
                        } }
                    },
                    scales: {
                        x: { stacked: true, ticks: { font: { size: 11 }, color: '#000' }, grid: { display: false } },
                        y: { stacked: true, ticks: { callback: function(v) { return v + '억'; }, font: { size: 11 }, color: '#000' }, grid: { color: '#eee' } }
                    }
                }
            });
        })();
        </script>
        """.replace('__CUMULATIVE_DATA__', chart_json)

        return f"""
        <div style="margin-top:40px;max-width:1800px;margin:40px auto 0 auto;">
            <h3 style="font-size:18px;font-weight:700;margin-bottom:12px;">누적 AUM</h3>
            <div style="display:flex;gap:100px;align-items:flex-start;">
                <div style="width:370px;">
                    <table class="portfolio-table aum-aligned" style="white-space:nowrap;width:370px;table-layout:fixed;">
                        <colgroup>
                            <col style="width:60px"><col style="width:160px"><col style="width:80px"><col style="width:70px">
                        </colgroup>
                        <thead><tr>
                            <th>증권사</th>
                            <th>상품명</th>
                            <th>AUM</th>
                            <th>기준일</th>
                        </tr></thead>
                        <tbody>{cum_rows_html}</tbody>
                    </table>
                </div>
                <div style="flex:1;background:#fff;border-radius:12px;padding:20px;box-shadow:0 4px 6px rgba(0,0,0,0.1);">
                    <div style="position:relative;height:350px;"><canvas id="cumulativeAumChart"></canvas></div>
                </div>
            </div>
        </div>
        {chart_js}"""
    except Exception as e:
        print(f"Error creating cumulative AUM chart: {e}")
        return ""


def create_wrap_monthly_returns_table():
    """RETURN 섹션: 일반형 3종 + KOSPI/KOSDAQ 월별·연간 캘린더 (지표 토글: 수익률/MDD, 상품 토글).
    행=연도, 열=1~12월+연간. 수익률=월말 NAV(지수) 기준 월수익률, 연간=월수익률 복리(누적 NAV와 정확히 일치).
    MDD=월 내 최대낙폭(매월 고점 리셋, 일별 cummax), 연간=그 해 전체 최대낙폭(연 내 cummax). 부호 음수.
    상품: KOSPI / KOSDAQ / 삼성 트루밸류 / NH 다이내믹밸류 일반형(Value ESG) / DB 개방형(개방형 랩). 기본=KOSPI·수익률.
    KOSPI/KOSDAQ는 기준가 시트의 동일 컬럼(상단 RETURN 표와 동일 소스)을 사용.
    색상은 MONTHLY RETURNS 표와 동일(양수 빨강/음수 파랑, 강도 3단계)."""
    try:
        nav_file = 'Wrap_NAV.xlsx'
        if not os.path.exists(nav_file):
            return ''
        df = pd.read_excel(nav_file, sheet_name='기준가')
        if 'Date' not in df.columns:
            return ''
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date').sort_index()
        products = [('KOSPI', 'KOSPI'),
                    ('KOSDAQ', 'KOSDAQ'),
                    ('삼성 트루밸류', '트루밸류'),
                    ('NH 다이내믹밸류 일반형', 'Value ESG'),
                    ('DB 개방형', '개방형 랩')]
        MONTHS = list(range(1, 13))

        def color_bg(pct):
            a = abs(pct)
            if pct > 0:
                return '+', ('#ffe8e8' if a <= 5 else '#ffb8b8' if a <= 10 else '#ff7a7a')
            if pct < 0:
                return '', ('#e8edff' if a <= 5 else '#b8c5ff' if a <= 10 else '#7a90ff')
            return '', 'transparent'

        TH = ('padding:8px 4px;background:#f3f4f6;font-weight:700;text-align:center;'
              'border:1px solid #e5e7eb;font-size:12px;white-space:nowrap;')
        TD = ('padding:9px 4px;text-align:center;border:1px solid #e5e7eb;'
              'font-variant-numeric:tabular-nums;font-size:12px;color:#000;white-space:nowrap;')

        def build_body(years, month_map, annual_map, is_mdd):
            """연×월 캘린더 tbody. is_mdd=False: 연간=월수익률 복리. True: 연간=annual_map(연내 MDD)."""
            bdy = ''
            for y in years:
                row = f'<td style="{TD}font-weight:700;">{y}</td>'
                comp = 1.0
                has = False
                for m in MONTHS:
                    if m in month_map.get(y, {}):
                        pct = month_map[y][m]
                        sign, bg = color_bg(pct)
                        row += f'<td style="{TD}background:{bg};">{sign}{pct:.1f}%</td>'
                        comp *= (1 + pct / 100)
                        has = True
                    else:
                        row += f'<td style="{TD}">&nbsp;</td>'
                if not has:
                    ann = None
                elif is_mdd:
                    ann = annual_map.get(y)
                else:
                    ann = (comp - 1) * 100
                if ann is not None:
                    sign, bg = color_bg(ann)
                    row += (f'<td style="{TD}font-weight:700;background:{bg};'
                            f'border-left:2px solid #1f2937;">{sign}{ann:.1f}%</td>')
                else:
                    row += f'<td style="{TD}border-left:2px solid #1f2937;">&nbsp;</td>'
                bdy += f'<tr>{row}</tr>'
            return bdy

        latest = df.index.max().strftime('%Y-%m-%d')
        panels = ''
        buttons = ''
        rendered = 0
        for i, (disp, col) in enumerate(products):
            if col not in df.columns:
                continue
            s = df[col].dropna()
            if s.empty:
                continue
            me = s.resample('ME').last().dropna()
            prev = float(s.iloc[0])  # 인셉션 NAV(=1000) 기준 첫 부분월
            monthly = {}
            for dt, v in me.items():
                monthly.setdefault(dt.year, {})[dt.month] = (float(v) / prev - 1) * 100
                prev = float(v)
            years = sorted(monthly)
            # 월별 MDD(월 내 최대낙폭, 매월 고점 리셋) + 연간 MDD(연 내 최대낙폭). 부호 음수.
            mdd_monthly = {}
            for (yy, mm), grp in s.groupby([s.index.year, s.index.month]):
                mdd_monthly.setdefault(yy, {})[mm] = float(((grp / grp.cummax() - 1.0) * 100.0).min())
            mdd_annual = {}
            for yy, grp in s.groupby(s.index.year):
                mdd_annual[yy] = float(((grp / grp.cummax() - 1.0) * 100.0).min())
            head = f'<th style="{TH}width:52px;">연도</th>'
            head += ''.join(f'<th style="{TH}">{m}월</th>' for m in MONTHS)
            head += f'<th style="{TH}border-left:2px solid #1f2937;">연간</th>'
            body_ret = build_body(years, monthly, None, False)
            body_mdd = build_body(years, mdd_monthly, mdd_annual, True)
            for metric, bdy in (('ret', body_ret), ('mdd', body_mdd)):
                vis = 'block' if (rendered == 0 and metric == 'ret') else 'none'
                panels += (f'<div class="wmr-panel" data-prod="{i}" data-metric="{metric}" '
                           f'style="display:{vis};overflow-x:auto;">'
                           f'<table style="border-collapse:collapse;width:100%;'
                           f'font-family:inherit;table-layout:fixed;">'
                           f'<thead><tr>{head}</tr></thead><tbody>{bdy}</tbody></table></div>')
            btn_cls = 'wmr-btn wmr-btn-active' if rendered == 0 else 'wmr-btn'
            buttons += f'<button class="{btn_cls}" data-prod="{i}" onclick="showWmr({i})">{disp}</button>'
            rendered += 1

        if rendered == 0:
            return ''

        metric_buttons = (
            '<button class="wmr-mbtn wmr-mbtn-active" data-metric="ret" '
            "onclick=\"showWmrMetric('ret')\">수익률</button>"
            '<button class="wmr-mbtn" data-metric="mdd" '
            "onclick=\"showWmrMetric('mdd')\">MDD</button>")
        style = ('<style>.wmr-btn{font-family:inherit;font-size:13px;font-weight:600;padding:6px 14px;'
                 'border:1px solid #d1d5db;background:#f9fafb;color:#555;border-radius:8px;cursor:pointer;}'
                 '.wmr-btn-active{background:#374151;color:#fff;border-color:#374151;}'
                 '.wmr-mbtn{font-family:inherit;font-size:13px;font-weight:600;padding:5px 14px;'
                 'border:1px solid #d1d5db;background:#f9fafb;color:#555;border-radius:8px;cursor:pointer;}'
                 '.wmr-mbtn-active{background:#0072CE;color:#fff;border-color:#0072CE;}</style>')
        script = ('<script>var wmrProd=0,wmrMetric="ret";'
                  'function wmrApply(){'
                  "document.querySelectorAll('.wmr-panel').forEach(function(p){"
                  "p.style.display=(p.getAttribute('data-prod')==String(wmrProd)"
                  "&&p.getAttribute('data-metric')==wmrMetric)?'block':'none';});}"
                  'function showWmr(i){wmrProd=i;'
                  "document.querySelectorAll('.wmr-btn').forEach(function(b){"
                  "b.classList.toggle('wmr-btn-active', b.getAttribute('data-prod')==String(i));});wmrApply();}"
                  'function showWmrMetric(m){wmrMetric=m;'
                  "document.querySelectorAll('.wmr-mbtn').forEach(function(b){"
                  "b.classList.toggle('wmr-mbtn-active', b.getAttribute('data-metric')==m);});wmrApply();}</script>")
        card = (f'<div style="max-width:1000px;margin:22px auto 0;background:#fff;border-radius:10px;'
                f'padding:16px 20px;box-shadow:0 2px 4px rgba(0,0,0,0.08);">'
                f'<div style="display:flex;align-items:center;justify-content:space-between;'
                f'margin-bottom:12px;flex-wrap:wrap;gap:8px;">'
                f'<div style="font-weight:700;font-size:15px;">월별 수익률</div>'
                f'<div style="display:flex;gap:6px;">{metric_buttons}</div></div>'
                f'{style}'
                f'<div style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap;">{buttons}</div>'
                f'{panels}</div>')
        return card + script
    except Exception as e:
        print(f"Error creating wrap monthly returns table: {e}")
        return ''


def create_wrap_returns_table():
    """WRAP 수익률 비교 테이블 HTML (삼성 트루밸류, KOSPI, KOSDAQ) - 날짜 필터 포함"""
    try:
        nav_file = 'Wrap_NAV.xlsx'
        if not os.path.exists(nav_file):
            return ""

        df_returns = pd.read_excel(nav_file, sheet_name='수익률')
        if df_returns.empty:
            return ""

        items = [
            ('KOSPI', 'KOSPI'),
            ('KOSDAQ', 'KOSDAQ'),
            ('삼성 트루밸류', '트루밸류'),
            ('NH 목표전환형 4호', '목표전환형 4호'),  # 운용 개시 2026-06-15 (DB 5차 페어, 동일 구성)
            ('DB 목표전환형 5차', '목표전환형 5차'),  # 운용 개시 2026-06-12 (NH 4호 페어)
            # ('NH 목표전환형 3호', '목표전환형 3호'),  # NH 3호 완료 (2026-05-27 청산, 목표달성)
            # ('DB 목표전환형 4차', '목표전환형 4차'),  # DB 4차 완료 (2026-05-27 청산, 목표달성)
            # ('NH 목표전환형 2호', '목표전환형 2호'),  # NH 2호 완료 (2026-05-06, +7.26%, 목표 6.5% 초과)
        ]
        periods = ['1D', '1W', '1M', '3M', '6M', '1Y', '3Y', 'YTD', 'DD']

        # 모든 날짜-데이터 수집
        all_data = {}
        date_list = []
        for _, row in df_returns.iterrows():
            date_str = str(row.get('날짜', ''))[:10]
            if not date_str or date_str == 'nan':
                continue
            row_data = {}
            for _, key in items:
                for p in periods:
                    col = f'{key}_{p}'
                    val = row.get(col)
                    row_data[col] = None if (val is None or (isinstance(val, float) and pd.isna(val))) else str(val)
            all_data[date_str] = row_data
            date_list.append(date_str)

        if not date_list:
            return ""

        latest_date = date_list[-1]
        earliest_date = date_list[0]

        def cell_td(val, cell_id, divider=False):
            s = val if val and val != 'nan' and val != 'None' else ''
            divider_cls = ' rt-divider-left' if divider else ''
            if not s:
                return f'<td id="{cell_id}" class="rt-cell rt-na{divider_cls}">-</td>'
            try:
                num = float(s.replace('%', '').strip())
                cls = 'rt-pos' if num > 0 else 'rt-neg' if num < 0 else 'rt-zero'
            except Exception:
                cls = ''
            return f'<td id="{cell_id}" class="rt-cell {cls}{divider_cls}">{s}</td>'

        latest_row = all_data.get(latest_date, {})
        rows_html = ''
        for display_name, key in items:
            rows_html += f'<tr><td class="rt-name">{display_name}</td>'
            for p in periods:
                rows_html += cell_td(latest_row.get(f'{key}_{p}'), f'rt-{key}-{p}', divider=(p == 'YTD'))
            rows_html += '</tr>\n'

        headers = ''.join(
            f'<th class="rt-ph rt-divider-left">{p}</th>' if p == 'YTD' else f'<th class="rt-ph">{p}</th>'
            for p in periods
        )
        data_json = json.dumps(all_data, ensure_ascii=False)
        # sorted date list for floor-lookup in JS
        dates_sorted_json = json.dumps(sorted(date_list))
        items_json = json.dumps([[d, k] for d, k in items], ensure_ascii=False)
        periods_json = json.dumps(periods)
        monthly_card = create_wrap_monthly_returns_table()

        return f"""
        <div class="category-section">
            <h2 class="category-title">RETURN</h2>
            <div style="max-width:1000px;margin:0 auto;background:#fff;border-radius:10px;padding:16px 20px;box-shadow:0 2px 4px rgba(0,0,0,0.08);">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;">
                    <span style="font-size:13px;color:#555;font-weight:600;">기준일</span>
                    <button onclick="shiftReturnDate(-1)" style="border:1px solid #d1d5db;background:#f9fafb;border-radius:6px;padding:2px 8px;cursor:pointer;font-size:12px;color:#555;">&lt;</button>
                    <span id="return-date-display" style="font-size:13px;padding:4px 12px;border:1px solid #d1d5db;border-radius:6px;background:#f9fafb;color:#222;">{latest_date}</span>
                    <button onclick="shiftReturnDate(1)" style="border:1px solid #d1d5db;background:#f9fafb;border-radius:6px;padding:2px 8px;cursor:pointer;font-size:12px;color:#555;">&gt;</button>
                    <span id="return-actual-date-label" style="font-size:12px;color:#888;"></span>
                </div>
                <table class="rt-table">
                    <thead>
                        <tr><th class="rt-nh"></th>{headers}</tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                </table>
            </div>
            {monthly_card}
        </div>
        <script>
        (function() {{
            var returnData = {data_json};
            var rtDatesSorted = {dates_sorted_json};
            var rtItems = {items_json};
            var rtPeriods = {periods_json};

            function floorDate(selected) {{
                // 선택 날짜 이하의 가장 가까운 데이터 날짜 반환
                var found = null;
                for (var i = rtDatesSorted.length - 1; i >= 0; i--) {{
                    if (rtDatesSorted[i] <= selected) {{
                        found = rtDatesSorted[i];
                        break;
                    }}
                }}
                return found;
            }}

            function applyRow(dataDate) {{
                var label = document.getElementById('return-actual-date-label');
                var row = dataDate ? (returnData[dataDate] || {{}}) : {{}};
                if (dataDate) {{
                    label.textContent = '(데이터: ' + dataDate + ')';
                    label.style.display = '';
                }} else {{
                    label.textContent = '데이터 없음';
                    label.style.display = '';
                }}
                rtItems.forEach(function(item) {{
                    var key = item[1];
                    rtPeriods.forEach(function(p) {{
                        var col = key + '_' + p;
                        var cid = 'rt-' + key + '-' + p;
                        var cell = document.getElementById(cid);
                        if (!cell) return;
                        var val = row[col];
                        var dividerCls = (p === 'YTD') ? ' rt-divider-left' : '';
                        if (!val || val === 'nan') {{
                            cell.className = 'rt-cell rt-na' + dividerCls;
                            cell.textContent = '-';
                        }} else {{
                            var num = parseFloat(val.replace('%', '').trim());
                            var cls = 'rt-cell';
                            if (!isNaN(num)) {{
                                cls += num > 0 ? ' rt-pos' : num < 0 ? ' rt-neg' : ' rt-zero';
                            }}
                            cell.className = cls + dividerCls;
                            cell.textContent = val;
                        }}
                    }});
                }});
            }}

            var currentRtIdx = rtDatesSorted.length - 1;

            function showDate(idx) {{
                if (idx < 0 || idx >= rtDatesSorted.length) return;
                currentRtIdx = idx;
                var d = rtDatesSorted[idx];
                document.getElementById('return-date-display').textContent = d;
                document.getElementById('return-actual-date-label').style.display = 'none';
                applyRow(d);
            }}

            window.shiftReturnDate = function(dir) {{
                var next = currentRtIdx + dir;
                if (next >= 0 && next < rtDatesSorted.length) showDate(next);
            }};

            // 초기 로드
            document.getElementById('return-actual-date-label').style.display = 'none';
        }})();
        </script>"""
    except Exception as e:
        print(f"Error creating wrap returns table: {e}")
        return ""


def create_order_section():
    """ORDER 패널 — WRAP 페이지 'Order' 탭 안의 콘텐츠.

    fetch portfolio_data.json + ExcelJS 클라이언트 사이드 처리 (journal.html 검증된 패턴).

    UX:
      - 1개 포트폴리오 버튼 (트루밸류/NH Value ESG/DB 개방형 묶음)
      - 각 버튼 클릭 시 종목 테이블: 변경전(read-only), 변경후(input), 주문구분(자동), 추천사유(input)
      - Download(빨간) → 자문지/ 템플릿 fetch → R7부터 F/G/H/I 셀 patch → .xlsx 다운로드
      - NH 3호+DB 4차 페어 청산(2026-05-27, 목표달성)으로 NH/DB 페어 모두 비활성. 다음 페어 출시 시 ORDER_PORTFOLIOS 재추가.
    """
    return """
        <div id="orderTabs" style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;"></div>
        <div id="orderContent"><div style="text-align:center;color:#888;padding:40px;">로딩 중...</div></div>
        <script src="https://cdn.jsdelivr.net/npm/exceljs/dist/exceljs.min.js"></script>
        <script>
        // 일반형 3개는 종목/비중 동일 → 한 테이블 + 3개 Download 버튼
        // 목표전환형은 주문 시점이 다를 수 있어 별도 카드 유지
        // newSheetTargets: 저장 시 Wrap_NAV.xlsx의 NEW 시트에 행을 추가할 (증권사, 상품명) 매핑
        // 일반형 카드 → 3개 상품(삼성 트루밸류 / NH Value ESG / DB 개방형) 모두에 동일 종목/비중 행 추가
        // 목표전환형 카드 → 1개 상품에만 추가
        var ORDER_PORTFOLIOS = [
            {
                display: '삼성 트루밸류 / NH Value ESG / DB 개방형',
                jsonKey: '삼성 트루밸류 / NH Value ESG / DB 개방형',
                templates: [
                    { label: '삼성 트루밸류',  file: '자문지/라이프자산운용_트루밸류_260427.xlsx' },
                    { label: 'NH Value ESG',  file: '자문지/라이프자산운용_라이프 다이내믹밸류_일반형 _2026.4.27.xlsx' },
                    { label: 'DB 개방형',     file: '자문지/라이프자산운용_DB 개방형 랩 _2026.4.27.xlsx' },
                ],
                newSheetTargets: [
                    { broker: '삼성', product: '트루밸류' },
                    { broker: 'NH',   product: 'Value ESG' },
                    { broker: 'DB',   product: '개방형 랩' },
                ],
            },
            {
                display: 'DB 목표전환형 5차',  // DB 5차(운용 개시 2026-06-12). NH 4호와 동일 구성, 증권사·주문 분리 → 별도 탭. (사용자 지정 순서: DB 5차 앞)
                jsonKey: 'NH 목표전환형 4호 / DB 목표전환형 5차',
                templates: [
                    { label: 'DB 목표전환형 5차', file: '자문지/라이프자산운용_DB 목표전환형 랩 _5차_2026.6.12.xlsx' },
                ],
                newSheetTargets: [
                    { broker: 'DB', product: '목표전환형 5차' },
                ],
            },
            {
                display: 'NH 목표전환형 4호',  // NH 4호(운용 개시 2026-06-15). DB 5차와 동일 종목/비중이나 증권사·주문 분리 → 별도 탭. 보유종목은 combined 키 공유.
                jsonKey: 'NH 목표전환형 4호 / DB 목표전환형 5차',
                templates: [
                    { label: 'NH 목표전환형 4호', file: '자문지/라이프자산운용_라이프 다이내믹밸류_목표전환형 4호_2026.6.15.xlsx' },
                ],
                newSheetTargets: [
                    { broker: 'NH', product: '목표전환형 4호' },
                ],
            },
        ];
        var orderState = {};
        var orderStocks = {};
        var orderActiveTab = null;
        var _orderLoaded = false;

        async function loadOrder() {
            if (_orderLoaded) return;
            _orderLoaded = true;
            try {
                var res = await fetch('portfolio_data.json?_=' + Date.now());
                if (!res.ok) throw new Error('portfolio_data.json fetch 실패: ' + res.status);
                var pdata = await res.json();
                ORDER_PORTFOLIOS.forEach(function(p) {
                    var stocks = pdata[p.jsonKey] || [];
                    // "변경전"은 D-1 기준(weight_prev) — 오늘 finalize된 행 직전 비중.
                    // 모든 PC가 finalize 후에도 동일하게 "변경 이력" 화면을 보게 됨 (자정 지나면 자동 리셋).
                    // weight_prev 누락 시(구버전 portfolio_data.json) 또는 신규 편입 시: weight 자체 fallback.
                    orderStocks[p.display] = stocks.map(function(s) {
                        var origW = parseFloat(s.weight) || 0;
                        var prevW = (s.weight_prev != null) ? (parseFloat(s.weight_prev) || 0) : origW;
                        return { code: s.code, name: s.name, sector: s.sector || '', weight: prevW };
                    });
                    orderState[p.display] = stocks.map(function(s) {
                        return { newWeight: parseFloat(s.weight) || 0, reason: '' };
                    });
                });

                // 오늘자 임시저장본(pending_orders.json) 화면 복원
                try {
                    var pendingRes = await fetch('orders/pending_orders.json?_=' + Date.now());
                    if (pendingRes.ok) {
                        var pending = await pendingRes.json();
                        var dNow = new Date();
                        var todayStr = dNow.getFullYear() + '-'
                            + String(dNow.getMonth() + 1).padStart(2, '0') + '-'
                            + String(dNow.getDate()).padStart(2, '0');
                        var todayPending = pending && pending[todayStr];
                        if (todayPending) {
                            ORDER_PORTFOLIOS.forEach(function(p) {
                                var entry = todayPending[p.display];
                                if (!entry || !Array.isArray(entry.stocks)) return;
                                var savedByCode = {};
                                entry.stocks.forEach(function(s) {
                                    if (s && s.code != null) savedByCode[String(s.code).trim()] = s;
                                });
                                var newStocks = [];
                                var newStates = [];
                                var consumed = {};
                                // portfolio_data 기존 종목: 저장본 있으면 newWeight + reason 복원, 없으면 미저장 (원본 유지)
                                orderStocks[p.display].forEach(function(s) {
                                    var key = String(s.code || '').trim();
                                    var saved = key && savedByCode[key];
                                    newStocks.push(s);
                                    if (saved) {
                                        consumed[key] = true;
                                        newStates.push({
                                            newWeight: parseFloat(saved.weight) || 0,
                                            reason: (saved.reason || '').toString()
                                        });
                                    } else {
                                        // 저장본에 없음 = 미저장 (원본 비중 유지)
                                        newStates.push({ newWeight: s.weight, reason: '' });
                                    }
                                });
                                // 저장본에만 있는 신규 종목 (사용자가 추가한 것) append
                                entry.stocks.forEach(function(s) {
                                    var key = String(s.code || '').trim();
                                    if (!key || consumed[key]) return;
                                    newStocks.push({
                                        code: s.code,
                                        name: s.name || '',
                                        sector: s.sector || '',
                                        weight: 0,
                                        isNew: true
                                    });
                                    newStates.push({
                                        newWeight: parseFloat(s.weight) || 0,
                                        reason: (s.reason || '').toString()
                                    });
                                });
                                orderStocks[p.display] = newStocks;
                                orderState[p.display] = newStates;
                            });
                        }
                    }
                } catch (e) {
                    console.warn('pending_orders.json 복원 실패 (무시):', e);
                }

                renderOrderTabs();
                switchOrderTab(ORDER_PORTFOLIOS[0].display);
            } catch(e) {
                document.getElementById('orderContent').innerHTML = '<div style="color:#dc2626;padding:40px;">데이터 로드 실패: ' + e.message + '</div>';
                console.error('loadOrder error:', e);
            }
        }

        function calcOrderType(oldW, newW) {
            if (oldW === newW) return '유지';
            if (oldW === 0 && newW > 0) return '신규 편입';
            if (newW === 0 && oldW > 0) return '전량 편출';
            if (newW > oldW) return '비중 확대';
            return '비중 축소';
        }

        // 다운로드 파일명: 자문지 폴더의 기존 파일명 패턴에 맞춰 오늘 날짜로 치환
        // - YYMMDD 패턴 (예: _260427.xlsx)
        // - YYYY.M.D 패턴 (예: _2026.4.27.xlsx)
        function buildOutFilename(template, date) {
            var fname = template.file.split('/').pop();
            var yy = (date.getFullYear() % 100).toString().padStart(2, '0');
            var mm = (date.getMonth() + 1).toString().padStart(2, '0');
            var dd = date.getDate().toString().padStart(2, '0');
            var yymmdd = yy + mm + dd;
            var yyyymdd = date.getFullYear() + '.' + (date.getMonth() + 1) + '.' + date.getDate();
            // 우선순위: YYYY.M.D 매칭 후 YYMMDD
            if (/_\d{4}\.\d{1,2}\.\d{1,2}\.xlsx$/.test(fname)) {
                fname = fname.replace(/_\d{4}\.\d{1,2}\.\d{1,2}\.xlsx$/, '_' + yyyymdd + '.xlsx');
            } else if (/_\d{6}\.xlsx$/.test(fname)) {
                fname = fname.replace(/_\d{6}\.xlsx$/, '_' + yymmdd + '.xlsx');
            }
            return fname;
        }

        function renderOrderTabs() {
            var html = '';
            ORDER_PORTFOLIOS.forEach(function(p) {
                html += '<button class="order-pf-btn" data-pf="' + p.display + '" style="font-family:inherit;font-size:14px;font-weight:600;padding:8px 16px;background:#f3f4f6;color:#444;border:none;border-radius:8px;cursor:pointer;">' + p.display + '</button>';
            });
            // Email 탭 (모든 이메일 텍스트 모음)
            html += '<button class="order-pf-btn" data-pf="Email" style="font-family:inherit;font-size:14px;font-weight:600;padding:8px 16px;background:#f3f4f6;color:#444;border:none;border-radius:8px;cursor:pointer;">Email</button>';
            document.getElementById('orderTabs').innerHTML = html;
            document.querySelectorAll('.order-pf-btn').forEach(function(b) {
                b.addEventListener('click', function() { switchOrderTab(b.dataset.pf); });
            });
        }

        function switchOrderTab(pfName) {
            orderActiveTab = pfName;
            document.querySelectorAll('.order-pf-btn').forEach(function(b) {
                var active = b.dataset.pf === pfName;
                b.style.background = active ? '#222' : '#f3f4f6';
                b.style.color = active ? '#fff' : '#444';
            });
            if (pfName === 'Email') {
                renderEmailPanel();
            } else {
                renderOrderPanel(pfName);
            }
        }

        function buildEmailBox(title, text, bgColor, borderColor, titleColor, btnBg) {
            return '<div style="margin-top:16px;padding:16px;background:' + bgColor + ';border:1px solid ' + borderColor + ';border-radius:8px;">'
                + '<div style="display:flex;align-items:center;margin-bottom:12px;">'
                + '<h4 style="margin:0;font-size:15px;color:' + titleColor + ';">' + title + '</h4>'
                + '<button class="email-tab-copy-btn" data-bg="' + btnBg + '" style="margin-left:auto;font-family:inherit;font-size:13px;font-weight:600;padding:5px 14px;background:' + btnBg + ';color:#fff;border:none;border-radius:6px;cursor:pointer;">복사</button>'
                + '</div>'
                + '<pre class="email-tab-text" style="white-space:pre-wrap;font-family:\\'맑은 고딕\\', \\'Malgun Gothic\\', \\'Inter\\', \\'Noto Sans KR\\', sans-serif;font-size:13px;color:#222;margin:0;line-height:1.6;"><span style="font-family:\\'맑은 고딕\\', \\'Malgun Gothic\\', sans-serif;font-size:13px;color:#222;">' + escapeHtml(text) + '</span></pre>'
                + '</div>';
        }

        function renderEmailPanel() {
            var GENERAL = '삼성 트루밸류 / NH Value ESG / DB 개방형';
            var NH = 'NH 목표전환형 4호';
            var compliance = buildComplianceEmailText();
            var samsung = buildOrderEmailText(GENERAL, orderStocks[GENERAL] || [], orderState[GENERAL] || []);
            var nh = buildOrderEmailText(NH, orderStocks[NH] || [], orderState[NH] || []);
            // 네이트온 (NH 이메일 밑) — 일반형 + 목표전환형 한 박스
            // ORDER 탭 분리(NH 4호 / DB 5차) 후 둘은 동일 구성이라 한쪽(DB 5차)을 목표전환형 소스로 사용
            var TGT = 'DB 목표전환형 5차';
            var nateonText = buildOrderNateonText(orderStocks[GENERAL] || [], orderState[GENERAL] || [], '일반형')
                + '\\n\\n'
                + buildOrderNateonText(orderStocks[TGT] || [], orderState[TGT] || [], '목표전환형');
            var nateonReasonLines = buildNateonReasonLines([GENERAL, TGT]);
            if (nateonReasonLines.length) nateonText += '\\n\\n' + nateonReasonLines.join('\\n');
            // 다운로드 섹션 (증권사 순서: 삼성 → NH → DB, 색상도 증권사별)
            var BROKER_ORDER = { '삼성': 0, 'NH': 1, 'DB': 2 };
            var BROKER_COLOR = { '삼성': '#1428A0', 'NH': '#0072CE', 'DB': '#00854A' };
            function brokerKey(label) {
                if (label.indexOf('삼성') === 0) return '삼성';
                if (label.indexOf('NH') === 0) return 'NH';
                if (label.indexOf('DB') === 0) return 'DB';
                return 'zz';
            }
            var dlItems = [];
            ORDER_PORTFOLIOS.forEach(function(p) {
                (p.templates || []).forEach(function(t, ti) {
                    var btnLabel = t.label || ('Download' + (p.templates.length > 1 ? ' ' + (ti + 1) : ''));
                    dlItems.push({ pf: p.display, ti: ti, t: t, label: btnLabel, broker: brokerKey(btnLabel) });
                });
            });
            dlItems.sort(function(a, b) {
                var oa = (BROKER_ORDER[a.broker] != null) ? BROKER_ORDER[a.broker] : 999;
                var ob = (BROKER_ORDER[b.broker] != null) ? BROKER_ORDER[b.broker] : 999;
                return oa - ob;
            });
            var dlRows = '';
            var prevBroker = null;
            dlItems.forEach(function(it) {
                if (prevBroker && it.broker !== prevBroker) {
                    dlRows += '<hr style="border:none;border-top:1px solid #9ca3af;width:160px;margin:10px 0 10px auto;">';
                }
                prevBroker = it.broker;
                var outName = buildOutFilename(it.t, new Date());
                var btnColor = BROKER_COLOR[it.broker] || '#dc2626';
                dlRows += '<div style="display:flex;align-items:center;justify-content:flex-end;gap:12px;margin-bottom:8px;">'
                    + '<span style="font-size:13px;color:#666;font-family:\\'Pretendard Variable\\', Pretendard, sans-serif;">' + outName + ' →</span>'
                    + '<button class="email-tab-dl-btn" data-pf="' + it.pf + '" data-tidx="' + it.ti + '" style="font-family:inherit;font-size:14px;font-weight:600;padding:6px 14px;background:' + btnColor + ';color:#fff;border:none;border-radius:8px;cursor:pointer;min-width:160px;text-align:center;">' + it.label + '</button>'
                    + '</div>';
            });
            var dlSection = '<div style="margin-bottom:8px;padding:16px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;">'
                + '<h4 style="margin:0 0 12px 0;font-size:15px;color:#444;">자문지 다운로드</h4>'
                + dlRows
                + '</div>';
            var html = '<div style="max-width:720px;margin:0 auto;background:#fff;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.06);">'
                + dlSection
                + buildEmailBox('컴플라이언스 이메일', compliance, '#fffbeb', '#fef3c7', '#92400e', '#d97706')
                + buildEmailBox('삼성 이메일', samsung, '#f9fafb', '#e5e7eb', '#444', '#374151')
                + buildEmailBox('NH 이메일', nh, '#f9fafb', '#e5e7eb', '#444', '#374151')
                + buildEmailBox('네이트온 (NH)', nateonText, '#eef2ff', '#c7d2fe', '#1f5a2a', '#4f46e5')
                + '</div>';
            document.getElementById('orderContent').innerHTML = html;
            document.querySelectorAll('#orderContent .email-tab-dl-btn').forEach(function(btn) {
                btn.addEventListener('click', function() {
                    downloadOrderExcel(btn.dataset.pf, parseInt(btn.dataset.tidx));
                });
            });
            document.querySelectorAll('#orderContent .email-tab-copy-btn').forEach(function(btn) {
                btn.addEventListener('click', function() {
                    var section = btn.parentElement.parentElement;
                    var pre = section.querySelector('.email-tab-text');
                    if (!pre) return;
                    navigator.clipboard.writeText(pre.textContent).then(function() {
                        var original = btn.textContent;
                        btn.textContent = '복사됨';
                        btn.style.background = '#16a34a';
                        setTimeout(function() {
                            btn.textContent = original;
                            btn.style.background = btn.dataset.bg || '#374151';
                        }, 1500);
                    }).catch(function(err) { alert('복사 실패: ' + err.message); });
                });
            });
        }

        function buildOrderChanges(stocks, st) {
            var newBuy = [], inc = [], dec = [], out = [];
            stocks.forEach(function(s, i) {
                var oldW = parseFloat(s.weight) || 0;
                var newW = parseFloat(st[i] && st[i].newWeight) || 0;
                var name = (s.name || '').trim();
                if (!name) return;
                if (oldW === 0 && newW > 0) newBuy.push(name);
                else if (oldW > 0 && newW === 0) out.push(name);
                else if (oldW > 0 && newW > oldW) inc.push(name);
                else if (oldW > 0 && newW < oldW) dec.push(name);
            });
            return { newBuy: newBuy, inc: inc, dec: dec, out: out };
        }

        function buildEmailSectionLines(changes, headerLabel) {
            // headerLabel 있으면 `[label]` 만 (주요 내용 줄 생략 — 이미 라벨로 구분됨)
            // headerLabel 없으면 `[주요 내용]`
            function fmt(arr) { return arr.length ? arr.join(', ') : '없음'; }
            var lines = [];
            if (headerLabel) {
                lines.push('[' + headerLabel + ']');
            } else {
                lines.push('[주요 내용]');
            }
            lines.push('신규 편입: ' + fmt(changes.newBuy));
            lines.push('비중 확대: ' + fmt(changes.inc));
            lines.push('비중 축소: ' + fmt(changes.dec));
            lines.push('전량 편출: ' + fmt(changes.out));
            return lines;
        }

        function buildOrderEmailText(pfName, stocks, st) {
            // 일반형 + NH 목표전환형 통합 이메일 (NH 4호 탭에서 활성화)
            var TARGET_TABS = ['NH 목표전환형 4호'];
            var GENERAL = '삼성 트루밸류 / NH Value ESG / DB 개방형';
            var lines = [
                '안녕하십니까.',
                '라이프자산운용 김태식입니다.',
                '',
                '랩 자문지 보내드립니다.',
                '주요 변경 내용은 다음과 같습니다.',
                ''
            ];
            if (TARGET_TABS.indexOf(pfName) >= 0) {
                var generalChanges = buildOrderChanges(orderStocks[GENERAL] || [], orderState[GENERAL] || []);
                var targetChanges = buildOrderChanges(stocks, st);
                lines = lines.concat(buildEmailSectionLines(generalChanges, '일반형'));
                lines.push('');
                lines = lines.concat(buildEmailSectionLines(targetChanges, '목표전환형'));
            } else {
                var changes = buildOrderChanges(stocks, st);
                lines = lines.concat(buildEmailSectionLines(changes, null));
            }
            lines.push('');
            lines.push('감사합니다.');
            return lines.join('\\n');
        }

        function escapeHtml(s) {
            return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }

        function buildOrderEmailSection(pfName, stocks, st) {
            var emailText = buildOrderEmailText(pfName, stocks, st);
            return '<div style="margin-top:24px;padding:16px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;">'
                + '<div style="display:flex;align-items:center;margin-bottom:12px;">'
                + '<h4 style="margin:0;font-size:15px;color:#444;">이메일 텍스트</h4>'
                + '<button class="email-copy-btn" style="margin-left:auto;font-family:inherit;font-size:13px;font-weight:600;padding:5px 14px;background:#374151;color:#fff;border:none;border-radius:6px;cursor:pointer;">복사</button>'
                + '</div>'
                + '<pre class="email-text" style="white-space:pre-wrap;font-family:inherit;font-size:14px;color:#222;margin:0;line-height:1.6;">' + escapeHtml(emailText) + '</pre>'
                + '</div>';
        }

        function buildComplianceEmailText() {
            // 일반형 + 목표전환형(NH 4호 / DB 5차 페어) 통합
            var GENERAL = '삼성 트루밸류 / NH Value ESG / DB 개방형';
            var TARGET = 'DB 목표전환형 5차';
            var gen = buildOrderChanges(orderStocks[GENERAL] || [], orderState[GENERAL] || []);
            var tgt = buildOrderChanges(orderStocks[TARGET] || [], orderState[TARGET] || []);
            function dedupe(a, b) {
                var seen = {}, out = [];
                a.concat(b).forEach(function(name) {
                    if (!seen[name]) { seen[name] = true; out.push(name); }
                });
                return out;
            }
            var combined = {
                newBuy: dedupe(gen.newBuy, tgt.newBuy),
                inc:    dedupe(gen.inc,    tgt.inc),
                dec:    dedupe(gen.dec,    tgt.dec),
                out:    dedupe(gen.out,    tgt.out)
            };
            var lines = [
                '안녕하십니까.',
                '라이프자산운용 김태식입니다.',
                '',
                '랩 자문지 보내드립니다.',
                '주요 변경 내용은 다음과 같습니다.',
                ''
            ].concat(buildEmailSectionLines(combined, null)).concat(['', '감사합니다.']);
            return lines.join('\\n');
        }

        function buildComplianceEmailSection(pfName) {
            // 일반형 탭에서만 노출 (개방형 + 목표전환형 통합본)
            if (pfName !== '삼성 트루밸류 / NH Value ESG / DB 개방형') return '';
            var text = buildComplianceEmailText();
            return '<div style="margin-top:16px;padding:16px;background:#fffbeb;border:1px solid #fef3c7;border-radius:8px;">'
                + '<div style="display:flex;align-items:center;margin-bottom:12px;">'
                + '<h4 style="margin:0;font-size:15px;color:#92400e;">컴플라이언스 이메일 텍스트</h4>'
                + '<button class="compliance-copy-btn" style="margin-left:auto;font-family:inherit;font-size:13px;font-weight:600;padding:5px 14px;background:#d97706;color:#fff;border:none;border-radius:6px;cursor:pointer;">복사</button>'
                + '</div>'
                + '<pre class="compliance-text" style="white-space:pre-wrap;font-family:inherit;font-size:14px;color:#222;margin:0;line-height:1.6;">' + escapeHtml(text) + '</pre>'
                + '</div>';
        }

        function buildOrderNateonText(stocks, st, headerLabel) {
            var newBuy = [], inc = [], dec = [], out = [];
            stocks.forEach(function(s, i) {
                var oldW = parseFloat(s.weight) || 0;
                var newW = parseFloat(st[i] && st[i].newWeight) || 0;
                var name = (s.name || '').trim();
                if (!name) return;
                if (oldW === 0 && newW > 0) newBuy.push({ name: name, weight: newW });
                else if (oldW > 0 && newW === 0) out.push({ name: name, weight: 0 });
                else if (oldW > 0 && newW > oldW) inc.push({ name: name, weight: newW });
                else if (oldW > 0 && newW < oldW) dec.push({ name: name, weight: newW });
            });
            function fmtList(arr) {
                return arr.map(function(x) { return x.name + ' ' + x.weight + '%'; }).join(' ');
            }
            var lines = ['[' + headerLabel + ']'];
            if (newBuy.length) lines.push('신규편입: ' + fmtList(newBuy));
            if (inc.length) lines.push('비중확대: ' + fmtList(inc));
            if (dec.length) lines.push('비중축소: ' + fmtList(dec));
            if (out.length) lines.push('전량편출: ' + fmtList(out));
            return lines.join('\\n');
        }

        // 네이트온 박스 하단 사유 라인 빌드: 변동 있는 종목 + 사유 있는 것만, dedupe(code+name)
        function buildNateonReasonLines(pfNames) {
            var seen = {};
            var lines = [];
            pfNames.forEach(function(pfName) {
                var stocks = orderStocks[pfName] || [];
                var st = orderState[pfName] || [];
                stocks.forEach(function(s, i) {
                    var oldW = parseFloat(s.weight) || 0;
                    var newW = parseFloat(st[i] && st[i].newWeight) || 0;
                    if (oldW === newW) return;
                    var name = (s.name || '').trim();
                    if (!name) return;
                    var reason = ((st[i] && st[i].reason) || '').trim();
                    if (!reason) return;
                    var key = (s.code || '') + '_' + name;
                    if (seen[key]) return;
                    seen[key] = true;
                    lines.push(name + ' / ' + reason);
                });
            });
            return lines;
        }

        function buildOrderNateonSection(pfName) {
            // NH 목표전환형 4호 탭에서만 노출 (일반형 + 목표전환형을 한 박스에 함께)
            if (pfName !== 'NH 목표전환형 4호') return '';
            var GENERAL = '삼성 트루밸류 / NH Value ESG / DB 개방형';
            var generalText = buildOrderNateonText(orderStocks[GENERAL] || [], orderState[GENERAL] || [], '일반형');
            var targetText = buildOrderNateonText(orderStocks[pfName] || [], orderState[pfName] || [], '목표전환형');
            var combined = generalText + '\\n\\n' + targetText;
            var reasonLines = buildNateonReasonLines([GENERAL, pfName]);
            if (reasonLines.length) combined += '\\n\\n' + reasonLines.join('\\n');
            return '<div style="margin-top:16px;padding:16px;background:#eef2ff;border:1px solid #c7d2fe;border-radius:8px;">'
                + '<div style="display:flex;align-items:center;margin-bottom:12px;">'
                + '<h4 style="margin:0;font-size:15px;color:#1f5a2a;">네이트온 텍스트</h4>'
                + '<button class="nateon-copy-btn" style="margin-left:auto;font-family:inherit;font-size:13px;font-weight:600;padding:5px 14px;background:#4f46e5;color:#fff;border:none;border-radius:6px;cursor:pointer;">복사</button>'
                + '</div>'
                + '<pre class="nateon-text" style="white-space:pre-wrap;font-family:inherit;font-size:14px;color:#222;margin:0;line-height:1.6;">' + escapeHtml(combined) + '</pre>'
                + '</div>';
        }

        // 렌더링 직전 reason 자동 채움:
        // - 이 탭의 어떤 종목의 reason이 비어있고 주문구분이 '유지'가 아닐 때
        // - 다른 탭에서 같은 종목코드 + 같은 주문구분의 비어있지 않은 reason이 있으면 가져옴
        // → 일반형에서 입력한 reason이 목표전환형 탭에서 비중 축소로 바꿀 때 자동 표시
        function syncReasonFromOtherTabs(pfName) {
            var stocks = orderStocks[pfName] || [];
            var st = orderState[pfName] || [];
            stocks.forEach(function(s, i) {
                if (!s || !s.code) return;
                if (!st[i]) return;
                if ((st[i].reason || '').toString().trim()) return;
                var curType = calcOrderType(parseFloat(s.weight) || 0,
                                            parseFloat(st[i].newWeight) || 0);
                if (curType === '유지') return;
                var key = String(s.code).trim();
                var found = '';
                Object.keys(orderStocks).some(function(tab) {
                    if (tab === pfName) return false;
                    var arr = orderStocks[tab] || [];
                    var stArr = orderState[tab] || [];
                    for (var j = 0; j < arr.length; j++) {
                        var os = arr[j];
                        if (!os || String(os.code || '').trim() !== key) continue;
                        var ostate = stArr[j];
                        if (!ostate) continue;
                        var otherType = calcOrderType(parseFloat(os.weight) || 0,
                                                      parseFloat(ostate.newWeight) || 0);
                        if (otherType !== curType) continue;
                        var otherReason = (ostate.reason || '').toString().trim();
                        if (otherReason) { found = otherReason; return true; }
                    }
                    return false;
                });
                if (found) st[i].reason = found;
            });
        }

        function renderOrderPanel(pfName) {
            syncReasonFromOtherTabs(pfName);
            var stocks = orderStocks[pfName] || [];
            var st = orderState[pfName] || [];
            var oldSum = stocks.reduce(function(a, s) { return a + s.weight; }, 0);
            var newSum = st.reduce(function(a, x) { return a + (parseFloat(x.newWeight) || 0); }, 0);
            var sumColor = (Math.abs(newSum - oldSum) < 0.01) ? '#16a34a' : (newSum > 100 ? '#dc2626' : '#222');
            var rows = '';
            stocks.forEach(function(s, i) {
                var orderState_i = st[i];
                var ot = calcOrderType(s.weight, parseFloat(orderState_i.newWeight) || 0);
                var sectorCell = s.isNew
                    ? '<td style="text-align:center;padding:8px;"><input type="text" data-idx="' + i + '" data-field="sector" value="' + (s.sector || '').replace(/"/g, '&quot;') + '" placeholder="업종" style="width:100px;text-align:center;padding:4px 6px;border:1px solid #d1d5db;border-radius:4px;font-family:inherit;font-size:15px;color:#000;"></td>'
                    : '<td style="text-align:center;padding:8px;">' + s.sector + '</td>';
                var codeCell = s.isNew
                    ? '<td style="text-align:center;padding:8px;"><input type="text" data-idx="' + i + '" data-field="code" value="' + s.code + '" placeholder="000000" maxlength="6" style="width:70px;text-align:center;padding:4px 6px;border:1px solid #d1d5db;border-radius:4px;font-family:inherit;font-size:15px;color:#000;"></td>'
                    : '<td style="text-align:center;padding:8px;">' + s.code + '</td>';
                var nameCell = s.isNew
                    ? '<td style="text-align:center;padding:8px;"><input type="text" data-idx="' + i + '" data-field="name" value="' + (s.name || '').replace(/"/g, '&quot;') + '" placeholder="종목명" style="width:120px;text-align:center;padding:4px 6px;border:1px solid #d1d5db;border-radius:4px;font-family:inherit;font-size:15px;font-weight:600;color:#000;"></td>'
                    : '<td style="text-align:center;font-weight:600;padding:8px;">' + s.name + '</td>';
                // 주문구분이 유지가 아닌데 추천사유가 비어있으면 입력란을 밝은 붉은색으로 강조
                var reasonEmpty = !(orderState_i.reason || '').toString().trim();
                var reasonNeeded = (ot !== '유지') && reasonEmpty;
                var reasonBg = reasonNeeded ? '#fee2e2' : '#fff';
                var reasonBorder = reasonNeeded ? '#fca5a5' : '#d1d5db';
                // 삭제 버튼: 사용자가 Order 탭에서 추가한 종목(isNew=true)만 표시.
                // portfolio_data.json 출처 종목은 변경후=0(전량 편출)으로 표현하므로 행 삭제 불필요.
                var deleteCell = s.isNew
                    ? '<td style="text-align:center;padding:8px;"><button class="order-del-btn" data-idx="' + i + '" title="종목 삭제" style="background:none;border:none;cursor:pointer;color:#dc2626;font-size:20px;line-height:1;padding:0 6px;font-weight:bold;">×</button></td>'
                    : '<td style="padding:8px;"></td>';
                // 주문구분 배지: 자문지 엑셀 H열과 동일 색상 (편입/확대=#FF0000, 축소/편출=#0070C0).
                // 셀 자체 배경 대신 inline-block span을 써서 전체취소·저장·최종저장 버튼과 동일한 라운드(8px).
                var otBg = '';
                if (ot === '신규 편입' || ot === '비중 확대') otBg = '#FF0000';
                else if (ot === '비중 축소' || ot === '전량 편출') otBg = '#0070C0';
                var otInner = otBg
                    ? '<span style="display:inline-block;padding:4px 12px;background:' + otBg + ';color:#000;border-radius:8px;white-space:nowrap;">' + ot + '</span>'
                    : ot;
                rows += '<tr>'
                    + '<td style="text-align:center;padding:8px;">' + (i + 1) + '</td>'
                    + sectorCell + codeCell + nameCell
                    + '<td style="text-align:center;padding:8px;">' + s.weight + '</td>'
                    + '<td style="text-align:center;padding:8px;"><input type="text" inputmode="decimal" data-idx="' + i + '" data-field="newWeight" value="' + orderState_i.newWeight + '" style="width:65px;box-sizing:border-box;text-align:center;padding:4px 6px;border:1px solid #d1d5db;border-radius:4px;font-family:inherit;font-size:15px;color:#000;"></td>'
                    + '<td style="text-align:center;padding:8px;">' + otInner + '</td>'
                    + '<td style="text-align:center;padding:8px;"><input type="text" data-idx="' + i + '" data-field="reason" value="' + (orderState_i.reason || '').replace(/"/g, '&quot;') + '" style="width:100%;box-sizing:border-box;padding:4px 6px;border:1px solid ' + reasonBorder + ';background:' + reasonBg + ';border-radius:4px;font-family:inherit;font-size:15px;text-align:center;color:#000;"></td>'
                    + deleteCell
                    + '</tr>';
            });
            // 합계 행: 변경전/변경후 SUM, 주문구분 자리에 변경전·후 비중 차이 (양수 빨강, 음수 파랑)
            var weightDiff = newSum - oldSum;
            var diffColor, diffSign;
            if (weightDiff > 0) { diffColor = '#dc2626'; diffSign = '+'; }
            else if (weightDiff < 0) { diffColor = '#1f4cb8'; diffSign = ''; }
            else { diffColor = '#444'; diffSign = ''; }
            var totalsRow = '<tr style="border-top:2px solid #374151;background:#f9fafb;font-weight:700;">'
                + '<td colspan="4" style="padding:8px;text-align:right;color:#444;">합계</td>'
                + '<td style="padding:8px;text-align:center;">' + oldSum.toFixed(0) + '%</td>'
                + '<td style="padding:8px;text-align:center;color:' + sumColor + ';">' + newSum.toFixed(0) + '%</td>'
                + '<td style="padding:8px;text-align:center;color:' + diffColor + ';font-weight:700;">' + diffSign + weightDiff.toFixed(0) + '%</td>'
                + '<td></td>'
                + '<td></td>'
                + '</tr>';
            var html = '<div style="background:#fff;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.06);">'
                + '<div style="display:flex;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:12px;">'
                + '<h3 style="margin:0;font-size:18px;">' + pfName + '</h3>'
                + '<div style="margin-left:auto;display:flex;gap:8px;">'
                + '<button id="orderCancelAllBtn" style="font-family:inherit;font-size:15px;font-weight:600;padding:6px 14px;background:#dc2626;color:#fff;border:none;border-radius:8px;cursor:pointer;">전체 취소</button>'
                + '<button id="orderSaveBtn" style="font-family:inherit;font-size:15px;font-weight:600;padding:6px 14px;background:#f3f4f6;color:#222;border:1px solid #d1d5db;border-radius:8px;cursor:pointer;">저장</button>'
                + '<button id="orderFinalizeBtn" style="font-family:inherit;font-size:15px;font-weight:600;padding:6px 14px;background:#16a34a;color:#fff;border:none;border-radius:8px;cursor:pointer;">최종 저장</button>'
                + '</div>'
                + '</div>'
                + '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:15px;">'
                + '<thead><tr style="border-bottom:2px solid #e5e7eb;color:#444;">'
                + '<th style="padding:8px;text-align:center;width:40px;">순위</th>'
                + '<th style="padding:8px;text-align:center;">업종</th>'
                + '<th style="padding:8px;text-align:center;width:70px;">코드</th>'
                + '<th style="padding:8px;text-align:center;">종목명</th>'
                + '<th style="padding:8px;text-align:center;width:70px;">변경전</th>'
                + '<th style="padding:8px;text-align:center;width:90px;">변경후</th>'
                + '<th style="padding:8px;text-align:center;width:100px;">주문구분</th>'
                + '<th style="padding:8px;text-align:center;">추천사유</th>'
                + '<th style="padding:8px;text-align:center;width:40px;"></th>'
                + '</tr></thead><tbody>' + rows + totalsRow + '</tbody></table></div>'
                + '<div style="margin-top:12px;text-align:right;"><button id="orderAddStockBtn" style="font-family:inherit;font-size:14px;font-weight:600;padding:6px 14px;background:#f3f4f6;color:#222;border:1px solid #d1d5db;border-radius:8px;cursor:pointer;">+ 종목 추가</button></div>'
                + '</div>';
            document.getElementById('orderContent').innerHTML = html;
            document.querySelectorAll('#orderContent input').forEach(function(el) {
                el.addEventListener('input', function(e) {
                    var idx = parseInt(e.target.dataset.idx);
                    var field = e.target.dataset.field;
                    var raw = e.target.value;
                    if (field === 'newWeight') {
                        orderState[orderActiveTab][idx][field] = parseFloat(raw) || 0;
                        renderOrderPanel(orderActiveTab);
                        var refocus = document.querySelector('#orderContent input[data-idx="' + idx + '"][data-field="newWeight"]');
                        if (refocus) { refocus.focus(); refocus.setSelectionRange(refocus.value.length, refocus.value.length); }
                    } else if (field === 'reason') {
                        orderState[orderActiveTab][idx][field] = raw;
                        // 같은 종목 코드 + 같은 주문구분일 때만 다른 탭의 추천사유 동기화
                        var curStock = orderStocks[orderActiveTab][idx];
                        var key = (curStock && curStock.code != null) ? String(curStock.code).trim() : '';
                        var curType = calcOrderType(parseFloat(curStock.weight) || 0,
                                                    parseFloat(orderState[orderActiveTab][idx].newWeight) || 0);
                        if (key) {
                            Object.keys(orderStocks).forEach(function(tab) {
                                if (tab === orderActiveTab) return;
                                orderStocks[tab].forEach(function(s, i) {
                                    if (String(s.code || '').trim() !== key) return;
                                    var otherType = calcOrderType(parseFloat(s.weight) || 0,
                                                                  parseFloat(orderState[tab][i].newWeight) || 0);
                                    if (otherType === curType) {
                                        orderState[tab][i].reason = raw;
                                    }
                                });
                            });
                        }
                    } else if (field === 'code' || field === 'name' || field === 'sector') {
                        // 신규 종목 필드 (orderStocks에 직접 반영)
                        orderStocks[orderActiveTab][idx][field] = raw;
                    }
                });
            });
            // 신규 종목 종목명/코드 blur → 네이버 자동완성으로 나머지 + 업종 자동
            document.querySelectorAll('#orderContent input[data-field="name"]').forEach(function(el) {
                el.addEventListener('blur', function(e) {
                    var idx = parseInt(e.target.dataset.idx);
                    if (!isNaN(idx)) autoFillStockFromName(idx);
                });
            });
            document.querySelectorAll('#orderContent input[data-field="code"]').forEach(function(el) {
                el.addEventListener('blur', function(e) {
                    var idx = parseInt(e.target.dataset.idx);
                    if (!isNaN(idx)) autoFillStockFromCode(idx);
                });
            });
            var cancelBtn = document.getElementById('orderCancelAllBtn');
            if (cancelBtn) cancelBtn.addEventListener('click', function() { cancelAllPendingOrders(); });
            var saveBtn = document.getElementById('orderSaveBtn');
            if (saveBtn) saveBtn.addEventListener('click', function() { saveAllPendingOrders(false); });
            var finalizeBtn = document.getElementById('orderFinalizeBtn');
            if (finalizeBtn) finalizeBtn.addEventListener('click', function() { finalizeOrder(orderActiveTab); });
            var addBtn = document.getElementById('orderAddStockBtn');
            if (addBtn) addBtn.addEventListener('click', function() { addOrderStock(orderActiveTab); });
            // 종목 삭제 (사용자가 추가한 isNew 종목만 가능)
            document.querySelectorAll('#orderContent .order-del-btn').forEach(function(btn) {
                btn.addEventListener('click', function(e) {
                    var idx = parseInt(e.currentTarget.dataset.idx);
                    if (isNaN(idx)) return;
                    orderStocks[orderActiveTab].splice(idx, 1);
                    orderState[orderActiveTab].splice(idx, 1);
                    renderOrderPanel(orderActiveTab);
                });
            });
            function bindCopy(btnSel, preSel, defaultBg) {
                document.querySelectorAll('#orderContent ' + btnSel).forEach(function(btn) {
                    btn.addEventListener('click', function() {
                        var section = btn.parentElement.parentElement;
                        var pre = section.querySelector(preSel);
                        if (!pre) return;
                        navigator.clipboard.writeText(pre.textContent).then(function() {
                            var original = btn.textContent;
                            btn.textContent = '복사됨';
                            btn.style.background = '#16a34a';
                            setTimeout(function() {
                                btn.textContent = original;
                                btn.style.background = defaultBg;
                            }, 1500);
                        }).catch(function(err) {
                            alert('복사 실패: ' + err.message);
                        });
                    });
                });
            }
            bindCopy('.email-copy-btn', '.email-text', '#374151');
            bindCopy('.compliance-copy-btn', '.compliance-text', '#d97706');
            bindCopy('.nateon-copy-btn', '.nateon-text', '#4f46e5');
        }

        function addOrderStock(pfName) {
            orderStocks[pfName].push({ code: '', name: '', sector: '', weight: 0, isNew: true });
            orderState[pfName].push({ newWeight: 0, reason: '' });
            renderOrderPanel(pfName);
        }

        // 같은 종목코드가 다른 탭에 이미 있으면 그 sector를 가져옴 (KRX 분류 lookup).
        function lookupSectorByCode(code) {
            var c = String(code || '').trim();
            if (!c) return '';
            var pfs = Object.keys(orderStocks);
            for (var p = 0; p < pfs.length; p++) {
                var arr = orderStocks[pfs[p]] || [];
                for (var i = 0; i < arr.length; i++) {
                    var s = arr[i];
                    if (String(s.code || '').trim() === c && s.sector && String(s.sector).trim()) {
                        return String(s.sector).trim();
                    }
                }
            }
            return '';
        }

        // KRX 전 종목 마스터(stock_master.json) 1회 로드 + name/code 인덱스 캐시.
        // 같은 origin이라 CORS 영향 없음. Wrap_NAV.xlsx Code 시트가 소스라서 portfolio_data.json의 섹터 표기와 일치.
        // 누락 종목(최근 신규IPO 등)은 수동 입력 fallback. (네이버 API는 GH Pages origin을 403으로 차단 → 외부 API 불가)
        var wicsAllCache = null;
        var wicsByCode = null;
        var wicsByName = null;
        async function loadWicsAll() {
            if (wicsAllCache) return wicsAllCache;
            var resp = await fetch('stock_master.json');
            if (!resp.ok) throw new Error('stock_master.json fetch 실패: ' + resp.status);
            wicsAllCache = await resp.json();
            wicsByCode = {};
            wicsByName = {};
            wicsAllCache.forEach(function(x) {
                if (x.code) wicsByCode[String(x.code)] = x;
                if (x.name) wicsByName[String(x.name)] = x;
            });
            return wicsAllCache;
        }

        // 신규 종목 행에서 종목명 입력 후 blur → stock_master.json lookup으로 코드/업종 채움.
        async function autoFillStockFromName(idx) {
            var stocks = orderStocks[orderActiveTab];
            if (!stocks || !stocks[idx] || !stocks[idx].isNew) return;
            var s = stocks[idx];
            var name = String(s.name || '').trim();
            if (!name) return;
            try {
                await loadWicsAll();
                var hit = wicsByName[name];
                if (!hit) {
                    // 부분 일치 fallback (대소문자 무시)
                    var lower = name.toLowerCase();
                    hit = wicsAllCache.find(function(x) { return x.name && x.name.toLowerCase() === lower; })
                       || wicsAllCache.find(function(x) { return x.name && x.name.toLowerCase().indexOf(lower) >= 0; });
                }
                if (!hit) {
                    console.warn('autoFillStockFromName: stock_master.json에 없음 →', name);
                    return;
                }
                if (!String(s.code || '').trim()) s.code = hit.code;
                s.name = hit.name;  // 정식 종목명으로 보정
                if (!String(s.sector || '').trim()) {
                    var sec = lookupSectorByCode(s.code) || hit.sector || '';
                    if (sec) s.sector = sec;
                }
                renderOrderPanel(orderActiveTab);
            } catch (e) {
                console.warn('autoFillStockFromName 실패:', e);
            }
        }

        // 신규 종목 행에서 코드 입력 후 blur → stock_master.json lookup으로 종목명/업종 채움.
        async function autoFillStockFromCode(idx) {
            var stocks = orderStocks[orderActiveTab];
            if (!stocks || !stocks[idx] || !stocks[idx].isNew) return;
            var s = stocks[idx];
            var code = String(s.code || '').trim();
            if (!code) return;
            // "5930" → "005930" 0-padding (한국 종목은 6자리)
            if (/^\d{1,6}$/.test(code) && code.length < 6) {
                code = code.padStart(6, '0');
                s.code = code;
            }
            try {
                await loadWicsAll();
                var hit = wicsByCode[code];
                if (!hit) {
                    console.warn('autoFillStockFromCode: stock_master.json에 없음 →', code);
                    return;
                }
                if (!String(s.name || '').trim()) s.name = hit.name;
                if (!String(s.sector || '').trim()) {
                    var sec = lookupSectorByCode(s.code) || hit.sector || '';
                    if (sec) s.sector = sec;
                }
                renderOrderPanel(orderActiveTab);
            } catch (e) {
                console.warn('autoFillStockFromCode 실패:', e);
            }
        }

        // ─────────────────────────────────────────────────────────────
        // 저장: GitHub Contents API → orders/wrap_orders.json 누적
        // PAT는 localStorage('github_pat')에 1회 저장 후 재사용
        // ─────────────────────────────────────────────────────────────
        var ORDER_REPO = 'sisyphe10/Antigravity_Market_Dashboard';
        var ORDER_FILE_PATH = 'orders/wrap_orders.json';

        function getGithubPat() {
            var pat = localStorage.getItem('github_pat');
            if (!pat) {
                pat = prompt('GitHub Personal Access Token 입력\\n\\n발급: https://github.com/settings/personal-access-tokens/new\\n- Repository: Antigravity_Market_Dashboard\\n- Permissions → Contents: Read and write\\n\\n(localStorage에 저장되어 이후 자동 사용)');
                if (!pat) return null;
                pat = pat.trim();
                localStorage.setItem('github_pat', pat);
            }
            return pat;
        }

        function utf8ToBase64(str) {
            return btoa(unescape(encodeURIComponent(str)));
        }
        function base64ToUtf8(b64) {
            return decodeURIComponent(escape(atob(b64.replace(/\\n/g, ''))));
        }

        // ORDER 저장 → orders/pending_orders.json 갱신.
        // 모든 포트폴리오를 1회 GET + 1회 PUT으로 영속화 — input 이벤트에서 메모리상 동기화된
        // 추천사유(같은 종목코드+같은 주문구분)가 다른 탭에서도 git에 함께 박히도록 함.
        async function saveAllPendingOrders(silent) {
            var pat = getGithubPat();
            if (!pat) { alert('PAT 입력이 취소되었습니다.'); return; }

            var d = new Date();
            var todayStr = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');

            var apiUrl = 'https://api.github.com/repos/' + ORDER_REPO + '/contents/orders/pending_orders.json';
            var headers = {
                'Authorization': 'Bearer ' + pat,
                'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28',
            };

            try {
                // 기존 pending 1회 GET
                var existing = {};
                var sha = null;
                var getResp = await fetch(apiUrl, { headers: headers });
                if (getResp.ok) {
                    var data = await getResp.json();
                    sha = data.sha;
                    try {
                        existing = JSON.parse(base64ToUtf8(data.content));
                        if (typeof existing !== 'object' || Array.isArray(existing)) existing = {};
                    } catch(_) { existing = {}; }
                } else if (getResp.status === 401 || getResp.status === 403) {
                    localStorage.removeItem('github_pat');
                    throw new Error('인증 실패 (' + getResp.status + '). PAT를 다시 입력하세요.');
                } else if (getResp.status !== 404) {
                    throw new Error('GET 실패: ' + getResp.status);
                }

                // 모든 포트폴리오 갱신
                if (!existing[todayStr]) existing[todayStr] = {};
                var totalRows = 0;
                var savedPfs = [];
                ORDER_PORTFOLIOS.forEach(function(p) {
                    var pfName = p.display;
                    var targets = p.newSheetTargets || [];
                    if (!targets.length) return;
                    var stocks = orderStocks[pfName] || [];
                    var st = orderState[pfName] || [];
                    var validRows = [];
                    stocks.forEach(function(s, i) {
                        var newW = parseFloat(st[i].newWeight) || 0;
                        if (s.code) {
                            validRows.push({
                                sector: s.sector || '',
                                code: String(s.code),
                                name: s.name || '',
                                weight: newW,
                                reason: (st[i].reason || '').toString()
                            });
                        }
                    });
                    if (validRows.length === 0) return;
                    existing[todayStr][pfName] = {
                        targets: targets,
                        stocks: validRows,
                        savedAt: new Date().toISOString(),
                    };
                    totalRows += validRows.length;
                    savedPfs.push(pfName);
                });

                if (savedPfs.length === 0) { alert('저장할 종목이 없습니다.'); return; }

                // 1회 PUT
                var newContent = utf8ToBase64(JSON.stringify(existing, null, 2));
                var msg = 'ORDER pending: ' + savedPfs.length + ' pf (' + todayStr + ', ' + totalRows + ' stocks)';
                var body = { message: msg, content: newContent };
                if (sha) body.sha = sha;

                var putResp = await fetch(apiUrl, {
                    method: 'PUT',
                    headers: Object.assign({}, headers, { 'Content-Type': 'application/json' }),
                    body: JSON.stringify(body),
                });
                if (!putResp.ok) {
                    var errTxt = await putResp.text();
                    throw new Error('PUT 실패: ' + putResp.status + ' ' + errTxt.slice(0, 200));
                }
                if (!silent) {
                    alert('✅ 저장 완료 (' + savedPfs.length + '개 포트폴리오, ' + totalRows + '개 종목)\\n\\n탭 간 추천사유 동기화 보존됨. 최종 반영은 [최종 저장] 또는 16:00 KST 자동 처리.');
                }
            } catch(e) {
                if (!silent) alert('❌ 저장 실패: ' + e.message);
                console.error('saveAllPendingOrders error:', e);
                throw e;
            }
        }

        // 전체 취소: 오늘 임시저장(pending_orders.json[todayStr]) 전부 삭제 + 메모리 리셋 → portfolio_data.json 원본 다시 로드.
        // 최종 저장(finalize) 후 NEW 시트에 박힌 건 되돌리지 않음 — pending 단계만 취소.
        async function cancelAllPendingOrders() {
            if (!confirm('오늘 임시 저장한 모든 변경사항을 취소하시겠습니까?\\n원본 비중·빈 추천사유로 되돌립니다.')) return;
            var pat = getGithubPat();
            if (!pat) { alert('PAT 입력이 취소되었습니다.'); return; }
            var d = new Date();
            var todayStr = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
            var apiUrl = 'https://api.github.com/repos/sisyphe10/Antigravity_Market_Dashboard/contents/orders/pending_orders.json';
            var headers = {
                'Authorization': 'token ' + pat,
                'Accept': 'application/vnd.github.v3+json',
                'Content-Type': 'application/json'
            };
            try {
                var existing = {};
                var sha = null;
                var getResp = await fetch(apiUrl, { headers: headers });
                if (getResp.ok) {
                    var raw = await getResp.json();
                    sha = raw.sha;
                    try { existing = JSON.parse(base64ToUtf8(raw.content)); } catch(_) { existing = {}; }
                } else if (getResp.status !== 404) {
                    throw new Error('GET 실패: ' + getResp.status);
                }
                var hadToday = !!existing[todayStr];
                if (hadToday) {
                    delete existing[todayStr];
                    var newContent = utf8ToBase64(JSON.stringify(existing, null, 2));
                    var body = { message: 'ORDER cancel: 전체 취소 (' + todayStr + ')', content: newContent };
                    if (sha) body.sha = sha;
                    var putResp = await fetch(apiUrl, { method: 'PUT', headers: headers, body: JSON.stringify(body) });
                    if (!putResp.ok) {
                        var errTxt = await putResp.text();
                        throw new Error('PUT 실패: ' + putResp.status + ' ' + errTxt.slice(0, 200));
                    }
                }
                // 메모리 직접 리셋 — pending fetch 우회.
                // loadOrder()는 Pages의 orders/pending_orders.json을 다시 fetch하는데,
                // PUT 직후엔 Pages CDN이 stale 응답을 줄 수 있어 비운 내용이 그대로 복원되는 케이스가 있음.
                // → portfolio_data.json만 직접 fetch해서 orderStocks/orderState를 원본으로 초기화.
                var pdRes = await fetch('portfolio_data.json?_=' + Date.now());
                if (!pdRes.ok) throw new Error('portfolio_data.json fetch 실패: ' + pdRes.status);
                var pdata = await pdRes.json();
                orderStocks = {};
                orderState = {};
                ORDER_PORTFOLIOS.forEach(function(p) {
                    var stocks = pdata[p.jsonKey] || [];
                    orderStocks[p.display] = stocks.map(function(s) {
                        var origW = parseFloat(s.weight) || 0;
                        var prevW = (s.weight_prev != null) ? (parseFloat(s.weight_prev) || 0) : origW;
                        return { code: s.code, name: s.name, sector: s.sector || '', weight: prevW };
                    });
                    orderState[p.display] = stocks.map(function(s) {
                        return { newWeight: parseFloat(s.weight) || 0, reason: '' };
                    });
                });
                _orderLoaded = true;
                if (orderActiveTab && orderActiveTab !== 'Email') renderOrderPanel(orderActiveTab);
            } catch(e) {
                alert('❌ 취소 실패: ' + e.message);
                console.error('cancelAllPendingOrders error:', e);
            }
        }

        // 최종 저장 = 3개 포트폴리오 모두 저장 + finalize 워크플로 1회 트리거
        async function finalizeOrder(_pfNameIgnored) {
            if (!confirm('최종 저장하시겠습니까?\\n\\n3개 포트폴리오(일반형/DB 목표전환형 5차/NH 목표전환형 4호) 모두 저장 후 GitHub Actions(finalize_orders) 즉시 실행. 1~2분 후 Wrap_NAV.xlsx NEW 시트 + 대시보드 반영.')) return;
            var pat = getGithubPat();
            if (!pat) { alert('PAT 입력이 취소되었습니다.'); return; }
            // 모든 포트폴리오 1회 커밋으로 저장 (탭 간 reason 동기화 보존)
            try {
                await saveAllPendingOrders(true);
            } catch(e) {
                alert('❌ 저장 실패: ' + e.message + '\\n\\n워크플로 실행 중단. 수정 후 재시도하세요.');
                return;
            }
            try {
                var dispatchUrl = 'https://api.github.com/repos/' + ORDER_REPO + '/actions/workflows/finalize_orders.yml/dispatches';
                var resp = await fetch(dispatchUrl, {
                    method: 'POST',
                    headers: {
                        'Authorization': 'token ' + pat,
                        'Accept': 'application/vnd.github+json',
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ ref: 'main' })
                });
                if (resp.status === 204) {
                    alert('✅ 최종 저장 완료\\n\\nfinalize_orders 워크플로 실행 중. 1~2분 후 Wrap_NAV.xlsx + 대시보드 반영. Actions 탭에서 진행상황 확인 가능.');
                } else if (resp.status === 401 || resp.status === 403) {
                    alert('❌ PAT 권한 부족 (' + resp.status + ')\\n\\nfine-grained PAT 설정에서 Actions 권한을 "Read and write"로 추가하세요.\\nhttps://github.com/settings/personal-access-tokens');
                } else {
                    var t = await resp.text();
                    alert('❌ 워크플로 트리거 실패: HTTP ' + resp.status + '\\n' + t.slice(0, 300));
                }
            } catch(e) {
                alert('❌ 워크플로 호출 실패: ' + e.message);
                console.error('finalizeOrder error:', e);
            }
        }

        async function downloadOrderExcel(pfName, templateIdx) {
            var p = ORDER_PORTFOLIOS.find(function(x) { return x.display === pfName; });
            if (!p) { alert('포트폴리오 매핑 누락: ' + pfName); return; }
            if (typeof ExcelJS === 'undefined') { alert('ExcelJS 라이브러리 로드 실패. 새로고침 해주세요.'); return; }
            var t = p.templates[templateIdx];
            if (!t) { alert('템플릿 매핑 누락: ' + templateIdx); return; }
            var stocks = orderStocks[pfName];
            var st = orderState[pfName];
            try {
                var resp = await fetch(t.file);
                if (!resp.ok) throw new Error('템플릿 fetch 실패: HTTP ' + resp.status + ' (' + t.file + ')');
                var buf = await resp.arrayBuffer();
                var wb = new ExcelJS.Workbook();
                await wb.xlsx.load(buf);
                var ws = wb.worksheets[0];

                // 종목 데이터 결합 + 비중(변경후) 내림차순 정렬
                var combined = stocks.map(function(s, i) {
                    var newW = parseFloat(st[i].newWeight) || 0;
                    return {
                        sector: s.sector || '',
                        code: String(s.code || ''),
                        name: s.name || '',
                        oldWeight: parseFloat(s.weight) || 0,
                        newWeight: newW,
                        orderType: calcOrderType(parseFloat(s.weight) || 0, newW),
                        reason: st[i].reason || '',
                    };
                });
                combined.sort(function(a, b) { return b.newWeight - a.newWeight; });

                // 자문지 양식의 Total 행 자동 감지 (E열에 'Total' 또는 'TOTAL' 텍스트)
                var totalRow = -1;
                for (var r = 7; r <= ws.rowCount + 5; r++) {
                    var v = ws.getCell(r, 5).value;
                    if (v && /total/i.test(String(v))) { totalRow = r; break; }
                }

                if (totalRow >= 7) {
                    // Total 행이 있는 양식 (목표전환형) → 행 수 자동 조정
                    var existingCount = totalRow - 7;
                    var newCount = combined.length;
                    if (newCount > existingCount) {
                        // R7 행 서식을 복제하여 (newCount-existingCount)개 행 삽입
                        ws.duplicateRow(7, newCount - existingCount, true);
                        totalRow += (newCount - existingCount);
                    } else if (newCount < existingCount) {
                        ws.spliceRows(7, existingCount - newCount);
                        totalRow -= (existingCount - newCount);
                    }
                }

                // B4 TODAY() 셀 날짜 포맷 (ExcelJS load 후 'General'로 떨어지는 케이스 방어)
                var b4 = ws.getCell('B4');
                if (b4 && b4.value && (b4.formula === 'TODAY()' || /TODAY/i.test(String(b4.formula || b4.value)))) {
                    b4.numFmt = 'yyyy-mm-dd';
                }

                // B2 헤더의 "목표전환형 N호"를 현재 회차(pfName 내 숫자)에 맞춰 동적 치환.
                // NH 자문지 템플릿이 N호 시리즈 사이에서 재사용되며 헤더가 옛 호수로 박혀있어 발생.
                var b2 = ws.getCell('B2');
                if (b2 && typeof b2.value === 'string') {
                    var hoMatch = pfName.match(/(\d+)\s*호/);
                    if (hoMatch) {
                        var newB2 = b2.value.replace(/목표전환형\s*\d+\s*호/, '목표전환형 ' + hoMatch[1] + '호');
                        if (newB2 !== b2.value) b2.value = newB2;
                    }
                }

                // 자문지 템플릿 H7:H27에 걸린 조건부 서식 제거.
                // CF가 "매수/매도/편출/신규편입" 키워드를 검색해 진한 색을 덮어쓰는데,
                // 새 분류명("신규 편입" 등 공백 포함)과 일치도가 깨져 색이 일관되지 않음.
                // → CF를 비우고 아래 직접 fill만으로 색 통제.
                ws.conditionalFormattings = [];

                // 종목 채우기 + 행 높이 통일 + 주문구분 셀 색상 (편입/확대=빨강, 축소/편출=파랑)
                var DATA_ROW_HEIGHT = 15;
                combined.forEach(function(s, i) {
                    var r = 7 + i;
                    ws.getCell('B' + r).value = i + 1;
                    ws.getCell('C' + r).value = s.sector;
                    ws.getCell('D' + r).value = s.code;  // 코드는 string으로 (앞 0 보존)
                    ws.getCell('E' + r).value = s.name;
                    ws.getCell('F' + r).value = s.oldWeight;
                    ws.getCell('G' + r).value = s.newWeight;
                    var hCell = ws.getCell('H' + r);
                    hCell.value = s.orderType;
                    // duplicateRow(true)가 style 객체를 참조 복사하므로, H셀 style을 shallow clone하여 공유 해제.
                    // 안 하면 마지막 분류 색상이 모든 복제 행에 덮어써짐.
                    hCell.style = Object.assign({}, hCell.style);
                    var ot = s.orderType;
                    // 글씨는 항상 검정. 배경: 편입/확대=빨강, 축소/편출=파랑, 유지=흰색(템플릿 기본).
                    var prevFont = hCell.font || {};
                    hCell.font = Object.assign({}, prevFont, { color: { argb: 'FF000000' } });
                    var bgColor;
                    if (ot === '신규 편입' || ot === '비중 확대') bgColor = 'FFFF0000';
                    else if (ot === '비중 축소' || ot === '전량 편출') bgColor = 'FF0070C0';
                    else bgColor = 'FFFFFFFF';  // 유지: 흰색 명시 (ExcelJS pattern:'none'이 잔존 fill 못 지우는 케이스 방어)
                    hCell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: bgColor } };
                    ws.getCell('I' + r).value = s.reason;
                    ws.getRow(r).height = DATA_ROW_HEIGHT;
                });

                if (totalRow >= 7) {
                    // Total 행 SUM 범위 갱신 (실제 종목 수에 맞춰)
                    var lastDataRow = 6 + combined.length;
                    ws.getCell('F' + totalRow).value = { formula: 'SUM(F7:F' + lastDataRow + ')' };
                    ws.getCell('G' + totalRow).value = { formula: 'SUM(G7:G' + lastDataRow + ')' };
                    ws.getCell('H' + totalRow).value = { formula: 'G' + totalRow + '-F' + totalRow };
                }

                var out = await wb.xlsx.writeBuffer();
                var blob = new Blob([out], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
                var url = URL.createObjectURL(blob);
                var a = document.createElement('a');
                a.href = url;
                a.download = buildOutFilename(t, new Date());
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            } catch(e) {
                alert('자문지 송출 실패: ' + e.message);
                console.error('downloadOrderExcel error:', e);
            }
        }
        </script>
    """


def create_disclosures_section():
    """공시 탭 — disclosures.json 누적 데이터를 날짜순 테이블 + 종목 필터로 렌더.

    매일 fetch_disclosures.py(GHA cron)가 portfolio_data.json의 현재 보유 종목에 대해
    DART API로 신규 공시만 수집해서 누적. 컬럼: 공시일/종목/제목/요약/URL.
    """
    return """
        <div style="max-width:1800px;margin:0 auto;">
            <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px;flex-wrap:wrap;">
                <h2 style="margin:0;font-size:24px;font-weight:700;color:#222;">공시 (DART + KIND)</h2>
                <span id="disclLastUpdated" style="font-size:13px;color:#666;"></span>
                <label style="margin-left:auto;font-size:14px;color:#444;display:flex;align-items:center;gap:8px;">
                    종목 필터
                    <select id="disclStockFilter" style="padding:6px 10px;border:1px solid #d1d5db;border-radius:6px;font-family:inherit;font-size:14px;background:#fff;min-width:160px;text-align:center;text-align-last:center;">
                        <option value="">전체</option>
                    </select>
                </label>
                <span id="disclCount" style="font-size:13px;color:#666;"></span>
            </div>
            <div id="disclContent" style="background:#fff;border-radius:8px;padding:12px;box-shadow:0 1px 3px rgba(0,0,0,0.05);">
                <div style="text-align:center;color:#888;padding:40px;">로딩 중...</div>
            </div>
        </div>
        <script>
        var _disclData = null;
        var _disclLoaded = false;

        async function loadDisclosures() {
            if (_disclLoaded) return;
            _disclLoaded = true;
            try {
                var res = await fetch('disclosures.json?_=' + Date.now());
                if (!res.ok) throw new Error('disclosures.json fetch 실패: ' + res.status);
                _disclData = await res.json();
                var items = _disclData.items || [];
                document.getElementById('disclLastUpdated').textContent = _disclData.updated_at ? ('Updated: ' + _disclData.updated_at) : '';
                // 종목 dropdown 채우기 (name+code 유일하게)
                var seen = {};
                var stocks = [];
                items.forEach(function(it) {
                    var key = it.code + '|' + it.name;
                    if (!seen[key]) { seen[key] = true; stocks.push({ code: it.code, name: it.name }); }
                });
                stocks.sort(function(a, b) { return a.name.localeCompare(b.name, 'ko'); });
                var sel = document.getElementById('disclStockFilter');
                stocks.forEach(function(s) {
                    var opt = document.createElement('option');
                    opt.value = s.code;
                    opt.textContent = s.name + ' (' + s.code + ')';
                    sel.appendChild(opt);
                });
                sel.addEventListener('change', renderDisclosures);
                renderDisclosures();
            } catch (e) {
                document.getElementById('disclContent').innerHTML = '<div style="text-align:center;color:#c00;padding:40px;">로드 실패: ' + e.message + '</div>';
            }
        }

        // 금액 하이라이트 (API 비용 없이 정규식만):
        //   1) 콤마 2개 이상 포함된 큰 숫자 (백만 이상). 예: "515,761,033,577"
        //   2) 한글 단위 표현. 예: "5,000억원", "1조 원", "300만"
        // HTML escape 후 적용 — escape가 <>만 변환하므로 숫자 패턴은 그대로 매칭.
        function highlightAmounts(text) {
            return text.replace(/(\d{1,3}(?:,\d{3}){2,}(?:\s*원)?|\d+(?:,\d{3})*\s*(?:조|억|만)\s*원?)/g,
                '<mark style="background:#fff7c2;padding:0 3px;border-radius:3px;font-weight:600;">$1</mark>');
        }

        function renderDisclosures() {
            if (!_disclData) return;
            var filter = document.getElementById('disclStockFilter').value;
            var items = (_disclData.items || []).filter(function(it) { return !filter || it.code === filter; });
            document.getElementById('disclCount').textContent = items.length + '건';
            if (items.length === 0) {
                document.getElementById('disclContent').innerHTML = '<div style="text-align:center;color:#888;padding:40px;">공시 데이터 없음.</div>';
                return;
            }
            var html = '<table style="width:100%;border-collapse:collapse;font-size:14px;">';
            html += '<thead><tr style="background:#f3f4f6;border-bottom:2px solid #d1d5db;">'
                  + '<th style="padding:10px;text-align:center;width:110px;">공시일</th>'
                  + '<th style="padding:10px;text-align:center;width:140px;">종목</th>'
                  + '<th style="padding:10px;text-align:left;width:280px;">제목</th>'
                  + '<th style="padding:10px;text-align:center;width:60px;">링크</th>'
                  + '<th style="padding:10px;text-align:left;">요약</th>'
                  + '</tr></thead><tbody>';
            items.forEach(function(it) {
                var summary = highlightAmounts((it.summary || '').replace(/</g, '&lt;').replace(/>/g, '&gt;'));
                var title = (it.title || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                var name = (it.name || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                // source 배지: KIND(거래소) 진녹 / DART(금감원, 기본) 회색
                var src = it.source || 'DART';
                var badgeBg = src === 'KIND' ? '#2d7a3a' : '#6c757d';
                var badge = '<span style="display:inline-block;background:' + badgeBg + ';color:#fff;font-size:10px;font-weight:700;padding:2px 6px;border-radius:3px;margin-right:6px;vertical-align:middle;">' + src + '</span>';
                html += '<tr style="border-bottom:1px solid #e5e7eb;">'
                      + '<td style="padding:8px;text-align:center;color:#444;white-space:nowrap;">' + it.date + '</td>'
                      + '<td style="padding:8px;text-align:center;font-weight:600;color:#1f2937;">' + name + '<div style="font-size:11px;color:#888;">' + it.code + '</div></td>'
                      + '<td style="padding:8px;text-align:left;color:#222;font-weight:500;">' + badge + title + '</td>'
                      + '<td style="padding:8px;text-align:center;"><a href="' + it.url + '" target="_blank" rel="noopener" style="color:#2563eb;text-decoration:none;font-weight:700;font-size:20px;line-height:1;">⧉</a></td>'
                      + '<td style="padding:8px;text-align:left;color:#555;line-height:1.5;">' + summary + '</td>'
                      + '</tr>';
            });
            html += '</tbody></table>';
            document.getElementById('disclContent').innerHTML = html;
        }
        </script>
    """


# 수수료 탭 데이터 — 빈 골격. 값은 숫자(%) 또는 None(미입력=화면에 '—').
# 각 항목: 선취/후취 수수료를 증권사 / 자문사 행으로 분리. 합계 행은 자동 계산.
FEE_TABLE = [
    {
        'broker': '삼성',
        'types': [
            {'type': '개방형',     'pre_broker': None, 'pre_advisor': None, 'post_broker': None, 'post_advisor': None, 'perf_ratio': None},
        ],
    },
    {
        'broker': 'NH',
        'types': [
            {'type': '개방형',     'pre_broker': 0, 'pre_advisor': 0, 'post_broker': 0.9, 'post_advisor': 0.6, 'perf_ratio': (4, 6), 'perf_note': '7% 초과분의 20%'},
            {'type': '목표전환형', 'target': 5, 'pre_broker': 1, 'pre_advisor': 0, 'post_broker': 0, 'post_advisor': 0,
             'perf_broker_pct': 0.5, 'perf_advisor_pct': 0.5, 'perf_total_tip': '<ul class="tip-list"><li>성과 보수 = 발생 수익의 20%</li></ul>'},
        ],
    },
    {
        'broker': 'DB',
        'types': [
            {'type': '개방형',     'pre_broker': 1, 'pre_advisor': 0, 'post_broker': 0.24, 'post_advisor': 0.36, 'perf_ratio': (4, 6), 'perf_note': '7% 초과분의 20%'},
            {'type': '목표전환형', 'target': 6, 'pre_broker': 0.75, 'pre_advisor': 0.75, 'post_broker': 0, 'post_advisor': 0, 'perf_ratio': None, 'perf_text': '-',
             'pre_total_text': '1.5% (연율)',
             'pre_total_tip': '<ul class="tip-list"><li>총 수수료 = 중도해지수수료 + 환매수수료<ul><li>중도해지수수료 = 소요일 / 365 × 1.5%</li><li>환매수수료 = (365 − 소요일) / 365 × 1.5% × 80%</li></ul></li></ul>'},
        ],
    },
    {
        'broker': '한투',
        'types': [
            {'type': '개방형',     'pre_broker': None, 'pre_advisor': None, 'post_broker': None, 'post_advisor': None, 'perf_ratio': None},
            {'type': '목표전환형', 'pre_broker': None, 'pre_advisor': None, 'post_broker': None, 'post_advisor': None, 'perf_ratio': None},
        ],
    },
]


def _fmt_fee(v):
    """수수료 값 표시: None → 공란, 숫자 → 소수점 둘째자리 '1.00%'."""
    if v is None:
        return ''
    if isinstance(v, (int, float)):
        return f'{v:.2f}%'
    return str(v)


def _sum_fee(a, b):
    """증권사 + 자문사 합계. 둘 다 None이면 None, 숫자만 합산."""
    if isinstance(a, (int, float)) or isinstance(b, (int, float)):
        return (a or 0) + (b or 0)
    return None


def create_fee_section():
    """수수료 패널 — 증권사 / 형태 / 선취·후취 수수료(증권사·자문사·합계 3행) 정적 테이블."""
    rows = ''
    for grp in FEE_TABLE:
        broker = grp['broker']
        types = grp['types']
        broker_rowspan = len(types) * 3
        first_broker_row = True
        for t in types:
            type_cell = f'<td class="fee-type" rowspan="3">{t["type"]}</td>'
            # 성과보수는 증권사:자문사 분배 비율로 표기 (perf_ratio = (증권사, 자문사))
            pr = t.get("perf_ratio")
            perf_bpct = t.get("perf_broker_pct")
            perf_apct = t.get("perf_advisor_pct")
            perf_note = t.get("perf_note")
            if perf_bpct is not None or perf_apct is not None:
                # 성과보수를 실제 %로 표기 (증권사/자문사 %, 합계는 합 + 선택적 호버 툴팁)
                perf_broker_cell = _fmt_fee(perf_bpct)
                perf_advisor_cell = _fmt_fee(perf_apct)
                perf_total_cell = _fmt_fee(_sum_fee(perf_bpct, perf_apct))
                _ptip = t.get("perf_total_tip")
                if _ptip:
                    perf_total_cell = f'<span class="fee-tip" tabindex="0">{perf_total_cell}<span class="fee-tip-box">{_ptip}</span></span>'
            elif pr:
                # 성과보수를 증권사:자문사 분배 비율로 표기
                perf_broker_cell = f'{pr[0]:g}'
                perf_advisor_cell = f'{pr[1]:g}'
                # 합계 행: 비율(증권사/자문사 행에서 확인 가능)은 생략하고 기준 문구만 표기
                perf_total_cell = perf_note if perf_note else f'{pr[0]:g} : {pr[1]:g}'
            else:
                perf_broker_cell = ''
                perf_advisor_cell = ''
                perf_total_cell = perf_note or ''
            # 성과보수가 고정 문구('-' 등)일 때: 세 행 모두 같은 값
            perf_text = t.get("perf_text")
            if perf_text:
                perf_broker_cell = perf_advisor_cell = perf_total_cell = perf_text
            # 후취/성과보수가 아예 없는 상품: '없음' 등을 3행 병합으로 표기 (post_label/perf_label)
            post_label = t.get("post_label")
            perf_label = t.get("perf_label")
            # 증권사 행
            rows += '<tr>'
            if first_broker_row:
                rows += f'<td class="fee-broker" rowspan="{broker_rowspan}">{broker}</td>'
                first_broker_row = False
            rows += type_cell
            target_disp = '-' if t["type"] == '개방형' else _fmt_fee(t.get("target"))
            rows += f'<td class="fee-target" rowspan="3">{target_disp}</td>'
            rows += '<td class="fee-share">증권사</td>'
            rows += f'<td class="fee-val">{_fmt_fee(t["pre_broker"])}</td>'
            if post_label:
                rows += f'<td class="fee-val fee-none" rowspan="3">{post_label}</td>'
            else:
                rows += f'<td class="fee-val">{_fmt_fee(t["post_broker"])}</td>'
            if perf_label:
                rows += f'<td class="fee-val fee-none" rowspan="3">{perf_label}</td>'
            else:
                rows += f'<td class="fee-val">{perf_broker_cell}</td>'
            rows += '</tr>'
            # 자문사 행
            rows += '<tr class="fee-row-advisor">'
            rows += '<td class="fee-share">자문사</td>'
            rows += f'<td class="fee-val">{_fmt_fee(t["pre_advisor"])}</td>'
            if not post_label:
                rows += f'<td class="fee-val">{_fmt_fee(t["post_advisor"])}</td>'
            if not perf_label:
                rows += f'<td class="fee-val">{perf_advisor_cell}</td>'
            rows += '</tr>'
            # 선취 합계: override 문구가 있으면 그 문구(+호버 툴팁) 사용, 없으면 증권사+자문사 합
            pre_total_cell = _fmt_fee(_sum_fee(t["pre_broker"], t["pre_advisor"]))
            if t.get("pre_total_text"):
                _txt = t["pre_total_text"]
                _tip = t.get("pre_total_tip")
                if _tip:
                    pre_total_cell = f'<span class="fee-tip" tabindex="0">{_txt}<span class="fee-tip-box">{_tip}</span></span>'
                else:
                    pre_total_cell = _txt
            # 합계 행 (선취/후취는 증권사+자문사 합, 성과보수는 비율)
            rows += '<tr class="fee-row-total">'
            rows += '<td class="fee-share">합계</td>'
            rows += f'<td class="fee-val">{pre_total_cell}</td>'
            if not post_label:
                rows += f'<td class="fee-val">{_fmt_fee(_sum_fee(t["post_broker"], t["post_advisor"]))}</td>'
            if not perf_label:
                rows += f'<td class="fee-val">{perf_total_cell}</td>'
            rows += '</tr>'

    return f"""
        <div class="fee-wrapper">
            <div class="table-container">
                <table class="fee-table">
                    <thead>
                        <tr>
                            <th>증권사</th>
                            <th>형태</th>
                            <th>목표</th>
                            <th>구분</th>
                            <th>선취 수수료</th>
                            <th>후취 수수료</th>
                            <th>성과 보수</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>
            </div>
        </div>
    """


# ── 매출 탭 (실제 발생 수수료 = 자문사 몫 정산 금액) ──────────────────────
def load_fee_revenue(path='fee_revenue.json'):
    """매출(실제 발생 수수료, 자문사 몫) 데이터 로드. 없으면 빈 구조."""
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {'updated': '', 'records': []}
    data.setdefault('records', [])
    return data


def _fmt_won(won):
    """원 단위 정수 표기: '42,768,106원'."""
    return f"{int(round(won)):,}원"


def _fmt_eok_man(won):
    """원 → 'N억 N,NNN만원' (억 미만은 만원). 매출 요약용 가독 표기."""
    won = int(round(won))
    eok, rem = divmod(won, 10**8)
    man = round(rem / 10**4)
    if eok > 0:
        return f"{eok}억 {man:,}만원" if man else f"{eok}억원"
    return f"{man:,}만원"


_REV_CAT_ORDER = ['개방형', '목표전환형']
_REV_BROKER_ORDER = ['삼성', 'NH', 'DB', '한투']


def create_fee_revenue_section():
    """매출 탭 — 실제 정산 수수료(자문사 몫)를 분기별/증권사별/상품별로 집계."""
    data = load_fee_revenue()
    records = [r for r in data.get('records', []) if isinstance(r.get('amount'), (int, float))]
    updated = data.get('updated', '')

    if not records:
        return ('<div class="fee-wrapper"><p class="rev-empty">아직 입력된 매출 데이터가 없습니다.<br>'
                '<code>python add_fee_revenue.py</code> 로 실제 정산 금액을 입력하세요.</p></div>')

    total = sum(r['amount'] for r in records)
    payload = json.dumps({'records': records, 'updated': updated}, ensure_ascii=False)
    updated_html = f'<span class="rev-updated">기준일 {updated}</span>' if updated else ''

    # 상단: 누적 총매출 카드 + 정렬 버튼(분기별/증권사별/상품별) + 단일 평면 테이블.
    # 모든 레코드를 한 테이블에 펼쳐두고, 버튼을 누르면 JS(revRender)가 그 기준으로 정렬한다.
    head_html = f"""
        <div class="fee-wrapper rev-wrapper">
            {updated_html}
            <div class="rev-summary">
                <div class="rev-sum-label">누적 매출</div>
                <div class="rev-sum-value" title="{_fmt_won(total)}">{_fmt_eok_man(total)}</div>
            </div>
            <div class="table-container"><div id="revTableHost"></div></div>
        </div>
    """

    script = """
        <script>
        var FEE_REVENUE = __PAYLOAD__;
        var REV_CATS = ['개방형', '목표전환형'];
        var REV_BROKER_ORDER = ['삼성', 'NH', 'DB', '한투'];
        var REV_DIMS = [['quarter', '분기'], ['broker', '증권사'], ['product', '상품']];
        var REV_ORD_SHADES = ['#1e40af', '#5277cc', '#8aa9e6'];  // 클릭 순서: 진한→연한 (순서 표시)
        var revActiveDims = ['quarter'];  // 클릭 순서대로 누적되는 그룹 기준 (엑셀 피벗 Rows 영역)
        function revFmtNum(n) { return Number(n).toLocaleString('ko-KR'); }        // 안쪽 셀: 숫자만
        function revFmtWon(n) { return Number(n).toLocaleString('ko-KR') + '원'; } // 합계 라인: 원
        function revProd(r) { return r.label || r.category; }
        function revFmtQuarter(q) { var m = /^(\\d{4})-Q([1-4])$/.exec(q); return m ? m[1] + '년 ' + m[2] + '분기' : q; }
        function revDimRaw(d, r) { return d === 'quarter' ? r.quarter : (d === 'broker' ? r.broker : revProd(r)); }
        function revDimDisp(d, val) { return d === 'quarter' ? revFmtQuarter(val) : val; }
        function revDimHead(d) { return d === 'quarter' ? '분기' : (d === 'broker' ? '증권사' : '상품'); }
        function revDimSort(d, val) { return d === 'broker' ? REV_BROKER_ORDER.indexOf(val) : val; }
        // 레코드 목록 → 카테고리별 합계 {개방형, 목표전환형, _total}
        function revCatVals(list) {
            var o = {}, tot = 0;
            REV_CATS.forEach(function(c) {
                var v = list.filter(function(r) { return r.category === c; })
                            .reduce(function(s, r) { return s + r.amount; }, 0);
                o[c] = v; tot += v;
            });
            o._total = tot; return o;
        }
        // 버튼 클릭: 그냥 클릭 = 단일 전환 / Ctrl·Shift+클릭 = 다중 누적(클릭 순서대로 추가, 재클릭 해제)
        function revToggleDim(d, ev) {
            var multi = ev && (ev.ctrlKey || ev.shiftKey || ev.metaKey);
            if (!multi) {
                revActiveDims = [d];
            } else {
                var i = revActiveDims.indexOf(d);
                if (i === -1) { revActiveDims.push(d); }
                else if (revActiveDims.length > 1) { revActiveDims.splice(i, 1); }
            }
            revRender();
        }
        function revRender() {
            var dims = revActiveDims;
            var recs = FEE_REVENUE.records;
            var withDates = dims.indexOf('product') !== -1;
            // 복합키(클릭 순서)로 그룹화
            var groups = {}, order = [];
            recs.forEach(function(r) {
                var keyArr = dims.map(function(d) { return revDimRaw(d, r); });
                var kk = keyArr.join('|#|');
                if (!groups[kk]) { groups[kk] = { keyArr: keyArr, recs: [] }; order.push(kk); }
                groups[kk].recs.push(r);
            });
            var rows = order.map(function(kk) { return groups[kk]; });
            rows.sort(function(a, b) {
                for (var i = 0; i < dims.length; i++) {
                    var sa = revDimSort(dims[i], a.keyArr[i]), sb = revDimSort(dims[i], b.keyArr[i]);
                    if (sa < sb) return -1; if (sa > sb) return 1;
                }
                return 0;
            });
            // 본문
            var body = rows.map(function(g) {
                var v = revCatVals(g.recs);
                var cells = dims.map(function(d, i) { return '<td class="rev-key">' + revDimDisp(d, g.keyArr[i]) + '</td>'; }).join('') +
                    REV_CATS.map(function(c) { return '<td class="rev-amt">' + (v[c] ? revFmtNum(v[c]) : '-') + '</td>'; }).join('');
                if (withDates) {
                    var ss = g.recs.map(function(r) { return r.start || ''; });
                    var ee = g.recs.map(function(r) { return r.end || ''; });
                    var s0 = ss.every(function(x) { return x === ss[0]; }) ? ss[0] : '';
                    var e0 = ee.every(function(x) { return x === ee[0]; }) ? ee[0] : '';
                    cells += '<td class="rev-date">' + s0 + '</td><td class="rev-date">' + e0 + '</td>';
                }
                cells += '<td class="rev-amt rev-rowtot">' + revFmtNum(v._total) + '</td>';
                return '<tr>' + cells + '</tr>';
            }).join('');
            // 합계 행 (기준 칼럼들 병합, 개시일/종료일 칸 공란)
            var grand = revCatVals(recs);
            var totalCells = '<td class="rev-key" colspan="' + dims.length + '">합계</td>' +
                REV_CATS.map(function(c) { return '<td class="rev-amt">' + revFmtWon(grand[c]) + '</td>'; }).join('');
            if (withDates) { totalCells += '<td class="rev-date"></td><td class="rev-date"></td>'; }
            totalCells += '<td class="rev-amt">' + revFmtWon(grand._total) + '</td>';
            body += '<tr class="fee-row-total">' + totalCells + '</tr>';
            // 헤더: 첫 기준 칼럼 머리 셀에 버튼 편입. 활성 기준은 클릭 순서 번호 표시.
            var btns = REV_DIMS.map(function(b) {
                var idx = revActiveDims.indexOf(b[0]);
                var sty = idx !== -1 ? ' style="background:' + REV_ORD_SHADES[Math.min(idx, REV_ORD_SHADES.length - 1)] + ';color:#fff;"' : '';
                return '<button class="rev-viewbtn' + (idx !== -1 ? ' active' : '') +
                    '" data-rev-view="' + b[0] + '"' + sty + ' onclick="revToggleDim(this.dataset.revView, event)">' + b[1] + '</button>';
            }).join('');
            var dimHeads = dims.map(function(d, i) {
                return i === 0 ? '<th class="rev-headcell"><div class="rev-views">' + btns + '</div></th>'
                               : '<th>' + revDimHead(d) + '</th>';
            }).join('');
            var dateHeads = withDates ? '<th>개시일</th><th>종료일</th>' : '';
            var head = '<tr>' + dimHeads + REV_CATS.map(function(c) { return '<th>' + c + '</th>'; }).join('') + dateHeads + '<th>합계</th></tr>';
            document.getElementById('revTableHost').innerHTML =
                '<table class="fee-table rev-table"><thead>' + head + '</thead><tbody>' + body + '</tbody></table>';
        }
        revRender();
        </script>
    """.replace('__PAYLOAD__', payload)

    return head_html + script


def _fmt_jo_eok(won):
    """원 단위 금액 -> 'NN조 N,NNN억원' 표기 (사용자 금액 표기 규칙)."""
    eok = int(round(won / 1e8))
    jo, rem = divmod(eok, 10000)
    if jo > 0:
        return f"{jo}조 {rem:,}억원"
    return f"{eok:,}억원"


def _build_landing_kofia_section():
    """index.html(랜딩) 고객예탁금/신용잔고 Chart.js 카드 2개.

    데이터: 리포에 커밋된 kofia_stats.json (execution/fetch_kofia_stats.py가
    data.go.kr 금투협 종합통계 API로 생성, 단위: 원).
    파일이 없거나 비어 있으면 빈 문자열 반환 — API 키 없는 환경(VM 16:20 재생성 등)
    에서도 graceful하게 동작.
    """
    try:
        with open('kofia_stats.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        dep = data.get('deposit') or {}
        crd = data.get('credit') or {}
        if not dep.get('dates') or not dep.get('values') \
           or not crd.get('dates') or not crd.get('total'):
            print("kofia_stats.json empty - landing kofia section skipped")
            return ''
    except Exception as e:
        print(f"kofia_stats.json not available - landing kofia section skipped: {e}")
        return ''

    dep_latest = _fmt_jo_eok(dep['values'][-1])
    dep_latest_date = dep['dates'][-1]
    crd_latest = _fmt_jo_eok(crd['total'][-1])
    crd_latest_date = crd['dates'][-1]

    export_json = json.dumps({
        'deposit': {'dates': dep['dates'], 'values': dep['values']},
        'credit': {
            'dates': crd['dates'],
            'total': crd['total'],
            'kospi': crd.get('kospi') or [],
            'kosdaq': crd.get('kosdaq') or [],
        },
    }, ensure_ascii=False)

    section = """
        <style>
        .lh-kofia-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 10px; }
        .lh-kofia-title { font-size: 1.0rem; font-weight: 700; color: #111; }
        .lh-kofia-latest { font-size: 0.88rem; font-weight: 600; color: #333; }
        .lh-kofia-latest small { color: #888; font-weight: 500; margin-left: 4px; }
        .lh-kofia-legend { margin-top: 10px; text-align: center; color: #222; }
        </style>
        <div class="lh-card">
            <div class="lh-kofia-head">
                <span class="lh-kofia-title">고객예탁금</span>
                <span class="lh-kofia-latest">DEP_LATEST_PLACEHOLDER<small>(DEP_DATE_PLACEHOLDER)</small></span>
            </div>
            <div style="position:relative;height:240px;"><canvas id="kofiaDepositChart"></canvas></div>
        </div>
        <div class="lh-card">
            <div class="lh-kofia-head">
                <span class="lh-kofia-title">신용잔고 (신용거래융자)</span>
                <span class="lh-kofia-latest">CRD_LATEST_PLACEHOLDER<small>(CRD_DATE_PLACEHOLDER)</small></span>
            </div>
            <div style="position:relative;height:240px;"><canvas id="kofiaCreditChart"></canvas></div>
            <div id="kofiaCreditLegend" class="lh-kofia-legend"></div>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script>
        (function() {
            Chart.defaults.font.family = "'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif";
            Chart.defaults.devicePixelRatio = 2 * (window.devicePixelRatio || 1);
            Chart.defaults.elements.line.borderJoinStyle = 'round';
            Chart.defaults.elements.line.borderCapStyle = 'round';
            var KOFIA = KOFIA_DATA_PLACEHOLDER;
            function fmtJoEok(v) {
                var eok = Math.round(v / 1e8);
                var jo = Math.floor(eok / 10000), rem = eok % 10000;
                if (jo > 0) return jo + '조 ' + rem.toLocaleString('ko-KR') + '억원';
                return eok.toLocaleString('ko-KR') + '억원';
            }
            function kofiaOpts() {
                return {
                    responsive: true, maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: { display: false },
                        tooltip: { callbacks: { label: function(ctx) { return ctx.dataset.label + ': ' + (ctx.parsed.y === null ? '-' : fmtJoEok(ctx.parsed.y)); } } }
                    },
                    scales: {
                        x: { type: 'category', ticks: { maxTicksLimit: 6, callback: function(val) { var d = this.getLabelForValue(val); if (!d) return ''; return d.slice(2,4) + '/' + d.slice(5,7); }, maxRotation: 0, font: { size: 11 }, color: '#000' }, grid: { color: '#eee', display: true }, border: { color: '#000' } },
                        y: { ticks: { callback: function(v) { return Math.round(v / 1e11) / 10 + '조원'; }, font: { size: 11 }, color: '#000' }, grid: { color: '#eee' }, border: { color: '#000' } }
                    }
                };
            }
            function lineDs(label, data, color) {
                return { label: label, data: data, borderColor: color, backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.3, spanGaps: true };
            }
            new Chart(document.getElementById('kofiaDepositChart'), {
                type: 'line',
                data: { labels: KOFIA.deposit.dates, datasets: [lineDs('고객예탁금', KOFIA.deposit.values, '#1e3a8a')] },
                options: kofiaOpts()
            });
            var crdSets = [lineDs('합계', KOFIA.credit.total, '#dc2626')];
            if (KOFIA.credit.kospi && KOFIA.credit.kospi.length) crdSets.push(lineDs('코스피', KOFIA.credit.kospi, '#1976D2'));
            if (KOFIA.credit.kosdaq && KOFIA.credit.kosdaq.length) crdSets.push(lineDs('코스닥', KOFIA.credit.kosdaq, '#F57C00'));
            new Chart(document.getElementById('kofiaCreditChart'), {
                type: 'line',
                data: { labels: KOFIA.credit.dates, datasets: crdSets },
                options: kofiaOpts()
            });
            var legendEl = document.getElementById('kofiaCreditLegend');
            if (legendEl) {
                legendEl.innerHTML = crdSets.map(function(ds) {
                    return '<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px;font-size:13px;">' +
                        '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + ds.borderColor + ';"></span>' +
                        ds.label + '</span>';
                }).join('');
            }
        })();
        </script>
    """
    section = (section
               .replace('KOFIA_DATA_PLACEHOLDER', export_json)
               .replace('DEP_LATEST_PLACEHOLDER', dep_latest)
               .replace('DEP_DATE_PLACEHOLDER', dep_latest_date)
               .replace('CRD_LATEST_PLACEHOLDER', crd_latest)
               .replace('CRD_DATE_PLACEHOLDER', crd_latest_date))
    return section


def _build_contribution_section():
    """WRAP 기여도 탭.
    contribution_data.json 을 탭 첫 진입 시 지연 fetch → 포트폴리오 토글 + 날짜 범위 선택 +
    종목별 누적 기여도(bp) + 업종별 기여도 + DH(구분) 필터.
    저장된 일별 기여도(bp)는 가산값. 선택 구간은 Cariño 연결로 종목 합이 기하 포트수익률과 일치.
    """
    return """
    <div class="category-section" style="max-width:1800px;margin:0 auto;">
      <h2 class="category-title">기여도</h2>
      <div id="contribLoading" style="text-align:center;color:#888;padding:40px;">로딩 중...</div>
      <div id="contribBody" style="display:none;">
        <div id="contribPfToggle" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;"></div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
          <span style="color:#444;font-size:14px;font-weight:600;">기간</span>
          <input type="text" id="contribStart" maxlength="10" placeholder="YYYY-MM-DD" onchange="formatDateInput(this);renderContribution()" style="font-family:inherit;font-size:13px;padding:5px 8px;border:1px solid #d1d5db;border-radius:6px;background:#f9fafb;width:115px;text-align:center;">
          <span style="color:#888;">~</span>
          <input type="text" id="contribEnd" maxlength="10" placeholder="YYYY-MM-DD" onchange="formatDateInput(this);renderContribution()" style="font-family:inherit;font-size:13px;padding:5px 8px;border:1px solid #d1d5db;border-radius:6px;background:#f9fafb;width:115px;text-align:center;">
          <button onclick="contribResetRange()" style="font-family:inherit;font-size:12px;font-weight:600;padding:5px 12px;background:#f3f4f6;color:#444;border:1px solid #d1d5db;border-radius:6px;cursor:pointer;">전체</button>
          <span id="contribRangeHint" style="color:#888;font-size:12px;"></span>
        </div>
        <div style="display:flex;gap:40px;align-items:flex-start;flex-wrap:wrap;">
          <div style="flex:2;min-width:480px;">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
              <div style="font-size:15px;font-weight:700;color:#111;">종목별 누적 기여도 (bp)</div>
              <div style="display:flex;gap:6px;margin-left:auto;">
                <button id="contribFltAll" class="contrib-flt active" onclick="contribSetFilter(false)">전체</button>
                <button id="contribFltDh" class="contrib-flt" onclick="contribSetFilter(true)">DH</button>
              </div>
            </div>
            <div id="contribStockTable" style="overflow-x:auto;"></div>
          </div>
          <div style="flex:1;min-width:280px;">
            <div style="font-size:15px;font-weight:700;color:#111;margin-bottom:8px;">업종별 누적 기여도 (bp)</div>
            <div id="contribSectorTable"></div>
          </div>
        </div>
      </div>
    </div>
    <style>
      .contrib-tbl{border-collapse:separate;border-spacing:0;width:100%;font-size:13.5px;background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.06);overflow:hidden;}
      .contrib-tbl th{background:#f3f4f6;color:#444;font-weight:600;padding:9px 10px;text-align:center;white-space:nowrap;border-bottom:2px solid #e5e7eb;cursor:pointer;user-select:none;}
      .contrib-tbl td{padding:8px 10px;text-align:center;white-space:nowrap;border-bottom:1px solid #f0f0f0;}
      .contrib-tbl tr:last-child td{border-bottom:none;}
      .contrib-tbl tbody tr:hover{background:#fafafa;}
      .contrib-pos{color:#dc2626;font-weight:600;}
      .contrib-neg{color:#2563eb;font-weight:600;}
      .dh-pill{display:inline-block;background:#2563eb;color:#fff;font-size:11px;font-weight:700;padding:1px 7px;border-radius:10px;}
      .contrib-tbl tfoot td{border-top:2px solid #1f2937;font-weight:700;background:#fafafa;}
      .contrib-flt{font-family:inherit;font-size:12.5px;font-weight:600;padding:5px 12px;border-radius:8px;border:1px solid #d1d5db;background:#fff;color:#444;cursor:pointer;}
      .contrib-flt.active{background:#111;color:#fff;border-color:#111;}
    </style>
    <script>
    var CONTRIB_DATA=null, contribPf=null, contribSortKey='contrib', contribSortDir=-1, contribDhOnly=false;
    async function loadContribution(){
      if(CONTRIB_DATA) return;
      try{
        var resp=await fetch('contribution_data.json?cb='+Date.now());
        if(!resp.ok) throw new Error('HTTP '+resp.status);
        CONTRIB_DATA=await resp.json();
        var pfs=Object.keys(CONTRIB_DATA.portfolios);
        var tg=document.getElementById('contribPfToggle');
        tg.innerHTML=pfs.map(function(p){return '<button class="contrib-pf-btn" data-pf="'+p+'" onclick="contribSetPf(this.dataset.pf)" style="font-family:inherit;font-size:14px;font-weight:600;padding:6px 14px;border-radius:8px;border:1px solid #d1d5db;background:#fff;color:#444;cursor:pointer;">'+p+'</button>';}).join('');
        document.getElementById('contribLoading').style.display='none';
        document.getElementById('contribBody').style.display='block';
        contribSetPf(pfs[0]);
      }catch(e){
        document.getElementById('contribLoading').innerHTML='<span style="color:#dc2626;">기여도 데이터 로드 실패: '+e.message+'</span>';
      }
    }
    function contribSetPf(pf){
      contribPf=pf;
      document.querySelectorAll('.contrib-pf-btn').forEach(function(b){
        var on=b.dataset.pf===pf;
        b.style.background=on?'#dc2626':'#fff'; b.style.color=on?'#fff':'#444'; b.style.borderColor=on?'#dc2626':'#d1d5db';
      });
      contribResetRange();
    }
    function contribResetRange(){
      var d=CONTRIB_DATA.portfolios[contribPf];
      document.getElementById('contribStart').value=d.dates[0];
      document.getElementById('contribEnd').value=d.dates[d.dates.length-1];
      document.getElementById('contribRangeHint').textContent='(데이터 '+d.dates[0]+' ~ '+d.dates[d.dates.length-1]+')';
      renderContribution();
    }
    function contribSetFilter(dhOnly){
      contribDhOnly=dhOnly;
      document.getElementById('contribFltAll').classList.toggle('active',!dhOnly);
      document.getElementById('contribFltDh').classList.toggle('active',dhOnly);
      renderContribution();
    }
    function carinoFactors(prArr){
      var R=1,i; for(i=0;i<prArr.length;i++) R*=(1+prArr[i]); R-=1;
      var k=Math.abs(R)<1e-12?1:Math.log(1+R)/R;
      return prArr.map(function(pr){var kd=Math.abs(pr)<1e-12?1:Math.log(1+pr)/pr; return kd/k;});
    }
    function cbp(v){var c=v>=0?'contrib-pos':'contrib-neg'; return '<span class="'+c+'">'+(v>=0?'+':'')+Math.round(v).toLocaleString()+'</span>';}
    function contribSort(key){ if(contribSortKey===key) contribSortDir*=-1; else {contribSortKey=key; contribSortDir=(key==='name'||key==='sector')?1:-1;} renderContribution(); }
    function renderContribution(){
      if(!CONTRIB_DATA||!contribPf) return;
      var d=CONTRIB_DATA.portfolios[contribPf], dates=d.dates;
      var s=document.getElementById('contribStart').value, e=document.getElementById('contribEnd').value;
      var i0=0,i1=dates.length-1,i;
      for(i=0;i<dates.length;i++){ if(dates[i]>=s){i0=i;break;} }
      for(i=dates.length-1;i>=0;i--){ if(dates[i]<=e){i1=i;break;} }
      if(i0>i1){i0=0;i1=dates.length-1;}
      var n=i1-i0+1;
      var beta=carinoFactors(d.port_return.slice(i0,i1+1));
      var rows=[],sectors={},code,t,tot=0;
      for(code in d.stocks){
        var st=d.stocks[code], c=st.contrib, w=st.weight, sm=0, held=false;
        for(t=0;t<n;t++){ sm+=c[i0+t]*beta[t]; if(w[i0+t]>0) held=true; }
        if(!held) continue;
        rows.push({name:st.name,sector:st.sector,dh:st.dh,contrib:sm});
        tot+=sm; sectors[st.sector]=(sectors[st.sector]||0)+sm;
      }
      rows.sort(function(a,b){var av=a[contribSortKey],bv=b[contribSortKey]; if(typeof av==='string') return contribSortDir*av.localeCompare(bv,'ko'); return contribSortDir*(av-bv);});
      var shown=contribDhOnly?rows.filter(function(r){return r.dh;}):rows;
      var shownSum=0; shown.forEach(function(r){shownSum+=r.contrib;});
      function sarrow(k){return contribSortKey===k?(contribSortDir<0?' ▾':' ▴'):'';}
      var h='<table class="contrib-tbl"><thead><tr>'
        +'<th onclick="contribSort(\\'sector\\')">업종'+sarrow('sector')+'</th>'
        +'<th onclick="contribSort(\\'name\\')">종목'+sarrow('name')+'</th>'
        +'<th onclick="contribSort(\\'contrib\\')">기여도'+sarrow('contrib')+'</th>'
        +'<th onclick="contribSort(\\'dh\\')">구분'+sarrow('dh')+'</th></tr></thead><tbody>';
      if(!shown.length){ h+='<tr><td colspan="4" style="color:#888;padding:18px;">해당 종목 없음</td></tr>'; }
      shown.forEach(function(r){
        h+='<tr><td style="color:#666;">'+r.sector+'</td>'
          +'<td>'+r.name+'</td><td>'+cbp(r.contrib)+'</td>'
          +'<td>'+(r.dh?'<span class="dh-pill">DH</span>':'')+'</td></tr>';
      });
      h+='</tbody><tfoot><tr><td colspan="2">'+(contribDhOnly?'DH 합계':'합계')+'</td><td>'+cbp(shownSum)+'</td><td></td></tr></tfoot></table>';
      document.getElementById('contribStockTable').innerHTML=h;
      var sarr=Object.keys(sectors).map(function(k){return {sector:k,contrib:sectors[k]};}).sort(function(a,b){return b.contrib-a.contrib;});
      var sh='<table class="contrib-tbl"><thead><tr><th>업종</th><th>기여도</th></tr></thead><tbody>';
      sarr.forEach(function(r){ sh+='<tr><td>'+r.sector+'</td><td>'+cbp(r.contrib)+'</td></tr>'; });
      sh+='</tbody><tfoot><tr><td>합계</td><td>'+cbp(tot)+'</td></tr></tfoot></table>';
      document.getElementById('contribSectorTable').innerHTML=sh;
    }
    </script>
    """


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
        category_order = ['Indices', 'Wrap', 'Portfolio', 'SECTOR', 'INDEX_KOREA', 'INDEX_US', 'EXCHANGE RATE',
                         'INTEREST RATES', 'CRYPTOCURRENCY', 'Memory', 'COMMODITIES']

        # 통합 동적 차트로 묶이는 7개 카테고리 — 개별 PNG 그리드 렌더 스킵
        merged_into_combined = {
            'INDEX_KOREA', 'INDEX_US', 'EXCHANGE RATE', 'INTEREST RATES',
            'CRYPTOCURRENCY', 'Memory', 'COMMODITIES',
        }
        combined_rendered = False

        for category in category_order:
            # Indices는 동적 차트 (charts_by_category와 무관)
            if category == 'Indices':
                charts_html += _build_indices_chart_section('Indice')
                # Indices 직후에 통합 차트 1회 렌더
                if not combined_rendered:
                    charts_html += _build_combined_chart_section()
                    combined_rendered = True
                continue

            # 통합 차트로 묶이는 카테고리는 건너뜀
            if category in merged_into_combined:
                continue

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
            
            # Commodities order (includes battery metals)
            elif category == 'COMMODITIES':
                custom_order = [
                    'Gold',
                    'KRX GOLD Trading Volume',
                    'Silver',
                    'Copper',
                    'WTI Crude Oil',
                    'Brent Crude Oil',
                    'Natural Gas',
                    'Wheat',
                    'Uranium',
                    'Lithium Carbonate',
                    'Lithium Hydroxide',
                    'Poly Silicon',
                    'SCFI Comprehensive Index',
                    'KRX ETS  KAU25',
                    'KRX ETS Trading Volume',
                    'SMP'
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
                ]

            # Korea Indices order
            elif category == 'INDEX_KOREA':
                custom_order = [
                    'KOSPI',
                    'KOSPI/USD',
                    'KOSPI Market Cap',
                    'KOSDAQ',
                    'KOSDAQ/USD',
                    'KOSDAQ Market Cap'
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
            if category == 'Wrap':
                category_label = 'CHART'
            else:
                category_label = category

            # Add category header
            target = wrap_html if category == 'Wrap' else charts_html

            if category == 'Wrap':
                wrap_html += _build_wrap_chart_section(category_label)
                wrap_html += create_wrap_returns_table()
                wrap_html += create_aum_table()
                wrap_html += create_cumulative_aum_chart()
            else:
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
                charts_html += section

    # Generate full HTML
    now = datetime.now(tz=KST).strftime("%Y-%m-%d %H:%M:%S KST")

    monthly_returns_html = create_monthly_returns_table()

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Market Data Dashboard</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
    <style>
        :root {{
            --bg-color: #f8f9fa;
            --card-bg: #ffffff;
            --text-color: #333333;
            --accent-color: #2d7a3a;
            --category-bg: #eeeeee;
        }}

        body {{
            font-family: 'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif;
            font-size: 1.05rem;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 20px;
        }}

        header {{
            text-align: center;
            margin: 0 0 40px;
            padding: 20px 24px;
            position: relative;
        }}

        header h1 {{
            margin: 0;
            font-size: 33px;
            color: #333;
            font-weight: 700;
            line-height: 1.2;
        }}

        .last-updated {{
            margin-top: 10px;
            color: #6c757d;
            font-size: 15px;
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
            max-width: 1800px;
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
            color: #999;
            font-size: 14px;
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
            font-size: 16px;
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

        /* aum-aligned: colgroup width를 우선 적용 (상단 AUM/누적 AUM 컬럼 정렬 일치) */
        .portfolio-table.aum-aligned th,
        .portfolio-table.aum-aligned td {{
            width: auto;
        }}

        .portfolio-section-wrapper {{
            max-width: 1800px;
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
        {TOP_NAV_CSS}
    </style>
</head>
<body class="has-sidebar">
    {top_nav_html('market')}
    {sidebar_html('market')}
    <header>
        <h1>📊 Index</h1>
        <div class="last-updated">Updated: {now}</div>
    </header>

    {monthly_returns_html}

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

    # ── Generate index.html (Landing page) ──
    # 고객예탁금/신용잔고는 Market DATA(INDEX_KOREA)로 이전 — 랜딩에서 제외.
    landing_page = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Age of Emergence</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif; background: #f8f9fa; color: #333; min-height: 100vh; }}
        .lh-main {{ max-width: 800px; margin: 0 auto; padding: 56px 20px 40px; display: flex; flex-direction: column; align-items: center; }}
        h1 {{ font-size: 2.2rem; font-weight: 800; margin-bottom: 22px; color: #111; }}
        .lh-card {{ background: #fff; border-radius: 14px; padding: 14px 20px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); border: 1.5px solid #d1d5db; max-width: 800px; width: 100%; margin: 0 auto 26px auto; transition: transform 0.15s, box-shadow 0.15s; }}
        .lh-card:hover {{ transform: translateY(-2px); box-shadow: 0 6px 18px rgba(0,0,0,0.10); }}
        .lh-card[hidden] {{ display: none; }}
        .lh-chart-row {{ display: flex; align-items: center; gap: 14px; min-height: 90px; cursor: pointer; }}
        .lh-tag {{ flex: 0 0 90px; width: 90px; padding: 4px 0; background: #999; color: #fff; font-size: 0.72rem; font-weight: 700; border-radius: 999px; letter-spacing: 0.4px; text-align: center; white-space: nowrap; overflow: hidden; }}
        .lh-spark {{ flex: 0 0 auto; width: 202px; height: 80px; padding: 0 10px; border-left: 1px solid #000; border-right: 1px solid #000; display: flex; align-items: center; justify-content: center; }}
        .lh-spark svg {{ width: 180px; height: 80px; display: block; }}
        .lh-text {{ flex: 1 1 auto; font-size: 0.92rem; color: #333; line-height: 1.4; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .lh-shuffle {{ flex: 0 0 56px; width: 56px; background: none; border: none; cursor: pointer; font-size: 2.1rem; opacity: 0.9; padding: 8px 0; transition: opacity 0.15s, transform 0.2s; line-height: 1; color: inherit; text-align: center; display: inline-block; }}
        .lh-shuffle:hover {{ opacity: 1; transform: rotate(20deg); }}
        .lh-shuffle.rolling {{ animation: lh-roll 0.4s ease-out; }}
        @keyframes lh-roll {{
            0%   {{ transform: translateY(0)     rotate(0deg); }}
            50%  {{ transform: translateY(-16px) rotate(360deg); }}
            100% {{ transform: translateY(0)     rotate(720deg); }}
        }}
        .lh-divider {{ border: none; border-top: 1.5px solid #000; margin: 12px 0; }}
        .lh-quote-row {{ display: flex; align-items: center; padding: 4px 0 4px 20px; cursor: pointer; min-height: 36px; }}
        .lh-quote-text {{ flex: 1 1 auto; font-size: 0.92rem; color: #333; line-height: 1.55; white-space: normal; }}
        .lh-quote-text::before {{ content: "•"; color: #000; font-weight: bold; margin-right: 10px; }}
        .lh-author {{ color: #333; font-size: 1em; font-style: italic; margin-left: 8px; white-space: nowrap; }}
        @media (max-width: 600px) {{
            .lh-card {{ padding: 12px 14px; }}
            .lh-chart-row {{ flex-wrap: wrap; gap: 10px; }}
            .lh-text {{ white-space: normal; flex-basis: 100%; order: 4; font-size: 0.85rem; }}
            .lh-spark {{ width: 162px; height: 62px; }}
            .lh-spark svg {{ width: 140px; height: 62px; }}
        }}
        footer {{ margin-top: 48px; color: #999; font-size: 14px; }}
        {TOP_NAV_CSS}
    </style>
</head>
<body>
    {top_nav_html('')}
    <main class="lh-main">
        <h1>Age of Emergence</h1>
        <div id="landing-card" class="lh-card" hidden>
            <div class="lh-chart-row">
                <span class="lh-tag">—</span>
                <span class="lh-spark"></span>
                <span class="lh-text">—</span>
                <button class="lh-shuffle" type="button" title="다시 뽑기" aria-label="다시 뽑기">🎲</button>
            </div>
            <hr class="lh-divider">
            <div class="lh-quote-row">
                <span class="lh-quote-text">—</span>
            </div>
        </div>
        <footer>Age of Emergence</footer>
    </main>
    <script>
    (function() {{
        var card = document.getElementById('landing-card');
        if (!card) return;
        var chartRow = card.querySelector('.lh-chart-row');
        var quoteRow = card.querySelector('.lh-quote-row');
        var tagEl = chartRow.querySelector('.lh-tag');
        var sparkEl = chartRow.querySelector('.lh-spark');
        var textEl = chartRow.querySelector('.lh-text');
        var shuffleBtn = chartRow.querySelector('.lh-shuffle');
        var quoteTextEl = quoteRow.querySelector('.lh-quote-text');

        var slots = [];
        var quotes = [];
        var currentSlot = null;
        var prevSlotId = '';
        var prevQuoteIdx = -1;
        var TREND = {{ up: '#dc2626', down: '#1e40af', flat: '#555' }};

        try {{ prevSlotId = sessionStorage.getItem('lh_prev_id') || ''; }} catch (e) {{}}
        try {{ prevQuoteIdx = parseInt(sessionStorage.getItem('lh_quote_prev') || '-1', 10); }} catch (e) {{}}

        function escapeHtml(s) {{
            return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }}

        function renderSpark(spark) {{
            if (!spark || !spark.series || spark.series.length < 2) {{
                sparkEl.innerHTML = '';
                return;
            }}
            var vals = spark.series;
            var w = 180, h = 80, pad = 5;
            var mn = Math.min.apply(null, vals);
            var mx = Math.max.apply(null, vals);
            var range = (mx - mn) || 1;
            var stepX = (w - pad * 2) / (vals.length - 1);
            var pts = [];
            for (var i = 0; i < vals.length; i++) {{
                var x = pad + i * stepX;
                var y = h - pad - ((vals[i] - mn) / range) * (h - pad * 2);
                pts.push(x.toFixed(1) + ',' + y.toFixed(1));
            }}
            var color = TREND[spark.trend] || '#555';
            sparkEl.innerHTML =
                '<svg viewBox="0 0 ' + w + ' ' + h + '" xmlns="http://www.w3.org/2000/svg">' +
                '<path d="M' + pts.join(' L') + '" fill="none" stroke="' + color +
                '" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>' +
                '</svg>';
        }}

        function renderSlot(slot) {{
            currentSlot = slot;
            var color = slot.color || '#999';
            tagEl.textContent = slot.category || '';
            tagEl.style.backgroundColor = color;
            var html = escapeHtml(slot.text || '').replace(/\(([^)]+)\)/g, function(m, inner) {{
                if (/^[월화수목금토일]$/.test(inner)) return m;
                return '(<b><u>' + inner + '</u></b>)';
            }});
            textEl.innerHTML = html;
            renderSpark(slot.spark);
            prevSlotId = slot.id;
            try {{ sessionStorage.setItem('lh_prev_id', slot.id); }} catch (e) {{}}
        }}

        function renderQuote(idx) {{
            if (idx < 0 || idx >= quotes.length) return;
            var q = quotes[idx];
            var html = escapeHtml(q.text || '');
            if (q.author) {{
                html += ' <span class="lh-author">— ' + escapeHtml(q.author) + '</span>';
            }}
            quoteTextEl.innerHTML = html;
            prevQuoteIdx = idx;
            try {{ sessionStorage.setItem('lh_quote_prev', String(idx)); }} catch (e) {{}}
        }}

        function pickSlot() {{
            if (!slots.length) return null;
            var pool = slots.filter(function(s) {{ return s.id !== prevSlotId; }});
            if (!pool.length) pool = slots;
            return pool[Math.floor(Math.random() * pool.length)];
        }}

        function pickQuoteIdx() {{
            if (!quotes.length) return -1;
            if (quotes.length === 1) return 0;
            var idx;
            do {{ idx = Math.floor(Math.random() * quotes.length); }} while (idx === prevQuoteIdx);
            return idx;
        }}

        function shuffleAll() {{
            var slot = pickSlot();
            if (slot) renderSlot(slot);
            var idx = pickQuoteIdx();
            if (idx >= 0) renderQuote(idx);
        }}

        chartRow.addEventListener('click', function(e) {{
            if (e.target.closest('.lh-shuffle')) return;
            if (currentSlot && currentSlot.href) window.location.href = currentSlot.href;
        }});

        quoteRow.addEventListener('click', function() {{
            shuffleBtn.click();
        }});

        shuffleBtn.addEventListener('click', function(e) {{
            e.stopPropagation();
            shuffleBtn.classList.remove('rolling');
            void shuffleBtn.offsetWidth;
            shuffleBtn.classList.add('rolling');
            shuffleAll();
        }});

        Promise.all([
            fetch('landing_highlights.json?t=' + Date.now()).then(function(r) {{ return r.ok ? r.json() : null; }}),
            fetch('landing_quotes.json?t=' + Date.now()).then(function(r) {{ return r.ok ? r.json() : []; }})
        ]).then(function(results) {{
            var hl = results[0];
            slots = (hl && Array.isArray(hl.slots)) ? hl.slots : [];
            if (hl && hl.updated_at) card.title = 'Updated ' + hl.updated_at;
            quotes = Array.isArray(results[1]) ? results[1] : [];
            var slot = pickSlot();
            if (slot) renderSlot(slot);
            var idx = pickQuoteIdx();
            if (idx >= 0) renderQuote(idx);
            card.hidden = false;
        }}).catch(function() {{ /* hide silently */ }});
    }})();
    </script>
</body>
</html>"""

    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(landing_page)
    print("Landing page generated: index.html")

    # ── Generate wrap.html (WRAP + Portfolio + Sector + 공시/Order/수수료 tabs) ──
    order_html = create_order_section()
    fee_rate_html = create_fee_section()
    fee_revenue_html = create_fee_revenue_section()
    fee_html = f"""
        <div class="fee-subtabs">
            <button class="fee-subtab active" data-fee-sub="rate" onclick="feeSwitchSub('rate')">수수료율</button>
            <button class="fee-subtab" data-fee-sub="revenue" onclick="feeSwitchSub('revenue')">매출</button>
        </div>
        <div id="feeSubRate">{fee_rate_html}</div>
        <div id="feeSubRevenue" style="display:none;">{fee_revenue_html}</div>
    """
    disclosures_html = create_disclosures_section()
    contribution_html = _build_contribution_section()
    wrap_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WRAP</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
    <style>
        :root {{ --bg-color: #f8f9fa; --card-bg: #ffffff; --text-color: #333333; }}
        body {{ font-family: 'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif; font-size: 1.05rem; background-color: var(--bg-color); color: var(--text-color); margin: 0; padding: 20px; }}
        header {{ text-align: center; margin-bottom: 40px; padding: 20px; background-color: #000000; border-radius: 12px; }}
        h1 {{ margin: 0; font-size: 33px; color: #ffffff; }}
        .last-updated {{ margin-top: 10px; color: #6c757d; font-size: 15px; font-style: italic; }}
        .nav-group {{ display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; justify-content: center; }}
        .nav-button {{ display: inline-block; padding: 8px 20px; background-color: #2d7a3a; color: #ffffff; text-decoration: none; border-radius: 8px; font-size: 0.95rem; font-weight: 600; transition: background-color 0.2s; }}
        .nav-button:hover {{ background-color: #357abd; }}
        .category-section {{ margin-bottom: 50px; }}
        .category-title {{ font-size: 1.8rem; color: #000000; margin-bottom: 20px; padding: 10px 16px; background-color: #e0e0e0; border-left: 4px solid #000000; border-radius: 4px; text-transform: uppercase; }}
        .category-date {{ font-size: 1rem; font-weight: bold; color: #555; text-transform: none; }}
        .dashboard-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(600px, 1fr)); gap: 20px; max-width: 1800px; margin: 0 auto; }}
        @media (max-width: 768px) {{ .dashboard-grid {{ grid-template-columns: 1fr; }} }}
        .chart-card {{ background-color: var(--card-bg); border-radius: 12px; padding: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: transform 0.2s ease; text-align: center; }}
        .chart-card:hover {{ transform: translateY(-5px); }}
        .chart-card img {{ max-width: 100%; height: auto; border-radius: 8px; }}
        footer {{ text-align: center; margin-top: 50px; color: #999; font-size: 14px; }}
        /* Portfolio */
        .portfolio-section {{ margin-bottom: 40px; }}
        .portfolio-title {{ font-size: 1.4rem; color: #333; margin-bottom: 15px; padding-bottom: 8px; border-bottom: 1px solid #dee2e6; }}
        .update-time {{ font-size: 0.75rem; font-weight: bold; color: #555; }}
        .table-container {{ overflow-x: auto; background-color: var(--card-bg); border-radius: 8px; padding: 15px; }}
        .portfolio-table {{ width: 100%; border-collapse: collapse; font-size: 16px; }}
        .portfolio-table thead {{ background-color: #e9ecef; }}
        .portfolio-table th {{ padding: 12px 10px; text-align: center; font-weight: 600; color: #000; border-bottom: 2px solid #000; }}
        .portfolio-table td {{ padding: 10px; border-bottom: 1px solid #dee2e6; color: #333; text-align: center; }}
        .portfolio-table tbody tr:hover {{ background-color: #f5f5f5; }}
        .portfolio-table .number {{ text-align: right; }}
        .portfolio-table th:first-child, .portfolio-table td:first-child {{ width: 50px; text-align: center; }}
        .portfolio-table.aum-aligned th, .portfolio-table.aum-aligned td {{ width: auto; line-height: 24px; box-sizing: border-box; }}
        .portfolio-table.aum-aligned td {{ padding: 10px; }}
        .portfolio-table.aum-aligned th {{ padding: 12px 10px; }}
        /* 누적 AUM 목표전환형 행: hover 가능 affordance (연한 cool grey-blue 배경) */
        .portfolio-table.aum-aligned .iter-row > td {{ background-color: #e1ebf6; }}
        .portfolio-table.aum-aligned .iter-row:hover > td {{ background-color: #cfdef0; }}
        /* 누적 AUM 목표전환형 행: 회차별 detail hover tooltip */
        .iter-tooltip {{ display: none; position: absolute; left: 100%; top: 0; margin-left: 12px; background: #fff; box-shadow: 0 4px 10px rgba(0,0,0,0.18); z-index: 100; white-space: nowrap; font-size: 13px; font-weight: 400; }}
        .iter-row:hover .iter-tooltip {{ display: block; }}
        .iter-tooltip .iter-table {{ border-collapse: collapse; }}
        .iter-tooltip .iter-table th {{ padding: 8px 12px; background: #e9ecef; border-bottom: 2px solid #000; font-weight: 600; text-align: center; color: #000; }}
        .iter-tooltip .iter-table td {{ padding: 6px 12px; border-bottom: 1px solid #dee2e6; text-align: center; color: #333; }}
        .wrap-chart-item {{ cursor: pointer; transition: all 0.15s; }}
        .wrap-chart-item:hover td {{ background: #e9ecef; }}
        .wrap-chart-item.active td {{ background: #222; color: #fff; }}
        .wrap-tabs {{ display: flex; justify-content: center; gap: 0; background: #fff; border-bottom: 1px solid #eee; margin-bottom: 20px; position: sticky; top: 0; z-index: 100; }}
        .wrap-tab {{ padding: 14px 28px; border: none; background: none; font-size: 0.95rem; font-weight: 600; color: #999; cursor: pointer; border-bottom: 3px solid transparent; transition: all 0.2s; }}
        .wrap-tab:hover {{ color: #333; }}
        .wrap-tab.active {{ color: #1e40af; border-bottom-color: #1e40af; }}
        .wrap-mode-btn {{ padding: 6px 16px; border: 1px solid #dee2e6; border-radius: 6px; background: #f5f5f5; color: #555; font-size: 0.85rem; font-weight: 600; cursor: pointer; transition: all 0.15s; }}
        .wrap-mode-btn:hover {{ background: #e9ecef; }}
        .wrap-mode-btn.active {{ background: #222; color: #fff; border-color: #222; }}
        .portfolio-section-wrapper {{ max-width: 1800px; margin: 0 auto; }}
        .portfolio-table .positive {{ color: #cc0000; font-weight: 600; }}
        .portfolio-table .negative {{ color: #0055cc; font-weight: 600; }}
        .portfolio-table .total-row {{ background-color: #e9ecef; border-top: 2px solid #000; }}
        .portfolio-table .total-row td {{ font-weight: 600; padding: 12px 10px; }}
        /* Sector */
        .sector-card {{ background: var(--card-bg); border-radius: 8px; padding: 20px; margin-bottom: 30px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); }}
        .sector-card-title {{ font-size: 1.35rem; color: #111; margin: 0 0 10px 0; padding-bottom: 8px; border-bottom: 1px solid #ddd; }}
        .sect-portfolio-date, .sect-kodex-date {{ font-size: 0.85rem; font-weight: 700; color: #555; }}
        .sect-bm-1m {{ font-size: 0.88rem; font-weight: 600; color: #111; margin-left: 10px; }}
        .sect-vs {{ color: #111; font-weight: 400; font-size: 1.0rem; margin: 0 4px; }}
        .sect-note {{ font-size: 0.85rem; font-weight: 400; color: #666; }}
        .sector-legend {{ display: flex; align-items: center; gap: 16px; font-size: 0.92rem; color: #333; }}
        .legend-item {{ display: flex; align-items: center; gap: 5px; }}
        .legend-dot {{ width: 12px; height: 12px; border-radius: 2px; display: inline-block; flex-shrink: 0; }}
        .portfolio-dot {{ background: #2d7a3a; }}
        .kodex-dot {{ background: #444; }}
        .sector-table-wrap {{ overflow-x: auto; }}
        .sector-table {{ width: 100%; border-collapse: collapse; font-size: 1.0rem; }}
        .sector-table th {{ padding: 8px 12px; text-align: left; font-weight: 600; color: #111; border-bottom: 2px solid #111; background: #f0f0f0; white-space: nowrap; }}
        .sector-table td {{ padding: 6px 12px; border-bottom: 1px solid #eee; vertical-align: middle; }}
        .sect-name {{ min-width: 90px; font-weight: 500; white-space: nowrap; }}
        .sect-num {{ text-align: center; font-size: 0.95rem; white-space: nowrap; width: 64px; }}
        .sector-table thead th {{ text-align: center; }}
        .sect-diff {{ text-align: center; font-weight: 600; white-space: nowrap; width: 44px; min-width: 44px; max-width: 44px; }}
        .sect-over {{ color: #cc0000; }}
        .sect-under {{ color: #0055cc; }}
        .sect-neutral {{ color: #777; }}
        .sector-header-bar {{ display: grid; grid-template-columns: 3fr 2fr; gap: 0 24px; align-items: center; margin-bottom: 10px; }}
        .sect-not-held-label {{ font-size: 0.95rem; font-weight: 700; color: #111; text-align: center; padding-bottom: 4px; border-bottom: 1px solid #ddd; }}
        .sector-three-panel {{ display: grid; grid-template-columns: 3fr 1fr 1fr; gap: 24px; align-items: start; }}
        .sect-panel-title {{ font-size: 0.93rem; font-weight: 600; color: #111; text-align: center; margin: 0 0 8px 0; padding-bottom: 4px; border-bottom: 1px solid #ddd; }}
        .sect-right-val {{ text-align: right; font-weight: 600; white-space: nowrap; min-width: 60px; font-size: 0.95rem; padding-right: 8px !important; }}
        .sect-no-data {{ color: #aaa; font-size: 0.93rem; text-align: center; padding: 8px !important; }}
        .sect-right-stocks {{ font-size: 0.83rem; color: #444; font-weight: 500; padding: 0 8px 5px 12px !important; border-bottom: 1px solid #eee; }}
        .sect-detail-row td {{ padding: 0 12px 6px 12px !important; border-bottom: 1px solid #eee; }}
        .sect-detail {{ font-size: 0.85rem; color: #888; line-height: 1.4; }}
        .sect-detail-mine {{ color: #2d7a3a; font-weight: 700; }}
        .sect-detail-bm {{ color: #444; font-weight: 500; }}
        .sect-detail-sep {{ color: #ccc; }}
        @media (max-width: 800px) {{ .sector-header-bar, .sector-three-panel {{ grid-template-columns: 1fr; }} }}
        /* Returns Table */
        .rt-table {{ width:100%; border-collapse:collapse; font-size:0.9rem; }}
        .rt-nh {{ width:130px; padding:7px 10px; text-align:center; font-weight:600; color:#111; border-bottom:2px solid #111; background:#f0f0f0; }}
        .rt-ph {{ padding:7px 10px; text-align:center; font-weight:600; color:#111; border-bottom:2px solid #111; background:#f0f0f0; white-space:nowrap; min-width:54px; }}
        .rt-name {{ padding:8px 10px; text-align:center; font-weight:600; border-bottom:1px solid #eee; white-space:nowrap; }}
        .rt-cell {{ padding:8px 10px; text-align:center; border-bottom:1px solid #eee; font-variant-numeric:tabular-nums; white-space:nowrap; }}
        .rt-pos {{ color:#cc0000; font-weight:600; }}
        .rt-neg {{ color:#0055cc; font-weight:600; }}
        .rt-zero {{ color:#555; }}
        .rt-na {{ color:#bbb; }}
        .rt-divider-left {{ border-left:1px solid #c0c0c0; }}
        .rt-table tbody tr:hover td {{ background:#f9fafb; }}
        /* Fee table */
        .fee-wrapper {{ max-width: 900px; margin: 0 auto; background: var(--card-bg); border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
        .fee-title {{ margin: 0 0 18px 0; font-size: 1.3rem; color: #111; }}
        .fee-table {{ width: 100%; border-collapse: collapse; font-size: 0.98rem; }}
        .fee-table thead th {{ padding: 12px 10px; text-align: center; font-weight: 600; color: #000; background: #e9ecef; border-bottom: 2px solid #000; white-space: nowrap; }}
        .fee-table td {{ padding: 11px 10px; text-align: center; border-bottom: 1px solid #dee2e6; color: #333; }}
        .fee-broker {{ font-weight: 700; font-size: 1.05rem; color: #111; background: #f5f7fa; border-right: 1px solid #dee2e6; }}
        .fee-type {{ font-weight: 600; color: #1e40af; border-right: 1px solid #dee2e6; }}
        .fee-target {{ font-weight: 600; color: #111; border-right: 1px solid #dee2e6; font-variant-numeric: tabular-nums; }}
        .fee-share {{ color: #555; font-size: 0.92rem; white-space: nowrap; }}
        .fee-val {{ font-variant-numeric: tabular-nums; }}
        .fee-none {{ color: #9ca3af; font-style: italic; vertical-align: middle; }}
        .fee-row-total td {{ background: #f5f7fa; font-weight: 600; color: #111; border-bottom: 1px solid #c8ccd1; }}
        .fee-row-total .fee-share {{ color: #111; }}
        .fee-hurdle {{ font-size: 0.78rem; font-weight: 500; color: #6b7280; white-space: nowrap; }}
        .fee-tip {{ position: relative; cursor: help; border-bottom: 1px dotted #888; color: #0d3b8c; font-weight: 700; }}
        .fee-tip .fee-tip-box {{ display: none; position: absolute; left: 50%; transform: translateX(-50%); bottom: 135%; background: #222; color: #fff; padding: 10px 14px; border-radius: 6px; font-size: 0.82rem; font-weight: 400; line-height: 1.6; white-space: nowrap; z-index: 200; box-shadow: 0 4px 12px rgba(0,0,0,0.25); text-align: left; }}
        .fee-tip .fee-tip-box::after {{ content: ''; position: absolute; top: 100%; left: 50%; transform: translateX(-50%); border: 6px solid transparent; border-top-color: #222; }}
        .fee-tip:hover .fee-tip-box, .fee-tip:focus .fee-tip-box {{ display: block; }}
        .fee-tip-box .tip-list {{ margin: 0; padding-left: 1.3em; list-style-type: disc; }}
        .fee-tip-box .tip-list ul {{ margin: 5px 0 0 0; padding-left: 1.4em; list-style-type: circle; }}
        .fee-tip-box .tip-list li {{ margin: 3px 0; }}
        .fee-note {{ margin: 16px 0 0 0; font-size: 0.85rem; color: #888; }}
        /* Fee sub-tabs (수수료율 / 매출) */
        .fee-subtabs {{ display: flex; justify-content: center; gap: 8px; margin: 0 auto 20px auto; max-width: 900px; }}
        .fee-subtab {{ padding: 9px 26px; border: 1.5px solid #d1d5db; background: #fff; border-radius: 999px; font-size: 0.92rem; font-weight: 600; color: #666; cursor: pointer; font-family: inherit; transition: all 0.15s; }}
        .fee-subtab:hover {{ color: #1e40af; border-color: #1e40af; }}
        .fee-subtab.active {{ color: #fff; background: #1e40af; border-color: #1e40af; }}
        /* 매출 (revenue) */
        .rev-empty {{ text-align: center; color: #888; padding: 40px 12px; line-height: 1.8; }}
        .rev-empty code {{ background: #f1f3f5; padding: 2px 7px; border-radius: 5px; font-size: 0.9em; color: #1e40af; }}
        .rev-wrapper {{ position: relative; }}
        .rev-summary {{ text-align: center; padding: 18px 12px 6px 12px; }}
        .rev-sum-label {{ font-size: 0.95rem; color: #111; font-weight: 600; }}
        .rev-sum-value {{ font-size: 1.5rem; font-weight: 700; color: #111; margin-top: 4px; font-variant-numeric: tabular-nums; }}
        .rev-updated {{ position: absolute; top: 20px; right: 24px; font-size: 0.78rem; color: #aaa; }}
        .rev-date {{ color: #555; font-size: 0.9rem; font-variant-numeric: tabular-nums; }}
        .rev-headcell {{ padding: 7px 10px !important; }}
        .rev-views {{ display: inline-flex; gap: 5px; margin: 0; background: #fff; padding: 3px; border-radius: 999px; box-shadow: inset 0 0 0 1px #d8dde3; }}
        .rev-viewbtn {{ padding: 5px 14px; border: none; background: transparent; border-radius: 999px; font-size: 0.82rem; font-weight: 600; color: #555; cursor: pointer; font-family: inherit; transition: all 0.15s; white-space: nowrap; }}
        .rev-viewbtn:hover {{ color: #1e40af; }}
        .rev-viewbtn.active {{ color: #fff; background: #1e40af; }}
        .rev-table {{ margin: 0 auto; }}
        .rev-table td, .rev-table th {{ white-space: nowrap; text-align: center !important; }}
        .rev-key {{ font-weight: 600; color: #111; }}
        .rev-amt {{ font-variant-numeric: tabular-nums; }}
        .rev-rowtot {{ font-weight: 600; color: #111; }}
        /* Password overlay */
        .pw-overlay {{
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: #f8f9fa; display: flex; align-items: center; justify-content: center;
            z-index: 9999;
        }}
        .pw-box {{
            background: #fff; padding: 40px; border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15); text-align: center; max-width: 360px; width: 90%;
        }}
        .pw-box h2 {{ margin: 0 0 20px 0; font-size: 1.4rem; color: #333; }}
        .pw-box input {{
            width: 100%; padding: 12px; font-size: 1.1rem; border: 2px solid #ddd;
            border-radius: 8px; text-align: center; outline: none; box-sizing: border-box;
        }}
        .pw-box input:focus {{ border-color: #1e40af; }}
        .pw-box button {{
            margin-top: 14px; padding: 10px 40px; font-size: 1rem; font-weight: 600;
            background: #1e40af; color: #fff; border: none; border-radius: 8px; cursor: pointer;
        }}
        .pw-box button:hover {{ background: #1e3a8a; }}
        .pw-error {{ color: #dc2626; font-size: 0.9rem; margin-top: 10px; display: none; }}
        .pw-hidden {{ display: none !important; }}
        {TOP_NAV_CSS}
    </style>
</head>
<body>
    <div id="pwOverlay" class="pw-overlay">
        <div class="pw-box">
            <h2>🔒 Password Required</h2>
            <input type="password" id="pwInput" placeholder="비밀번호 입력" autofocus
                   onkeydown="if(event.key==='Enter')checkPw()">
            <button onclick="checkPw()">확인</button>
            <div id="pwError" class="pw-error">비밀번호가 틀렸습니다.</div>
        </div>
    </div>

    <div id="mainContent" class="pw-hidden has-sidebar">
    {top_nav_html('wrap')}
    {wrap_sidebar_html()}
    <header>
        <h1>📈 WRAP</h1>
        <div class="last-updated">Updated: {now}</div>
    </header>

    <div id="wrapPanelDashboard" style="padding-top:24px;">
    {wrap_html}
    </div>

    <div id="wrapPanelContribution" style="padding-top:24px;display:none;">
    {contribution_html}
    </div>

    <div id="wrapPanelDisclosures" style="padding-top:24px;display:none;">
    {disclosures_html}
    </div>

    <div id="wrapPanelOrder" style="padding-top:24px;display:none;max-width:1800px;margin:0 auto;">
    {order_html}
    </div>

    <div id="wrapPanelFee" style="padding-top:24px;display:none;max-width:1800px;margin:0 auto;">
    {fee_html}
    </div>

    <footer><p>Auto-generated by Antigravity Agent</p></footer>
    </div>

    <script>
    async function sha256(msg) {{
        const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(msg));
        return Array.from(new Uint8Array(buf)).map(b=>b.toString(16).padStart(2,'0')).join('');
    }}
    async function checkPw() {{
        const hash = await sha256(document.getElementById('pwInput').value);
        if (hash === '7d78e91672fb21bfd70f2c3a5df40ee3d3cf052ae66a133df53822cc8bad44ee') {{
            document.getElementById('pwOverlay').style.display = 'none';
            document.getElementById('mainContent').classList.remove('pw-hidden');
            sessionStorage.setItem('wrap_auth', '1');
            if (typeof wrapTabFromHash === 'function') wrapTabFromHash();
        }} else {{
            document.getElementById('pwError').style.display = 'block';
            document.getElementById('pwInput').value = '';
            document.getElementById('pwInput').focus();
        }}
    }}
    if (sessionStorage.getItem('wrap_auth') === '1') {{
        document.getElementById('pwOverlay').style.display = 'none';
        document.getElementById('mainContent').classList.remove('pw-hidden');
    }}

    // Order 탭 추가 비밀번호 (sha256('2026'))
    var ORDER_AUM_PW_HASH = '158a323a7ba44870f23d96f1516dd70aa48e9a72db4ebb026b0a89e212a208ab';

    async function checkOrderAumPw() {{
        if (sessionStorage.getItem('order_aum_auth') === '1') return true;
        var pw = prompt('Order 탭 비밀번호 입력');
        if (!pw) return false;
        var hash = await sha256(pw);
        if (hash === ORDER_AUM_PW_HASH) {{
            sessionStorage.setItem('order_aum_auth', '1');
            return true;
        }}
        alert('비밀번호가 틀렸습니다.');
        return false;
    }}

    async function wrapSwitchTab(tab) {{
        // Order / 기여도 진입 시 추가 비밀번호 체크 (sha256('2026'), 동일 게이트 공유)
        if ((tab === 'order' || tab === 'contribution') && !(await checkOrderAumPw())) {{
            return;  // 인증 실패 시 탭 전환 취소
        }}
        document.querySelectorAll('.sidebar-link[data-wrap-tab]').forEach(function(el) {{
            el.classList.toggle('active', el.getAttribute('data-wrap-tab') === tab);
        }});
        document.getElementById('wrapPanelDashboard').style.display = tab === 'dashboard' ? 'block' : 'none';
        document.getElementById('wrapPanelContribution').style.display = tab === 'contribution' ? 'block' : 'none';
        document.getElementById('wrapPanelDisclosures').style.display = tab === 'disclosures' ? 'block' : 'none';
        document.getElementById('wrapPanelOrder').style.display = tab === 'order' ? 'block' : 'none';
        document.getElementById('wrapPanelFee').style.display = tab === 'fee' ? 'block' : 'none';
        if (tab === 'contribution' && typeof loadContribution === 'function') loadContribution();
        if (tab === 'disclosures' && typeof loadDisclosures === 'function') loadDisclosures();
        if (tab === 'order' && typeof loadOrder === 'function') loadOrder();
    }}

    // 수수료 탭 내부 서브탭 (수수료율 / 매출)
    function feeSwitchSub(which) {{
        document.querySelectorAll('.fee-subtab[data-fee-sub]').forEach(function(el) {{
            el.classList.toggle('active', el.getAttribute('data-fee-sub') === which);
        }});
        var rate = document.getElementById('feeSubRate');
        var rev = document.getElementById('feeSubRevenue');
        if (rate) rate.style.display = which === 'rate' ? 'block' : 'none';
        if (rev) rev.style.display = which === 'revenue' ? 'block' : 'none';
    }}

    // 상단 네비 WRAP 드롭다운 / 타 페이지에서 wrap.html#tab 진입 시 해당 탭으로 전환
    function wrapTabFromHash() {{
        var h = (location.hash || '').replace('#', '');
        if (['dashboard', 'contribution', 'disclosures', 'order', 'fee'].indexOf(h) !== -1) wrapSwitchTab(h);
    }}
    window.addEventListener('hashchange', wrapTabFromHash);
    if (sessionStorage.getItem('wrap_auth') === '1') wrapTabFromHash();
    </script>
</body>
</html>"""

    with open('wrap.html', 'w', encoding='utf-8') as f:
        f.write(wrap_page)
    print("WRAP page generated: wrap.html")

    # Universe page
    universe_page = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Universe</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
    <script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif; font-size: 1.05rem; background: #f8f9fa; color: #333; }
        header { padding: 20px 24px; margin: 0 0 40px; text-align: center; position: relative; }
        header h1 { margin: 0; font-size: 33px; color: #333; font-weight: 700; line-height: 1.2; }
        .last-updated { margin-top: 10px; color: #6c757d; font-size: 15px; font-style: italic; }
        .nav-group { margin-top: 10px; }
        .nav-button { display: inline-block; padding: 6px 16px; border-radius: 6px; text-decoration: none; color: #fff; font-size: 0.85rem; font-weight: 600; background: #333; }
        .content { padding: 24px; max-width: 1800px; margin: 0 auto; }
        .tabs { display: flex; gap: 0; margin-bottom: 20px; border-bottom: 2px solid #2d7a3a; }
        .tab { padding: 10px 24px; cursor: pointer; font-weight: 600; font-size: 16px; color: #666; border: 1px solid transparent; border-bottom: none; border-radius: 8px 8px 0 0; background: #f0f0f0; }
        .tab.active { color: #2d7a3a; background: #fff; border-color: #2d7a3a #2d7a3a transparent; margin-bottom: -2px; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .filters { margin-bottom: 16px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .filters select { padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px; background: #fff; text-align: center; text-align-last: center; }
        .csel-wrap { position: relative; display: inline-block; }
        .csel-display { padding: 8px 28px 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px; background: #fff; text-align: center; cursor: pointer; min-width: 100px; user-select: none; font-family: inherit; position: relative; }
        .csel-display::after { content: ''; position: absolute; right: 10px; top: 50%; transform: translateY(-50%); border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 5px solid #666; }
        .csel-list { display: none; position: absolute; top: 100%; left: 0; right: 0; background: #fff; border: 1px solid #d1d5db; border-radius: 6px; margin-top: 2px; z-index: 100; box-shadow: 0 2px 8px rgba(0,0,0,0.12); }
        .csel-list.open { display: block; }
        .csel-item { padding: 8px 12px; text-align: center; cursor: pointer; font-size: 14px; font-family: inherit; }
        .csel-item:hover { background: #f0f7f2; }
        .csel-item.selected { background: #2d7a3a; color: #fff; }
        .sector-group { margin-bottom: 24px; }
        .sector-group h3 { font-size: 18px; color: #2d7a3a; margin-bottom: 8px; padding: 8px 0; border-bottom: 1px solid #2d7a3a; }
        table { width: 100%; border-collapse: collapse; font-size: 16px; table-layout: fixed; }
        thead { background: #e9ecef; }
        th { padding: 12px 6px; text-align: center; font-weight: 600; color: #000; cursor: pointer; white-space: nowrap; overflow: hidden; position: sticky; top: 0; background: #e9ecef; z-index: 10; box-shadow: inset 0 -2px 0 #000; }
        th:hover { background: #ddd; }
        td { padding: 10px 6px; border-bottom: 1px solid #dee2e6; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        /* 종목 리스트 컬럼 비율 */
        #tab0 th:nth-child(1) { width: 3%; }
        #tab0 th:nth-child(2) { width: 5%; }
        #tab0 th:nth-child(3) { width: 9%; }
        #tab0 th:nth-child(4) { width: 7%; }
        #tab0 th:nth-child(5) { width: 12%; }
        #tab0 th:nth-child(6) { width: 8%; }
        #tab0 th:nth-child(7) { width: 7%; }
        #tab0 th:nth-child(n+8) { width: 6%; }
        /* DD 열 (1Y 오른쪽) 세로 구분선 — 종목 리스트 16번째, 섹터 수익률 12번째 컬럼 */
        #tab0 th:nth-child(16), #tab0 td:nth-child(16) { border-left: 2px solid #868e96; }
        #sectorContent th:nth-child(12), #sectorContent td:nth-child(12) { border-left: 2px solid #868e96; }
        /* 기간 수익률 탭 컬럼 비율 */
        #tab2 th:nth-child(1) { width: 4%; }
        #tab2 th:nth-child(2) { width: 4%; }
        #tab2 th:nth-child(3) { width: 10%; }
        #tab2 th:nth-child(4) { width: 10%; }
        #tab2 th:nth-child(5) { width: 15%; }
        #tab2 th:nth-child(6) { width: 15%; }
        #tab2 th:nth-child(7) { width: 12%; cursor: default; }
        #tab2 th:nth-child(8) { width: 10%; }
        #tab2 th:nth-child(9) { width: 10%; }
        #tab2 th:nth-child(10) { width: 10%; }
        #tab2 td:nth-child(7) { padding: 0 6px; line-height: 0; }
        #tab2 td:nth-child(9) { background: #fff8e1; }
        tbody tr:hover { background: #f5f5f5; }
        .positive { color: #cc0000; font-weight: 600; }
        .negative { color: #0055cc; font-weight: 600; }
        footer { text-align: center; padding: 24px; color: #999; font-size: 14px; }
        TOP_NAV_CSS_PLACEHOLDER
    </style>
</head>
<body class="has-sidebar">
TOPNAV_PLACEHOLDER
SIDEBAR_PLACEHOLDER
<header>
    <h1>🌐 Universe</h1>
    <div class="last-updated">Updated: __UNIVERSE_UPDATED__</div>
</header>
<div class="content">
    <div class="tabs">
        <div class="tab active" onclick="switchTab(0)">종목 리스트</div>
        <div class="tab" onclick="switchTab(1)">섹터 수익률</div>
        <div class="tab" onclick="switchTab(2)">기간 수익률</div>
    </div>
    <div id="tab0" class="tab-content active">
    <div class="filters">
        <div class="csel-wrap" id="cselCurWrap">
            <div class="csel-display" id="cselCurDisplay" onclick="toggleCselId('cselCurList')">통화</div>
            <div class="csel-list" id="cselCurList"></div>
        </div>
        <div class="csel-wrap" id="cselSecWrap">
            <div class="csel-display" id="cselSecDisplay" onclick="toggleCselId('cselSecList')">섹터</div>
            <div class="csel-list" id="cselSecList"></div>
        </div>
        <button onclick="downloadUniverseList()" style="font-family:inherit;font-size:13px;font-weight:600;padding:6px 14px;background:#dc2626;color:#fff;border:none;border-radius:8px;cursor:pointer;">Download</button>
        <button onclick="superDownloadUniverse()" id="superDlBtn" style="font-family:inherit;font-size:13px;font-weight:600;padding:6px 14px;background:#2563eb;color:#fff;border:none;border-radius:8px;cursor:pointer;margin-left:8px;">Super Download</button>
    </div>
    <table>
        <thead><tr>
            <th onclick="doSort(0)">#</th>
            <th onclick="doSort(1)">통화</th>
            <th onclick="doSort(2)">섹터</th>
            <th onclick="doSort(3)">티커</th>
            <th onclick="doSort(4)">기업명</th>
            <th onclick="doSort(5)">시가총액</th>
            <th onclick="doSort(6)">가격</th>
            <th onclick="doSort(7)">RSI(1M)</th>
            <th onclick="doSort(8)">YTD</th>
            <th onclick="doSort(9)">1D</th>
            <th onclick="doSort(10)">1W</th>
            <th onclick="doSort(11)">1M</th>
            <th onclick="doSort(12)">3M</th>
            <th onclick="doSort(13)">6M</th>
            <th onclick="doSort(14)">1Y</th>
            <th onclick="doSort(15)">DD</th>
        </tr></thead>
        <tbody id="tbody"><tr><td colspan="16" style="padding:40px;color:#888;">로딩 중...</td></tr></tbody>
    </table>
    </div>
    <div id="tab1" class="tab-content">
        <div class="filters">
            <div class="csel-wrap" id="cselWrap">
                <div class="csel-display" id="cselDisplay" onclick="toggleCselId('cselList')">통화</div>
                <div class="csel-list" id="cselList"></div>
            </div>
            <button onclick="downloadUniverseSector()" style="font-family:inherit;font-size:13px;font-weight:600;padding:6px 14px;background:#dc2626;color:#fff;border:none;border-radius:8px;cursor:pointer;">Download</button>
        </div>
        <div id="sectorContent"><p style="padding:40px;color:#888;">로딩 중...</p></div>
    </div>
    <div id="tab2" class="tab-content">
        <div class="filters">
            <span style="color:#555;font-weight:600;font-size:14px;">기간</span>
            <input type="text" id="perStartDate" value="2025-12-30" onchange="formatDateInput(this);renderPeriod()" style="font-family:inherit;font-size:14px;padding:8px 10px;border:1px solid #d1d5db;border-radius:6px;background:#fff;color:#222;width:120px;text-align:center;" placeholder="YYYY-MM-DD">
            <span style="color:#888;">~</span>
            <input type="text" id="perEndDate" value="" onchange="formatDateInput(this);renderPeriod()" style="font-family:inherit;font-size:14px;padding:8px 10px;border:1px solid #d1d5db;border-radius:6px;background:#fff;color:#222;width:120px;text-align:center;" placeholder="YYYY-MM-DD">
            <div class="csel-wrap" id="cselPerCurWrap">
                <div class="csel-display" id="cselPerCurDisplay" onclick="toggleCselId('cselPerCurList')">통화</div>
                <div class="csel-list" id="cselPerCurList"></div>
            </div>
            <div class="csel-wrap" id="cselPerSecWrap">
                <div class="csel-display" id="cselPerSecDisplay" onclick="toggleCselId('cselPerSecList')">섹터</div>
                <div class="csel-list" id="cselPerSecList"></div>
            </div>
            <button onclick="downloadUniversePeriod()" style="font-family:inherit;font-size:13px;font-weight:600;padding:6px 14px;background:#dc2626;color:#fff;border:none;border-radius:8px;cursor:pointer;">Download</button>
        </div>
        <table>
            <thead><tr>
                <th onclick="doSortPer(0)">#</th>
                <th onclick="doSortPer(1)">통화</th>
                <th onclick="doSortPer(2)">섹터</th>
                <th onclick="doSortPer(3)">티커</th>
                <th onclick="doSortPer(4)">기업명</th>
                <th onclick="doSortPer(5)">시가총액</th>
                <th title="선택 기간 종가 추이 (스파크라인)">스파크 라인</th>
                <th onclick="doSortPer(7)" title="선택 기간 시작일 종가 → 종료일 종가 기준 (달력 날짜)">기간 수익률</th>
                <th onclick="doSortPer(8)" title="기간 상대강도 = 종목 기간수익률 − 해당 시장지수 기간수익률 (%p)">RSI</th>
                <th onclick="doSortPer(9)" title="기간 중 최대 낙폭 (고점→저점)">기간 MDD</th>
            </tr></thead>
            <tbody id="tbodyPer"><tr><td colspan="10" style="padding:40px;color:#888;">로딩 중...</td></tr></tbody>
        </table>
    </div>
</div>
<footer>Antigravity Universe</footer>
<script>
var D=[],sortCol=7,sortAsc=false;  // 기본 RSI(1M) 내림차순
var headers=['#','통화','섹터','티커','기업명','시가총액','가격','RSI(1M)','YTD','1D','1W','1M','3M','6M','1Y','DD'];
var numCols=[0,5,6,7,8,9,10,11,12,13,14,15];
var pctCols=[7,8,9,10,11,12,13,14,15];
// 티커 prefix → 시장 지수 매핑 (우선순위: KOSPI > KOSDAQ > NASDAQ > S&P 500 > TSEC > NIKKEI > TSX > HSI > STOXX)
// TYO = Tokyo SE (Japan → NIKKEI). TSE = Toronto SE (Canada → TSX, S&P/TSX Composite).
var INDEX_BY_PREFIX={'KRX':'KOSPI','KOSDAQ':'KOSDAQ','NASDAQ':'NASDAQ','NYSE':'S&P 500','NYSEAMERICAN':'S&P 500','TPE':'TSEC','TYO':'NIKKEI','TSE':'TSX','HKG':'HSI','AMS':'STOXX','ETR':'STOXX','EPA':'STOXX'};
var INDEX_1M={};
function rsiOf(r){
    var tk=r[3]||'';var p=tk.indexOf(':')>=0?tk.split(':')[0]:'';
    var key=INDEX_BY_PREFIX[p];if(!key)return null;
    var idx=INDEX_1M[key];if(idx===undefined||idx===null)return null;
    var s=r[10];if(!s)return null;
    var sr=parseFloat(String(s).replace(/%/g,''));if(isNaN(sr))return null;
    return sr-idx*100;
}
function fmtRsi(n){if(n===null||n===undefined)return'';var r=Math.round(n);return(r>0?'+':'')+r+'%';}

Promise.all([
    // GitHub Pages 정적 JSON (GHA cron이 매일 yfinance로 수집해서 갱신).
    // 이전: Google Sheets API + GOOGLEFINANCE — REST API에서 "로드 중..." stale 캐시 반환 문제로 폐기 (2026-05-26).
    fetch('universe.json?_=' + Date.now()).then(function(r){return r.json()}),
    fetch('index_returns.json').then(function(r){return r.ok?r.json():null}).catch(function(){return null})
]).then(function(results){
    var data=results[0], idxData=results[1];
    if(idxData&&idxData.returns_1m)INDEX_1M=idxData.returns_1m;
    D=(data.values||[]).slice(1).map(function(r){
        var row=r.slice(0,14);
        var rsi=fmtRsi(rsiOf(row));  // rsiOf는 원본 row[10]=1M 사용
        // RSI를 인덱스 7로 옮기고 기존 7~13 (YTD~1Y)을 한 칸씩 밀어 8~14로
        var saved=[row[7],row[8],row[9],row[10],row[11],row[12],row[13]];
        row[7]=rsi;
        for(var i=0;i<7;i++)row[8+i]=saved[i];
        // row[15]: DD (52주 고점 대비 낙폭) — 소스 col 22. 구버전 universe.json row는 undefined → ''
        row[15]=r[22]||'';
        // row[16]: 시가총액 정렬용 raw 숫자(억원). "43조9,769억" 등 표시값은 parseFloat 안 되니
        //          시트 col 14 raw 값("439,769") 사용
        row[16]=parseFloat(String(r[14]||'0').replace(/,/g,''))||0;
        return row;
    });
    // 초기 정렬 표시(RSI 내림차순)
    document.querySelectorAll('thead th').forEach(function(th,i){th.textContent=i===sortCol?headers[i]+' ▼':headers[i];});
    var c={},sec={};
    D.forEach(function(r){if(r[1])c[r[1]]=1;if(r[2])sec[r[2]]=1;});
    var ch='<div class="csel-item selected" data-v="">통화</div>';
    Object.keys(c).sort().forEach(function(v){ch+='<div class="csel-item" data-v="'+v+'">'+v+'</div>';});
    document.getElementById('cselCurList').innerHTML=ch;
    document.getElementById('cselCurList').addEventListener('click',function(e){var item=e.target.closest('.csel-item');if(item)pickCselCur(item.getAttribute('data-v'),item.textContent);});
    var sh='<div class="csel-item selected" data-v="">섹터</div>';
    Object.keys(sec).sort().forEach(function(v){sh+='<div class="csel-item" data-v="'+v+'">'+v+'</div>';});
    document.getElementById('cselSecList').innerHTML=sh;
    document.getElementById('cselSecList').addEventListener('click',function(e){var item=e.target.closest('.csel-item');if(item)pickCselSec(item.getAttribute('data-v'),item.textContent);});
    // 기간 수익률 탭 필터 (통화/섹터) — 종목 리스트 탭과 동일 옵션
    var pch='<div class="csel-item selected" data-v="">통화</div>';
    Object.keys(c).sort().forEach(function(v){pch+='<div class="csel-item" data-v="'+v+'">'+v+'</div>';});
    document.getElementById('cselPerCurList').innerHTML=pch;
    document.getElementById('cselPerCurList').addEventListener('click',function(e){var item=e.target.closest('.csel-item');if(item)pickCselPerCur(item.getAttribute('data-v'),item.textContent);});
    var psh='<div class="csel-item selected" data-v="">섹터</div>';
    Object.keys(sec).sort().forEach(function(v){psh+='<div class="csel-item" data-v="'+v+'">'+v+'</div>';});
    document.getElementById('cselPerSecList').innerHTML=psh;
    document.getElementById('cselPerSecList').addEventListener('click',function(e){var item=e.target.closest('.csel-item');if(item)pickCselPerSec(item.getAttribute('data-v'),item.textContent);});
    render();
});

function pn(s){if(!s)return -Infinity;var n=parseFloat(s.replace(/,/g,'').replace(/%/g,''));return isNaN(n)?-Infinity:n;}

function doSort(col){
    if(sortCol===col)sortAsc=!sortAsc;else{sortCol=col;sortAsc=true;}
    document.querySelectorAll('thead th').forEach(function(th,i){th.textContent=i===col?headers[i]+(sortAsc?' ▲':' ▼'):headers[i];});
    render();
}

function render(){
    var fc=_cselCurVal;
    var fs=_cselSecVal;
    var f=D.filter(function(r){
        if(fc&&r[1]!==fc)return false;
        if(fs&&r[2]!==fs)return false;
        return true;
    });
    if(sortCol>=0){
        var isN=numCols.indexOf(sortCol)>=0;
        f.sort(function(a,b){
            var va, vb;
            if(sortCol===5){va=a[16]||0;vb=b[16]||0;}  // 시가총액은 raw 숫자(억원) 사용
            else if(isN){va=pn(a[sortCol]);vb=pn(b[sortCol]);}
            else{va=a[sortCol]||'';vb=b[sortCol]||'';}
            if(va<vb)return sortAsc?-1:1;
            if(va>vb)return sortAsc?1:-1;
            return 0;
        });
    }
    var h='';
    f.forEach(function(r,idx){
        h+='<tr>';
        var rowMkt='';
        if(r[3]){var rp=r[3].indexOf(':')>=0?r[3].split(':')[0]:'';rowMkt=INDEX_BY_PREFIX[rp]||'';}
        for(var i=0;i<16;i++){
            var v=(i===0)?(idx+1):r[i]||'';if(i===3&&v.indexOf(':')>=0)v=v.split(':').pop();var cls='';
            if(pctCols.indexOf(i)>=0&&v){var n=parseFloat(String(v).replace(/%/g,''));if(!isNaN(n))cls=n>0?' class="positive"':n<0?' class="negative"':'';}
            var bg=(i===7)?' style="background:#fff8e1;"':(i===8?' style="background:#f3f0ff;"':'');
            var ttl=(i===7&&rowMkt)?' title="'+rowMkt+'"':'';
            h+='<td'+cls+bg+ttl+'>'+v+'</td>';
        }
        h+='</tr>';
    });
    if(!h)h='<tr><td colspan="16" style="padding:40px;color:#888;">데이터 없음</td></tr>';
    document.getElementById('tbody').innerHTML=h;
}

var _cselVal = '', _cselCurVal = '', _cselSecVal = '';
function toggleCselId(listId) {
    document.querySelectorAll('.csel-list').forEach(function(el) {
        if (el.id !== listId) el.classList.remove('open');
    });
    document.getElementById(listId).classList.toggle('open');
}
function pickCsel(val, label) {
    _cselVal = val;
    document.getElementById('cselDisplay').textContent = label;
    document.getElementById('cselList').classList.remove('open');
    document.querySelectorAll('#cselList .csel-item').forEach(function(el) {
        el.classList.toggle('selected', el.getAttribute('data-v') === val);
    });
    renderSector();
}
function pickCselCur(val, label) {
    _cselCurVal = val;
    document.getElementById('cselCurDisplay').textContent = label;
    document.getElementById('cselCurList').classList.remove('open');
    document.querySelectorAll('#cselCurList .csel-item').forEach(function(el) {
        el.classList.toggle('selected', el.getAttribute('data-v') === val);
    });
    render();
}
function pickCselSec(val, label) {
    _cselSecVal = val;
    document.getElementById('cselSecDisplay').textContent = label;
    document.getElementById('cselSecList').classList.remove('open');
    document.querySelectorAll('#cselSecList .csel-item').forEach(function(el) {
        el.classList.toggle('selected', el.getAttribute('data-v') === val);
    });
    render();
}
document.addEventListener('click', function(e) {
    document.querySelectorAll('.csel-wrap').forEach(function(w) {
        if (!w.contains(e.target)) w.querySelector('.csel-list').classList.remove('open');
    });
});

var _secSortCol = 3, _secSortAsc = false;
function sortSector(col) {
    if(_secSortCol === col) _secSortAsc = !_secSortAsc;
    else { _secSortCol = col; _secSortAsc = false; }
    renderSector();
}

function toggleSec(idx) {
    var rows = document.querySelectorAll('.sec-'+idx);
    var show = rows.length && rows[0].style.display === 'none';
    rows.forEach(function(r){ r.style.display = show ? '' : 'none'; });
}

function switchTab(idx) {
    document.querySelectorAll('.tab').forEach(function(t,i){ t.classList.toggle('active',i===idx); });
    document.querySelectorAll('.tab-content').forEach(function(t,i){ t.classList.toggle('active',i===idx); });
    if(idx===1) renderSector();
    if(idx===2) ensureHistThenRender();
}

// ── 기간 수익률 탭 ──────────────────────────────────────
// universe_history.json(종목별 일별 종가)을 탭 진입 시 1회 lazy fetch.
// 기간 수익률 = 시작일 이후 첫 거래일 종가 → 종료일 이전 마지막 거래일 종가.
// 표의 1W/1M(거래일 lookback 스냅샷)과 다른 탭이라 정합성 충돌 없음.
var HIST = null, IDXHIST = null, HIST_LOADING = false, perData = [];
var perSortCol = 7, perSortAsc = false;  // 컬럼: 추이=6, 기간수익률=7(기본 내림차순), RSI=8
var perHeaders = ['#','통화','섹터','티커','기업명','시가총액','스파크 라인','기간 수익률','RSI','기간 MDD'];
var _cselPerCurVal = '', _cselPerSecVal = '';
function formatDateInput(el){var v=el.value.replace(/[^0-9]/g,'');if(v.length===8){el.value=v.slice(0,4)+'-'+v.slice(4,6)+'-'+v.slice(6,8);}}
function ensureHistThenRender(){
    if(HIST){ renderPeriod(); return; }
    if(HIST_LOADING) return;
    HIST_LOADING = true;
    document.getElementById('tbodyPer').innerHTML='<tr><td colspan="10" style="padding:40px;color:#888;">시계열 로딩 중...</td></tr>';
    Promise.all([
        fetch('universe_history.json?_='+Date.now()).then(function(r){return r.ok?r.json():null;}).catch(function(){return null;}),
        fetch('index_history.json?_='+Date.now()).then(function(r){return r.ok?r.json():null;}).catch(function(){return null;})
    ]).then(function(res){
        HIST = res[0] || {dates:[],stocks:{}};
        IDXHIST = res[1] || {dates:[],indices:{}};
        HIST_LOADING = false;
        // 종료일 기본값 = 데이터 마지막 날짜 (사용자가 비워둔 경우만)
        var end=document.getElementById('perEndDate');
        if(HIST.dates&&HIST.dates.length&&!end.value) end.value=HIST.dates[HIST.dates.length-1];
        renderPeriod();
    });
}
function perReturn(ticker, start, end){
    if(!HIST||!HIST.stocks) return null;
    var arr=HIST.stocks[ticker]; if(!arr) return null;
    var dates=HIST.dates, base=null, last=null;
    for(var i=0;i<dates.length;i++){
        var v=arr[i]; if(v===null||v===undefined) continue;
        var d=dates[i]; if(d<start||d>end) continue;
        if(base===null) base=v; last=v;
    }
    if(base===null||last===null||base<=0) return null;
    return (last/base-1)*100;
}
// 선택 기간 중 최대 낙폭(MDD) — 고점 대비 최저 하락률(%, ≤0).
function perMDD(ticker, start, end){
    if(!HIST||!HIST.stocks) return null;
    var arr=HIST.stocks[ticker]; if(!arr) return null;
    var dates=HIST.dates, peak=null, mdd=0, any=false;
    for(var i=0;i<dates.length;i++){
        var v=arr[i]; if(v===null||v===undefined) continue;
        var d=dates[i]; if(d<start||d>end) continue;
        any=true;
        if(peak===null||v>peak) peak=v;
        if(peak>0){ var dd=(v/peak-1)*100; if(dd<mdd) mdd=dd; }
    }
    return any?mdd:null;
}
// 시장지수의 선택 기간 수익률 (RSI(기간) 계산용). perReturn과 동일 규칙.
function indexPerReturn(name, start, end){
    if(!IDXHIST||!IDXHIST.indices) return null;
    var arr=IDXHIST.indices[name]; if(!arr) return null;
    var dates=IDXHIST.dates, base=null, last=null;
    for(var i=0;i<dates.length;i++){
        var v=arr[i]; if(v===null||v===undefined) continue;
        var d=dates[i]; if(d<start||d>end) continue;
        if(base===null) base=v; last=v;
    }
    if(base===null||last===null||base<=0) return null;
    return (last/base-1)*100;
}
// 선택 기간의 종가 추이를 인라인 SVG 스파크라인으로 (검정 단색). 최대 60점 다운샘플(폭 대비 충분).
function sparkSvg(ticker, start, end, ret){
    if(!HIST||!HIST.stocks) return '';
    var arr=HIST.stocks[ticker]; if(!arr) return '';
    var dates=HIST.dates, ys=[];
    for(var i=0;i<dates.length;i++){var v=arr[i];if(v===null||v===undefined)continue;var d=dates[i];if(d<start||d>end)continue;ys.push(v);}
    if(ys.length<2) return '';
    var maxp=60, pts=ys;
    if(ys.length>maxp){pts=[];var step=(ys.length-1)/(maxp-1);for(var k=0;k<maxp;k++)pts.push(ys[Math.round(k*step)]);}
    var min=Math.min.apply(null,pts), max=Math.max.apply(null,pts), rng=(max-min)||1;
    var W=130,H=26,pad=1,n=pts.length,str='';
    for(var j=0;j<n;j++){
        var x=pad+(W-2*pad)*j/(n-1);
        var y=pad+(H-2*pad)*(1-(pts[j]-min)/rng);
        str+=(j?' ':'')+x.toFixed(1)+','+y.toFixed(1);
    }
    var col='#000';
    return '<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none" style="display:block;width:100%;height:100%;">'
        +'<polyline points="'+str+'" fill="none" stroke="'+col+'" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>';
}
function renderPeriod(){
    if(!D.length||!HIST) return;
    var start=document.getElementById('perStartDate').value;
    var end=document.getElementById('perEndDate').value||'9999-12-31';
    var fc=_cselPerCurVal, fs=_cselPerSecVal;
    var idxCache={};
    function idxRet(mkt){ if(!mkt) return null; if(mkt in idxCache) return idxCache[mkt]; var v=indexPerReturn(mkt,start,end); idxCache[mkt]=v; return v; }
    perData=[];
    D.forEach(function(r){
        if(fc&&r[1]!==fc) return;
        if(fs&&r[2]!==fs) return;
        var _p=(r[3]||'').indexOf(':')>=0?r[3].split(':')[0]:'';
        var mkt=INDEX_BY_PREFIX[_p]||'';
        var ret=perReturn(r[3],start,end);
        var ir=idxRet(mkt);
        var rsi=(ret!==null&&ir!==null)?(ret-ir):null;
        perData.push({cur:r[1]||'',sec:r[2]||'',ticker:r[3]||'',name:r[4]||'',mcap:r[5]||'',mcapRaw:r[16]||0,ret:ret,rsi:rsi,mkt:mkt,mdd:perMDD(r[3],start,end)});
    });
    perData.sort(function(a,b){
        var va,vb;
        if(perSortCol===5){va=a.mcapRaw;vb=b.mcapRaw;}
        else if(perSortCol===7){va=(a.ret===null?-Infinity:a.ret);vb=(b.ret===null?-Infinity:b.ret);}
        else if(perSortCol===8){va=(a.rsi===null?-Infinity:a.rsi);vb=(b.rsi===null?-Infinity:b.rsi);}
        else if(perSortCol===9){va=(a.mdd===null?-Infinity:a.mdd);vb=(b.mdd===null?-Infinity:b.mdd);}
        else{var keys={1:'cur',2:'sec',3:'ticker',4:'name'};va=a[keys[perSortCol]]||'';vb=b[keys[perSortCol]]||'';}
        if(va<vb) return perSortAsc?-1:1;
        if(va>vb) return perSortAsc?1:-1;
        return 0;
    });
    var h='';
    perData.forEach(function(s,idx){
        var tk=s.ticker.indexOf(':')>=0?s.ticker.split(':').pop():s.ticker;
        var retCell;
        if(s.ret===null) retCell='<td>-</td>';
        else{var n=Math.round(s.ret);var cls=n>0?' class="positive"':n<0?' class="negative"':'';retCell='<td'+cls+'>'+(n>0?'+':'')+n+'%</td>';}
        var rsiCell;
        if(s.rsi===null) rsiCell='<td>-</td>';
        else{var rn=Math.round(s.rsi);var rcls=rn>0?' class="positive"':rn<0?' class="negative"':'';var rttl=s.mkt?' title="'+s.mkt+' 대비 기간 초과수익(%p)"':'';rsiCell='<td'+rcls+rttl+'>'+(rn>0?'+':'')+rn+'%</td>';}
        var mddCell;
        if(s.mdd===null) mddCell='<td>-</td>';
        else{var m=Math.round(s.mdd);var mcls=m<0?' class="negative"':'';mddCell='<td'+mcls+'>'+m+'%</td>';}
        var sparkCell='<td>'+sparkSvg(s.ticker,start,end,s.ret)+'</td>';
        h+='<tr><td>'+(idx+1)+'</td><td>'+s.cur+'</td><td>'+s.sec+'</td><td>'+tk+'</td><td>'+s.name+'</td><td>'+s.mcap+'</td>'+sparkCell+retCell+rsiCell+mddCell+'</tr>';
    });
    if(!h) h='<tr><td colspan="10" style="padding:40px;color:#888;">데이터 없음</td></tr>';
    document.getElementById('tbodyPer').innerHTML=h;
    document.querySelectorAll('#tab2 thead th').forEach(function(th,i){th.textContent=i===perSortCol?perHeaders[i]+(perSortAsc?' ▲':' ▼'):perHeaders[i];});
}
function doSortPer(col){
    if(perSortCol===col) perSortAsc=!perSortAsc; else { perSortCol=col; perSortAsc=(col>=5?false:true); }
    renderPeriod();
}
function pickCselPerCur(val,label){
    _cselPerCurVal=val;
    document.getElementById('cselPerCurDisplay').textContent=label;
    document.getElementById('cselPerCurList').classList.remove('open');
    document.querySelectorAll('#cselPerCurList .csel-item').forEach(function(el){el.classList.toggle('selected',el.getAttribute('data-v')===val);});
    renderPeriod();
}
function pickCselPerSec(val,label){
    _cselPerSecVal=val;
    document.getElementById('cselPerSecDisplay').textContent=label;
    document.getElementById('cselPerSecList').classList.remove('open');
    document.querySelectorAll('#cselPerSecList .csel-item').forEach(function(el){el.classList.toggle('selected',el.getAttribute('data-v')===val);});
    renderPeriod();
}

var _sectorInit = false;
function renderSector() {
    if(!D.length) return;
    var fc2 = _cselVal;

    // 드롭다운 초기화 (1회)
    if(!_sectorInit) {
        var curs = {};
        D.forEach(function(r){ if(r[1]) curs[r[1]]=1; });
        var curOrder = ['KRW','USD','HKD','TWD','EUR','CAD'];
        var keys = Object.keys(curs).sort(function(a,b){
            var ia=curOrder.indexOf(a),ib=curOrder.indexOf(b);
            if(ia<0)ia=99;if(ib<0)ib=99;return ia-ib;
        });
        var lh = '<div class="csel-item selected" data-v="">통화</div>';
        keys.forEach(function(v) {
            lh += '<div class="csel-item" data-v="'+v+'">'+v+'</div>';
        });
        document.getElementById('cselList').innerHTML = lh;
        document.getElementById('cselList').addEventListener('click', function(e) {
            var item = e.target.closest('.csel-item');
            if (!item) return;
            pickCsel(item.getAttribute('data-v'), item.textContent);
        });
        _sectorInit = true;
    }

    // 필터링
    var filtered = fc2 ? D.filter(function(r){ return r[1]===fc2; }) : D;

    // 섹터별 집계 (시총 가중평균). row 인덱스: 7=RSI, 8=YTD, 9=1D, 10=1W, 11=1M, 12=3M, 13=6M, 14=1Y, 15=DD
    var agg = {};
    filtered.forEach(function(r) {
        var sec = r[2] || '기타';
        if(!agg[sec]) agg[sec] = {cnt:0, rsi:[], ytd:[], d1:[], w1:[], m1:[], m3:[], m6:[], y1:[], dd:[]};
        var g = agg[sec];
        var mcap = parseFloat(String(r[5]||'0').replace(/,/g,'').replace(/조/g,'*10000').replace(/억원/g,'').replace(/억/g,''));
        // 조/억 파싱
        var mcapStr = r[5] || '0';
        var mcapVal = 0;
        var joMatch = mcapStr.match(/(\d[\d,]*)조/);
        var eokMatch = mcapStr.match(/([\d,]+)억/);
        if(joMatch) mcapVal += parseFloat(joMatch[1].replace(/,/g,'')) * 10000;
        if(eokMatch) mcapVal += parseFloat(eokMatch[1].replace(/,/g,''));
        if(!mcapVal) mcapVal = parseFloat(mcapStr.replace(/,/g,'')) || 0;

        g.cnt++;
        var vals = [r[7],r[8],r[9],r[10],r[11],r[12],r[13],r[14],r[15]];
        var arrs = [g.rsi,g.ytd,g.d1,g.w1,g.m1,g.m3,g.m6,g.y1,g.dd];
        for(var i=0;i<9;i++) {
            if(vals[i]) {
                var n=parseFloat(String(vals[i]).replace(/%/g,'').replace(/,/g,''));
                if(!isNaN(n)) arrs[i].push({v:n, w:mcapVal});
            }
        }
    });

    function wavg(arr) {
        if(!arr.length) return null;
        var tw=0, ts=0;
        arr.forEach(function(x){ tw+=x.w; ts+=x.v*x.w; });
        return tw>0 ? ts/tw : null;
    }
    function fv(v) { if(v===null) return '-'; var s=v>0?'+':''; return s+Math.round(v)+'%'; }
    function cls(v) { if(v===null) return ''; return v>0?'positive':v<0?'negative':''; }

    var colMap = [null,null,'cnt','rsi','ytd','d1','w1','m1','m3','m6','y1','dd'];
    var secs = Object.keys(agg).sort(function(a,b) {
        var va, vb;
        if(_secSortCol <= 1) { va=a; vb=b; return _secSortAsc?va.localeCompare(vb):vb.localeCompare(va); }
        if(_secSortCol === 2) { va=agg[a].cnt; vb=agg[b].cnt; }
        else { var k=colMap[_secSortCol]; va=wavg(agg[a][k])||0; vb=wavg(agg[b][k])||0; }
        return _secSortAsc ? va-vb : vb-va;
    });

    // 종목별 데이터 (시총 파싱 + 정렬용)
    var stocksBySec = {};
    filtered.forEach(function(r) {
        var sec = r[2] || '기타';
        if(!stocksBySec[sec]) stocksBySec[sec] = [];
        var mcapStr = r[5] || '0';
        var mcapVal = 0;
        var joM = mcapStr.match(/(\d[\d,]*)조/);
        var eokM = mcapStr.match(/([\d,]+)억/);
        if(joM) mcapVal += parseFloat(joM[1].replace(/,/g,'')) * 10000;
        if(eokM) mcapVal += parseFloat(eokM[1].replace(/,/g,''));
        var _p=(r[3]||'').indexOf(':')>=0?r[3].split(':')[0]:'';
        var _mkt=INDEX_BY_PREFIX[_p]||'';
        // r 인덱스: 7=RSI, 8=YTD, 9=1D, 10=1W, 11=1M, 12=3M, 13=6M, 14=1Y, 15=DD
        stocksBySec[sec].push({name:r[4]||'',ticker:r[3]||'',cur:r[1]||'',mcap:mcapStr,mcapVal:mcapVal,mkt:_mkt,
            rsi:r[7]||'',ytd:r[8]||'',d1:r[9]||'',w1:r[10]||'',m1:r[11]||'',m3:r[12]||'',m6:r[13]||'',y1:r[14]||'',dd:r[15]||''});
    });
    for(var k in stocksBySec) stocksBySec[k].sort(function(a,b){return b.mcapVal-a.mcapVal;});

    var secHeaders = ['#','섹터','종목수','RSI(1M)','YTD','1D','1W','1M','3M','6M','1Y','DD'];
    var html = '<table style="width:100%;table-layout:fixed;border-collapse:collapse"><thead><tr>';
    secHeaders.forEach(function(h,i) {
        var bg = i===3?' style="background:#fff8e1;cursor:pointer"':(i===4?' style="background:#f3f0ff;cursor:pointer"':' style="cursor:pointer"');
        html += '<th'+bg+' onclick="sortSector('+i+')">' + h + (_secSortCol===i ? (_secSortAsc?' ▲':' ▼') : '') + '</th>';
    });
    html += '</tr></thead><tbody>';
    secs.forEach(function(sec,idx) {
        var g = agg[sec];
        var vals = [wavg(g.rsi),wavg(g.ytd),wavg(g.d1),wavg(g.w1),wavg(g.m1),wavg(g.m3),wavg(g.m6),wavg(g.y1),wavg(g.dd)];
        html += '<tr style="cursor:pointer" onclick="toggleSec('+idx+')">';
        html += '<td>' + (idx+1) + '</td><td style="font-weight:600">' + sec + '</td><td>' + g.cnt + '</td>';
        vals.forEach(function(v,i) {
            var bg = i===0?' style="background:#fff8e1"':(i===1?' style="background:#f3f0ff"':'');
            html += '<td class="'+cls(v)+'"'+bg+'>' + fv(v) + '</td>';
        });
        html += '</tr>';
        // 하위 종목 행 (숨김)
        var stocks = stocksBySec[sec] || [];
        stocks.forEach(function(s) {
            var tk = s.ticker.indexOf(':')>=0 ? s.ticker.split(':').pop() : s.ticker;
            var label = (s.cur==='KRW' || s.cur==='JPY') ? s.name : tk;
            function sc(v){if(!v)return'-';var n=parseFloat(String(v).replace(/%/g,'').replace(/,/g,''));if(isNaN(n))return v;return(n>0?'<span class="positive">+':'<span class="negative">')+Math.round(n)+'%</span>';}
            html += '<tr class="sec-detail sec-'+idx+'" style="display:none;background:#f0f0f0;font-size:14px">';
            html += '<td></td><td style="padding-left:60px;text-align:left">- '+label+'</td>';
            html += '<td>'+(s.mcap||'')+'</td>';
            var _ttl=s.mkt?' title="'+s.mkt+'"':'';
            html += '<td style="background:#fff8e1"'+_ttl+'>'+sc(s.rsi)+'</td><td style="background:#f3f0ff">'+sc(s.ytd)+'</td><td>'+sc(s.d1)+'</td><td>'+sc(s.w1)+'</td><td>'+sc(s.m1)+'</td><td>'+sc(s.m3)+'</td><td>'+sc(s.m6)+'</td><td>'+sc(s.y1)+'</td><td>'+sc(s.dd)+'</td>';
            html += '</tr>';
        });
    });
    html += '</tbody></table>';

    document.getElementById('sectorContent').innerHTML = html;
}

// ── 이미지 다운로드 (html2canvas, 상위 30개) ──────────────────
function _univCapture(node, baseName) {
    if (typeof html2canvas !== 'function') { alert('이미지 라이브러리 로딩 중입니다. 잠시 후 다시 시도해주세요.'); return Promise.resolve(); }
    return html2canvas(node, { scale: 2, backgroundColor: '#ffffff', scrollX: 0, scrollY: -window.scrollY }).then(function(canvas) {
        var d = new Date();
        var pad = function(n){ return n<10 ? '0'+n : ''+n; };
        var stamp = d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate());
        var a = document.createElement('a');
        a.href = canvas.toDataURL('image/png');
        a.download = baseName + '_' + stamp + '.png';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    });
}
function downloadUniverseList() {
    var table = document.querySelector('#tab0 table');
    if (!table) return;
    var rows = document.querySelectorAll('#tbody tr');
    var saved = [];
    for (var i = 30; i < rows.length; i++) { saved.push([rows[i], rows[i].style.display]); rows[i].style.display = 'none'; }
    _univCapture(table, 'Universe_Stocks').then(function() {
        saved.forEach(function(p){ p[0].style.display = p[1]; });
    });
}
function downloadUniverseSector() {
    var table = document.querySelector('#sectorContent table');
    if (!table) { alert('섹터 데이터가 아직 로딩되지 않았습니다.'); return; }
    var headerRows = table.querySelectorAll('tbody tr:not(.sec-detail)');
    var detailRows = table.querySelectorAll('tbody tr.sec-detail');
    var saved = [];
    headerRows.forEach(function(r, i){ if (i >= 30) { saved.push([r, r.style.display]); r.style.display = 'none'; } });
    detailRows.forEach(function(r){ saved.push([r, r.style.display]); r.style.display = 'none'; });
    _univCapture(table, 'Universe_Sectors').then(function() {
        saved.forEach(function(p){ p[0].style.display = p[1]; });
    });
}
function downloadUniversePeriod() {
    var table = document.querySelector('#tab2 table');
    if (!table) return;
    var rows = document.querySelectorAll('#tbodyPer tr');
    var saved = [];
    for (var i = 30; i < rows.length; i++) { saved.push([rows[i], rows[i].style.display]); rows[i].style.display = 'none'; }
    _univCapture(table, 'Universe_Period').then(function() {
        saved.forEach(function(p){ p[0].style.display = p[1]; });
    });
}
// ── Super Download: 종목 리스트 + 섹터 수익률을 RSI(1M)↓ / 1W↓ 두 정렬로 PNG 4장 일괄 저장 ──
function superDownloadUniverse() {
    var btn = document.getElementById('superDlBtn');
    if (btn && btn.disabled) return;  // 중복 클릭 방지
    if (typeof html2canvas !== 'function') { alert('이미지 라이브러리 로딩 중입니다. 잠시 후 다시 시도해주세요.'); return; }
    if (!D || !D.length) { alert('데이터 로딩 중입니다. 잠시 후 다시 시도해주세요.'); return; }
    if (btn) { btn.disabled = true; btn.textContent = '생성 중...'; }
    // 현재 상태 스냅샷 (정렬/탭) — 끝나면 원복
    var sCol = sortCol, sAsc = sortAsc, secCol = _secSortCol, secAsc = _secSortAsc;
    var sTab = 0;
    document.querySelectorAll('.tab-content').forEach(function(t, i){ if (t.classList.contains('active')) sTab = i; });
    function delay(ms){ return new Promise(function(r){ setTimeout(r, ms); }); }
    // #tab0 헤더 화살표만 갱신 (전역 thead th 오염 방지)
    function tab0Headers(col, asc){
        document.querySelectorAll('#tab0 thead th').forEach(function(th, i){
            th.textContent = (i === col) ? headers[i] + (asc ? ' ▲' : ' ▼') : headers[i];
        });
    }
    // 종목 리스트: col 내림차순 정렬 후 상위 30행만 캡처 (현재 통화/섹터 필터 유지)
    function capStocks(col, name){
        sortCol = col; sortAsc = false; tab0Headers(col, false); render();
        var table = document.querySelector('#tab0 table');
        var rows = document.querySelectorAll('#tbody tr'), hid = [];
        for (var i = 30; i < rows.length; i++){ hid.push([rows[i], rows[i].style.display]); rows[i].style.display = 'none'; }
        return _univCapture(table, name).then(function(){ hid.forEach(function(p){ p[0].style.display = p[1]; }); });
    }
    // 섹터 수익률: col 내림차순 정렬 후 헤더행 상위 30 + 세부행 숨기고 캡처 (#tab1 활성 상태에서 호출)
    function capSectors(col, name){
        _secSortCol = col; _secSortAsc = false; renderSector();
        var table = document.querySelector('#sectorContent table');
        if (!table) return Promise.resolve();
        var hdr = table.querySelectorAll('tbody tr:not(.sec-detail)');
        var det = table.querySelectorAll('tbody tr.sec-detail');
        var hid = [];
        hdr.forEach(function(r, i){ if (i >= 30){ hid.push([r, r.style.display]); r.style.display = 'none'; } });
        det.forEach(function(r){ hid.push([r, r.style.display]); r.style.display = 'none'; });
        return _univCapture(table, name).then(function(){ hid.forEach(function(p){ p[0].style.display = p[1]; }); });
    }
    function restore(){
        sortCol = sCol; sortAsc = sAsc; _secSortCol = secCol; _secSortAsc = secAsc;
        tab0Headers(sCol, sAsc); render();
        switchTab(sTab);
        if (btn){ btn.disabled = false; btn.textContent = 'Super Download'; }
    }
    Promise.resolve()
        .then(function(){ return capStocks(7, 'Universe_Stocks_RSI1M'); })   // 종목 RSI(1M)↓
        .then(function(){ return delay(500); })
        .then(function(){ return capStocks(10, 'Universe_Stocks_1W'); })     // 종목 1W↓
        .then(function(){ return delay(500); })
        .then(function(){ switchTab(1); return delay(80); })                 // 섹터 탭 가시화 (html2canvas는 display:none 캡처 불가)
        .then(function(){ return capSectors(3, 'Universe_Sectors_RSI1M'); }) // 섹터 RSI(1M)↓ (col 3)
        .then(function(){ return delay(500); })
        .then(function(){ return capSectors(6, 'Universe_Sectors_1W'); })    // 섹터 1W↓ (col 6)
        .then(function(){ return delay(300); })
        .then(restore)
        .catch(function(e){ console.error('superDownloadUniverse:', e); restore(); });
}
</script>
</body>
</html>"""

    universe_page = (universe_page
                     .replace('TOP_NAV_CSS_PLACEHOLDER', TOP_NAV_CSS)
                     .replace('TOPNAV_PLACEHOLDER', top_nav_html('universe'))
                     .replace('SIDEBAR_PLACEHOLDER', sidebar_html('universe'))
                     .replace('__UNIVERSE_UPDATED__', now))
    with open('universe.html', 'w', encoding='utf-8') as f:
        f.write(universe_page)
    print("Universe page generated: universe.html")

    # SEIBro page - TOP 50 종목별 데이터
    try:
        _df = pd.read_csv('dataset.csv', encoding='utf-8-sig')
        seibro_data = _df[_df['데이터 타입'] == 'SEIBro'].copy()
    except:
        seibro_data = pd.DataFrame()

    seibro_records = []
    if not seibro_data.empty:
        seibro_data['날짜'] = pd.to_datetime(seibro_data['날짜'])
        for _, row in seibro_data.iterrows():
            seibro_records.append({
                'd': row['날짜'].strftime('%Y-%m-%d'),
                'n': row['제품명'],
                'v': int(row['가격']),
            })

    seibro_json = json.dumps(seibro_records, ensure_ascii=False)
    seibro_dates_sorted = sorted(set(r['d'] for r in seibro_records))
    last_date = seibro_dates_sorted[-1] if seibro_dates_sorted else ''
    first_date = seibro_dates_sorted[0] if seibro_dates_sorted else ''

    # Ticker 매핑 로드
    ticker_map = {}
    try:
        with open('seibro_tickers.json', 'r', encoding='utf-8') as f:
            ticker_map = json.load(f)
    except:
        pass
    ticker_json = json.dumps(ticker_map, ensure_ascii=False)

    seibro_page = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SEIBro - US Settlement TOP 50</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>Chart.defaults.font.family = "'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif"; Chart.defaults.devicePixelRatio = 2 * (window.devicePixelRatio || 1); Chart.defaults.elements.line.borderJoinStyle = 'round'; Chart.defaults.elements.line.borderCapStyle = 'round';</script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif; font-size: 1.05rem; background: #f8f9fa; color: #333; }}
        header {{ padding: 20px 24px; margin: 0 0 40px; text-align: center; position: relative; }}
        header h1 {{ margin: 0; font-size: 33px; color: #333; font-weight: 700; line-height: 1.2; }}
        .last-updated {{ margin-top: 10px; color: #6c757d; font-size: 15px; font-style: italic; }}
        .nav-group {{ margin-top: 10px; }}
        .nav-button {{ display: inline-block; padding: 6px 16px; border-radius: 6px; text-decoration: none; color: #fff; font-size: 0.85rem; font-weight: 600; background: #333; }}
        .subtitle {{ color: #6c757d; font-size: 15px; font-style: italic; margin-top: 10px; }}
        .content {{ padding: 24px; max-width: 1800px; margin: 0 auto; }}
        .section {{ background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
        .section h2 {{ font-size: 1.1rem; color: #333; margin-bottom: 16px; }}
        .date-bar {{ display: flex; align-items: center; gap: 8px; margin-bottom: 16px; font-size: 13px; flex-wrap: wrap; }}
        .date-bar input {{ font-family: inherit; font-size: 13px; padding: 4px 8px; border: 1px solid #d1d5db; border-radius: 6px; background: #f9fafb; color: #222; width: 110px; text-align: center; }}
        .date-bar span {{ color: #888; }}
        .date-bar label {{ color: #555; font-weight: 600; }}
        .stats-row {{ display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }}
        .stat-card {{ background: #fff; border-radius: 10px; padding: 16px 20px; flex: 1; min-width: 160px; border-left: 4px solid #2d7a3a; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
        .stat-card .label {{ font-size: 0.8rem; color: #888; margin-bottom: 4px; }}
        .stat-card .value {{ font-size: 1.3rem; font-weight: 700; color: #333; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 16px; }}
        thead {{ background: #e9ecef; }}
        th {{ padding: 10px 12px; text-align: center; font-weight: 600; color: #000; border-bottom: 2px solid #000; }}
        td {{ padding: 9px 12px; border-bottom: 1px solid #dee2e6; }}
        td.name {{ text-align: left; max-width: 400px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
        td.rank {{ text-align: center; font-weight: 600; }}
        tbody tr:hover {{ background: #f5f5f5; }}
        .positive {{ color: #cc0000; font-weight: 600; }}
        .negative {{ color: #0055cc; font-weight: 600; }}
        footer {{ text-align: center; padding: 24px; color: #999; font-size: 14px; }}
        {TOP_NAV_CSS}
    </style>
</head>
<body class="has-sidebar">
{top_nav_html('seibro')}
{sidebar_html('seibro')}
<header>
    <h1>SEIBro US Settlement TOP 50</h1>
    <div class="subtitle">Overseas Securities Buy Settlement - US Market</div>
</header>
<div class="content">
    <div class="section">
        <div class="date-bar">
            <label>기간</label>
            <input type="text" id="sStartDate" value="{last_date}" placeholder="YYYY-MM-DD" oninput="tryRefresh()" onchange="refresh()">
            <span>~</span>
            <input type="text" id="sEndDate" value="{last_date}" placeholder="YYYY-MM-DD" oninput="tryRefresh()" onchange="refresh()">
            <span id="dateInfo" style="color:#555;font-size:12px;"></span>
        </div>
        <div class="stats-row" id="statsRow"></div>
        <div style="position:relative;height:400px;">
            <div style="position:absolute;top:0;right:0;font-size:12px;color:#888;">Data as of {last_date}</div>
            <canvas id="topChart"></canvas>
        </div>
    </div>
    <div class="section">
        <h2 id="tableTitle">TOP 50</h2>
        <div style="overflow-x:auto;">
            <table>
                <thead><tr><th style="width:40px">#</th><th>Ticker</th><th style="text-align:left">Stock</th><th style="text-align:right">Buy Amount (USD)</th><th style="text-align:right">Share</th></tr></thead>
                <tbody id="topTable"></tbody>
            </table>
        </div>
    </div>
</div>
<footer>Data source: SEIBro (seibro.or.kr)</footer>
<script>
var raw = {seibro_json};
var tickerMap = {ticker_json};
var topChart = null;

function fmtDate(el) {{
    var v = el.value;
    if (/^\d{{8}}$/.test(v)) {{ el.value = v.slice(0,4)+'-'+v.slice(4,6)+'-'+v.slice(6,8); return true; }}
    return /^\d{{4}}-\d{{2}}-\d{{2}}$/.test(v);
}}
function tryRefresh() {{
    var a = document.getElementById('sStartDate');
    var b = document.getElementById('sEndDate');
    if (fmtDate(a) && fmtDate(b)) refresh();
}}

function refresh() {{
    var s = document.getElementById('sStartDate').value;
    var e = document.getElementById('sEndDate').value;
    var filtered = raw.filter(function(r) {{ return r.d >= s && r.d <= e; }});

    // Aggregate by stock name
    var agg = {{}};
    filtered.forEach(function(r) {{
        if (!agg[r.n]) agg[r.n] = 0;
        agg[r.n] += r.v;
    }});

    // Sort and take top 50
    var sorted = Object.keys(agg).map(function(k) {{ return {{name: k, val: agg[k]}}; }});
    sorted.sort(function(a, b) {{ return b.val - a.val; }});
    var top50 = sorted.slice(0, 50);

    var total = top50.reduce(function(a, b) {{ return a + b.val; }}, 0);
    var totalAll = sorted.reduce(function(a, b) {{ return a + b.val; }}, 0);

    // Count unique dates
    var dates = {{}};
    filtered.forEach(function(r) {{ dates[r.d] = 1; }});
    var nDays = Object.keys(dates).length;
    var isSingle = (s === e);

    document.getElementById('dateInfo').textContent = isSingle ? '' : nDays + '거래일 합산';

    // Stats
    var statsHtml = '<div class="stat-card"><div class="label">TOP 50 합산</div><div class="value">' + fmtM(total) + '</div></div>';
    if (top50.length > 0) {{
        statsHtml += '<div class="stat-card" style="border-left-color:#cc0000"><div class="label">1위</div><div class="value" style="font-size:1rem;">' + getTicker(top50[0].name) + '</div></div>';
        statsHtml += '<div class="stat-card"><div class="label">1위 금액</div><div class="value">' + fmtM(top50[0].val) + '</div></div>';
    }}
    document.getElementById('statsRow').innerHTML = statsHtml;
    document.getElementById('tableTitle').textContent = isSingle ? s + ' TOP 50' : s + ' ~ ' + e + ' 합산 TOP 50';

    // Chart (horizontal bar, top 20)
    var chartData = top50.slice(0, 20);
    if (topChart) topChart.destroy();
    topChart = new Chart(document.getElementById('topChart'), {{
        type: 'bar',
        data: {{
            labels: chartData.map(function(d) {{ return getTicker(d.name); }}),
            datasets: [{{
                data: chartData.map(function(d) {{ return Math.round(d.val / 1000000); }}),
                backgroundColor: 'rgba(3,105,161,0.5)',
                borderColor: '#2d7a3a',
                borderWidth: 1
            }}]
        }},
        options: {{
            indexAxis: 'y',
            responsive: true, maintainAspectRatio: false,
            layout: {{ padding: {{ top: 20 }} }},
            plugins: {{
                legend: {{ display: false }},
                tooltip: {{ callbacks: {{ label: function(ctx) {{ return getTicker(chartData[ctx.dataIndex].name) + ': ' + ctx.raw.toLocaleString() + 'M$'; }} }} }}
            }},
            scales: {{
                x: {{ ticks: {{ callback: function(v) {{ return v.toLocaleString() + 'M$'; }}, font: {{ size: 11 }}, color: '#000' }}, grid: {{ color: '#eee' }} }},
                y: {{ ticks: {{ font: {{ size: 11 }}, color: '#000' }}, grid: {{ display: false }} }}
            }}
        }}
    }});

    // Table
    var html = '';
    top50.forEach(function(d, i) {{
        var pct = total > 0 ? (d.val / total * 100).toFixed(1) + '%' : '';
        var ticker = getTicker(d.name);
        html += '<tr><td class="rank">' + (i + 1) + '</td><td style="text-align:center;font-weight:600;">' + ticker + '</td><td class="name">' + d.name + '</td><td class="num">' + d.val.toLocaleString() + '</td><td class="num">' + pct + '</td></tr>';
    }});
    document.getElementById('topTable').innerHTML = html || '<tr><td colspan="5" style="padding:40px;color:#888;text-align:center;">데이터 없음</td></tr>';
}}

function fmtM(v) {{ return (v / 1000000).toFixed(0).replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, ',') + 'M$'; }}
function getTicker(n) {{ return tickerMap[n] || n.substring(0, 10); }}

refresh();
</script>
</body>
</html>"""

    with open('seibro.html', 'w', encoding='utf-8') as f:
        f.write(seibro_page)
    print("SEIBro page generated: seibro.html")

    # ── Featured page ──
    featured_records = []
    try:
        with open('featured_data.json', 'r', encoding='utf-8') as f:
            featured_records = json.load(f)
    except:
        pass

    featured_json = json.dumps(featured_records, ensure_ascii=False)
    featured_dates = sorted(set(r['d'] for r in featured_records))
    featured_last = featured_dates[-1] if featured_dates else ''

    # WICS 섹터 매핑 로드
    wics_map = {}
    wics_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'wics_mapping.json')
    if os.path.exists(wics_path):
        try:
            with open(wics_path, 'r', encoding='utf-8') as f:
                wics_map = json.load(f).get('mapping', {})
        except:
            pass
    wics_json = json.dumps(wics_map, ensure_ascii=False)

    # 뉴스 데이터 로드
    news_records = {}
    news_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'featured_news.json')
    if os.path.exists(news_path):
        try:
            with open(news_path, 'r', encoding='utf-8') as f:
                news_records = json.load(f)
        except:
            pass
    news_json = json.dumps(news_records, ensure_ascii=False)

    featured_page = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Featured</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif; font-size: 1.05rem; background: #f8f9fa; color: #333; }}
        header {{ padding: 20px 24px; margin: 0 0 40px; text-align: center; position: relative; }}
        header h1 {{ margin: 0; font-size: 33px; color: #333; font-weight: 700; line-height: 1.2; }}
        .last-updated {{ margin-top: 10px; color: #6c757d; font-size: 15px; font-style: italic; }}
        .subtitle {{ color: #6c757d; font-size: 15px; font-style: italic; margin-top: 10px; }}
        .content {{ padding: 24px; max-width: 1800px; margin: 0 auto; }}
        .section {{ background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
        .section h2 {{ font-size: 1.1rem; color: #333; margin-bottom: 16px; }}
        .date-bar {{ display: flex; align-items: center; gap: 8px; margin-bottom: 20px; font-size: 13px; flex-wrap: wrap; }}
        .date-bar input {{ font-family: inherit; font-size: 13px; padding: 4px 8px; border: 1px solid #d1d5db; border-radius: 6px; background: #f9fafb; color: #222; width: 110px; text-align: center; }}
        .date-bar label {{ color: #555; font-weight: 600; }}
        .tables {{ display: flex; gap: 24px; flex-wrap: wrap; }}
        .tables > div {{ flex: 1; min-width: 500px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 16px; }}
        thead {{ background: #2E7D32; }}
        th {{ padding: 8px 6px; text-align: center; font-weight: 600; color: #fff; font-size: 0.78rem; border: 1px solid #1B5E20; }}
        td {{ padding: 6px 6px; border: 1px solid #ddd; }}
        td.c {{ text-align: center; font-variant-numeric: tabular-nums; }}
        tbody tr:nth-child(even) {{ background: #E8F5E9; }}
        tbody tr:nth-child(odd) {{ background: #fff; }}
        tbody tr:hover {{ background: #C8E6C9; }}
        .section h2 {{ background: #2d7a3a; color: #fff; padding: 8px 12px; border-radius: 4px; font-size: 0.95rem; text-align: center; }}
        .pos {{ color: #cc0000; font-weight: 600; }}
        .neg {{ color: #0055cc; font-weight: 600; }}
        .tabs {{ display: flex; gap: 0; margin-bottom: 20px; border-bottom: 2px solid #2d7a3a; }}
        .tab {{ padding: 10px 24px; cursor: pointer; font-weight: 600; font-size: 16px; color: #666; border: 1px solid transparent; border-bottom: none; border-radius: 8px 8px 0 0; background: #f0f0f0; }}
        .tab.active {{ color: #2d7a3a; background: #fff; border-color: #2d7a3a #2d7a3a transparent; margin-bottom: -2px; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        .notable-news {{ font-size: 13px; color: #333; line-height: 1.8; }}
        .notable-news b {{ font-weight: 700; }}
        footer {{ text-align: center; padding: 24px; color: #999; font-size: 14px; }}
        {TOP_NAV_CSS}
    </style>
</head>
<body class="has-sidebar">
{top_nav_html('featured')}
{sidebar_html('featured')}
<header>
    <h1>🔥 Featured</h1>
    <div class="last-updated">Updated: __FEATURED_UPDATED__</div>
</header>
<div class="content">
    <div class="date-bar">
        <label>기간</label>
        <input type="text" id="fStartDate" value="{featured_last}" placeholder="YYYY-MM-DD" oninput="tryRefresh()" onchange="refresh()">
        <span>~</span>
        <input type="text" id="fEndDate" value="{featured_last}" placeholder="YYYY-MM-DD" oninput="tryRefresh()" onchange="refresh()">
        <span id="dateLabel" style="color:#888;font-size:12px;"></span>
    </div>
    <div class="tabs">
        <div class="tab active" onclick="switchTab(0)">종목</div>
        <div class="tab" onclick="switchTab(1)">특이사항</div>
    </div>
    <div id="tab0" class="tab-content active">
    <div class="section">
        <div class="tables">
            <div>
                <h2>거래대금 TOP 30</h2>
                <table>
                    <thead><tr><th>#</th><th>업종</th><th>종목</th><th>시장</th><th>거래대금</th><th>시총</th><th>등락률</th></tr></thead>
                    <tbody id="absTable"></tbody>
                </table>
            </div>
            <div>
                <h2>거래대금/시총 비율 TOP 30</h2>
                <table>
                    <thead><tr><th>#</th><th>업종</th><th>종목</th><th>시장</th><th>거래대금</th><th>회전율</th><th>시총</th><th>등락률</th></tr></thead>
                    <tbody id="turnTable"></tbody>
                </table>
            </div>
        </div>
    </div>
    <div class="section">
        <div class="tables">
            <div>
                <h2>코스피 시가총액 TOP 30</h2>
                <table>
                    <thead><tr><th>#</th><th>업종</th><th>종목</th><th>시총</th><th>거래대금</th><th>등락률</th></tr></thead>
                    <tbody id="kospiCapTable"></tbody>
                </table>
            </div>
            <div>
                <h2>코스닥 시가총액 TOP 30</h2>
                <table>
                    <thead><tr><th>#</th><th>업종</th><th>종목</th><th>시총</th><th>거래대금</th><th>등락률</th></tr></thead>
                    <tbody id="kosdaqCapTable"></tbody>
                </table>
            </div>
        </div>
    </div>
    <div class="section">
        <div class="tables">
            <div>
                <h2>코스피 상승률 TOP 30</h2>
                <table>
                    <thead><tr><th>#</th><th>업종</th><th>종목</th><th>시총</th><th>거래대금</th><th>등락률</th></tr></thead>
                    <tbody id="kospiChgTable"></tbody>
                </table>
            </div>
            <div>
                <h2>코스닥 상승률 TOP 30</h2>
                <table>
                    <thead><tr><th>#</th><th>업종</th><th>종목</th><th>시총</th><th>거래대금</th><th>등락률</th></tr></thead>
                    <tbody id="kosdaqChgTable"></tbody>
                </table>
            </div>
        </div>
    </div>
    <div class="section">
        <h2>신고가 종목</h2>
        <div style="overflow-x:auto;">
            <table>
                <thead><tr><th style="width:30px">#</th><th style="border-left:2px solid #2E7D32">업종</th><th>20일</th><th>시총</th><th style="border-left:2px solid #2E7D32">업종</th><th>120일</th><th>시총</th><th style="border-left:2px solid #2E7D32">업종</th><th>52주</th><th>시총</th></tr></thead>
                <tbody id="newHighTable"></tbody>
            </table>
        </div>
    </div>
    </div>
    <div id="tab1" class="tab-content">
        <div class="section">
            <h2>20일 신고가 업종 분석 (<span id="notable20Count" style="font-size:inherit">0</span>개)</h2>
            <table>
                <thead><tr><th style="width:10%">업종</th><th style="width:5%">종목수</th><th style="width:25%">주요 종목</th><th>요약</th></tr></thead>
                <tbody id="notable20"></tbody>
            </table>
        </div>
        <div class="section">
            <h2>120일 신고가 업종 분석 (<span id="notable120Count" style="font-size:inherit">0</span>개)</h2>
            <table>
                <thead><tr><th style="width:10%">업종</th><th style="width:5%">종목수</th><th style="width:25%">주요 종목</th><th>요약</th></tr></thead>
                <tbody id="notable120"></tbody>
            </table>
        </div>
        <div class="section">
            <h2>52주 신고가 업종 분석 (<span id="notable52Count" style="font-size:inherit">0</span>개)</h2>
            <table>
                <thead><tr><th style="width:10%">업종</th><th style="width:5%">종목수</th><th style="width:25%">주요 종목</th><th>요약</th></tr></thead>
                <tbody id="notable52"></tbody>
            </table>
        </div>
    </div>
</div>
<footer>Data source: KRX OpenAPI</footer>
<script>
var raw = {featured_json};
var wics = {wics_json};
var newsData = {news_json};

function sec(code) {{
    return wics[code] || '';
}}

function switchTab(idx) {{
    document.querySelectorAll('.tab').forEach(function(t, i) {{
        t.classList.toggle('active', i === idx);
    }});
    document.querySelectorAll('.tab-content').forEach(function(c, i) {{
        c.classList.toggle('active', i === idx);
    }});
    if (idx === 1) renderNotable();
}}

function renderNotable() {{
    var e = document.getElementById('fEndDate').value;
    var nhData = raw.filter(function(r) {{ return r.d === e; }});
    var types = ['newhigh_20d', 'newhigh_120d', 'newhigh_52w'];
    var tableIds = ['notable20', 'notable120', 'notable52'];
    var countIds = ['notable20Count', 'notable120Count', 'notable52Count'];

    types.forEach(function(type, idx) {{
        var stocks = nhData.filter(function(r) {{ return r.type === type; }});
        stocks.sort(function(a,b) {{ return b.mktcap - a.mktcap; }});

        var sectors = {{}};
        stocks.forEach(function(r) {{
            var s = wics[r.code] || '기타';
            if (!sectors[s]) sectors[s] = [];
            sectors[s].push(r);
        }});

        var sectorList = Object.keys(sectors).sort(function(a,b) {{
            return sectors[b].length - sectors[a].length;
        }});

        document.getElementById(countIds[idx]).textContent = stocks.length;

        var html = '';
        sectorList.forEach(function(s) {{
            var items = sectors[s];
            var names = items.slice(0, 10).map(function(r) {{
                return r.name;
            }}).join(', ');
            if (items.length > 10) names += ' 외 ' + (items.length - 10) + '개';

            var newsHtml = '';
            var nd = newsData.date || '';
            if (nd === e && newsData.summaries && newsData.summaries[s]) {{
                newsHtml = newsData.summaries[s].replace(/\\n\\n/g, '\\n').replace(/\\n/g, '<br>');
            }}
            if (!newsHtml) newsHtml = '<span style="color:#bbb">-</span>';

            html += '<tr>';
            html += '<td class="c" style="font-weight:600">' + s + '</td>';
            html += '<td class="c" style="font-weight:700;font-size:1.1em">' + items.length + '</td>';
            html += '<td style="text-align:left;padding-left:10px">' + names + '</td>';
            html += '<td class="notable-news" style="text-align:left;padding-left:10px">' + newsHtml + '</td>';
            html += '</tr>';
        }});

        document.getElementById(tableIds[idx]).innerHTML = html || '<tr><td colspan="4" style="text-align:center;padding:40px;color:#888;">데이터 없음</td></tr>';
    }});
}}

function fmtDate(el) {{
    var v = el.value;
    if (/^\d{{8}}$/.test(v)) {{ el.value = v.slice(0,4)+'-'+v.slice(4,6)+'-'+v.slice(6,8); return true; }}
    return /^\d{{4}}-\d{{2}}-\d{{2}}$/.test(v);
}}
function tryRefresh() {{
    var a = document.getElementById('fStartDate');
    var b = document.getElementById('fEndDate');
    if (fmtDate(a) && fmtDate(b)) refresh();
}}

function fmtVal(v) {{
    if (v >= 1e12) {{
        var jo = Math.floor(v / 1e12);
        var eok = Math.round((v % 1e12) / 1e8);
        return jo.toLocaleString() + '조 ' + eok.toLocaleString() + '억';
    }}
    if (v >= 1e8) return Math.round(v / 1e8).toLocaleString() + '억';
    return Math.round(v).toLocaleString();
}}

function refresh() {{
    var s = document.getElementById('fStartDate').value;
    var e = document.getElementById('fEndDate').value;
    var isSingle = (s === e);
    var filtered = raw.filter(function(r) {{ return r.d >= s && r.d <= e; }});

    // 기간 내 거래대금 합산으로 순위 재계산
    var absAgg = {{}};
    var turnAgg = {{}};
    filtered.forEach(function(r) {{
        var key = r.name;
        if (r.type === 'absolute') {{
            if (!absAgg[key]) absAgg[key] = {{name: r.name, code: r.code, market: r.market, trdval: 0, mktcap: r.mktcap, chgSum: 0, cnt: 0}};
            absAgg[key].trdval += r.trdval;
            absAgg[key].mktcap = r.mktcap;
            absAgg[key].chgSum += r.chg;
            absAgg[key].cnt++;
        }}
        if (r.type === 'turnover') {{
            if (!turnAgg[key]) turnAgg[key] = {{name: r.name, code: r.code, market: r.market, trdval: 0, mktcap: r.mktcap, turnover: 0, chgSum: 0, cnt: 0}};
            turnAgg[key].trdval += r.trdval;
            turnAgg[key].mktcap = r.mktcap;
            turnAgg[key].turnover += r.turnover;
            turnAgg[key].chgSum += r.chg;
            turnAgg[key].cnt++;
        }}
    }});

    var absList = Object.values(absAgg).sort(function(a,b) {{ return b.trdval - a.trdval; }}).slice(0, 30);
    var turnList = Object.values(turnAgg).sort(function(a,b) {{ return b.turnover - a.turnover; }}).slice(0, 30);

    // 날짜 수
    var dateSet = {{}};
    filtered.forEach(function(r) {{ dateSet[r.d] = 1; }});
    var nDays = Object.keys(dateSet).length;
    document.getElementById('dateLabel').textContent = isSingle ? '' : nDays + '거래일 합산';

    // 종목별 기간 누적 수익률 계산 (시작일 종가 → 종료일 종가)
    var allDates = [];
    filtered.forEach(function(r) {{ if (allDates.indexOf(r.d) < 0) allDates.push(r.d); }});
    allDates.sort();

    var priceMap = {{}};
    filtered.forEach(function(r) {{
        if (!priceMap[r.name]) priceMap[r.name] = {{firstDate: r.d, lastDate: r.d, firstPrice: r.price, lastPrice: r.price, market: r.market, mktcap: r.mktcap}};
        if (r.d <= priceMap[r.name].firstDate && r.price > 0) {{ priceMap[r.name].firstDate = r.d; priceMap[r.name].firstPrice = r.price; }}
        if (r.d >= priceMap[r.name].lastDate && r.price > 0) {{ priceMap[r.name].lastDate = r.d; priceMap[r.name].lastPrice = r.price; priceMap[r.name].mktcap = r.mktcap; }}
    }});

    function getCumChg(name) {{
        if (!name || !priceMap[name]) return 0;
        var p = priceMap[name];
        if (!p.firstPrice || p.firstPrice === 0) return 0;
        return (p.lastPrice / p.firstPrice - 1) * 100;
    }}

    var h1 = '';
    absList.forEach(function(r, i) {{
        var cumChg = isSingle ? (r.cnt > 0 ? r.chgSum / r.cnt : 0) : getCumChg(r.name);
        var cls = cumChg > 0 ? 'pos' : (cumChg < 0 ? 'neg' : '');
        var chgLabel = (cumChg > 0 ? '+' : '') + Math.round(cumChg) + '%';
        h1 += '<tr><td class="c">' + (i+1) + '</td><td class="c">' + sec(r.code) + '</td><td class="c">' + r.name + '</td><td class="c">' + r.market + '</td><td class="c">' + fmtVal(r.trdval) + '</td><td class="c">' + fmtVal(r.mktcap) + '</td><td class="c ' + cls + '">' + chgLabel + '</td></tr>';
    }});
    document.getElementById('absTable').innerHTML = h1 || '<tr><td colspan="7" style="text-align:center;padding:40px;color:#888;">데이터 없음</td></tr>';

    var h2 = '';
    turnList.forEach(function(r, i) {{
        var cumChg = isSingle ? (r.cnt > 0 ? r.chgSum / r.cnt : 0) : getCumChg(r.name);
        var cls = cumChg > 0 ? 'pos' : (cumChg < 0 ? 'neg' : '');
        var chgLabel = (cumChg > 0 ? '+' : '') + Math.round(cumChg) + '%';
        var avgTurnover = r.cnt > 0 ? (r.turnover / r.cnt) : 0;
        h2 += '<tr><td class="c">' + (i+1) + '</td><td class="c">' + sec(r.code) + '</td><td class="c">' + r.name + '</td><td class="c">' + r.market + '</td><td class="c">' + fmtVal(r.trdval) + '</td><td class="c">' + Math.round(avgTurnover) + '%</td><td class="c">' + fmtVal(r.mktcap) + '</td><td class="c ' + cls + '">' + chgLabel + '</td></tr>';
    }});
    document.getElementById('turnTable').innerHTML = h2 || '<tr><td colspan="8" style="text-align:center;padding:40px;color:#888;">데이터 없음</td></tr>';

    // 시총/상승률 테이블: 기간 연동
    function aggByType(type) {{
        var agg = {{}};
        filtered.forEach(function(r) {{
            if (r.type !== type) return;
            if (!agg[r.name]) agg[r.name] = {{name: r.name, code: r.code, market: r.market, mktcap: r.mktcap, trdval: 0, price: r.price}};
            agg[r.name].trdval += r.trdval;
            agg[r.name].mktcap = r.mktcap;
            agg[r.name].price = r.price;
        }});
        return Object.values(agg);
    }}

    function renderCapTable(type, tableId) {{
        var items = aggByType(type).sort(function(a,b) {{ return b.mktcap - a.mktcap; }}).slice(0, 30);
        var h = '';
        items.forEach(function(r, i) {{
            var cumChg = getCumChg(r.name);
            if (isSingle) {{
                var dayItem = filtered.filter(function(x) {{ return x.name === r.name && x.type === type && x.d === e; }})[0];
                if (dayItem) cumChg = dayItem.chg;
            }}
            var cls = cumChg > 0 ? 'pos' : (cumChg < 0 ? 'neg' : '');
            h += '<tr><td class="c">' + (i+1) + '</td><td class="c">' + sec(r.code) + '</td><td class="c">' + r.name + '</td><td class="c">' + fmtVal(r.mktcap) + '</td><td class="c">' + fmtVal(r.trdval) + '</td><td class="c ' + cls + '">' + (cumChg > 0 ? '+' : '') + Math.round(cumChg) + '%</td></tr>';
        }});
        document.getElementById(tableId).innerHTML = h || '<tr><td colspan="6" style="text-align:center;padding:40px;color:#888;">데이터 없음</td></tr>';
    }}

    function renderChgTable(type, tableId) {{
        var items = aggByType(type);
        // 누적 등락률 기준 정렬
        items.forEach(function(r) {{ r.cumChg = isSingle ? 0 : getCumChg(r.name); }});
        if (isSingle) {{
            items.forEach(function(r) {{
                var dayItem = filtered.filter(function(x) {{ return x.name === r.name && x.type === type && x.d === e; }})[0];
                if (dayItem) r.cumChg = dayItem.chg;
            }});
        }}
        items.sort(function(a,b) {{ return b.cumChg - a.cumChg; }});
        items = items.slice(0, 30);
        var h = '';
        items.forEach(function(r, i) {{
            var cls = r.cumChg > 0 ? 'pos' : (r.cumChg < 0 ? 'neg' : '');
            h += '<tr><td class="c">' + (i+1) + '</td><td class="c">' + sec(r.code) + '</td><td class="c">' + r.name + '</td><td class="c">' + fmtVal(r.mktcap) + '</td><td class="c">' + fmtVal(r.trdval) + '</td><td class="c ' + cls + '">' + (r.cumChg > 0 ? '+' : '') + Math.round(r.cumChg) + '%</td></tr>';
        }});
        document.getElementById(tableId).innerHTML = h || '<tr><td colspan="6" style="text-align:center;padding:40px;color:#888;">데이터 없음</td></tr>';
    }}

    renderCapTable('kospi_cap', 'kospiCapTable');
    renderCapTable('kosdaq_cap', 'kosdaqCapTable');
    renderChgTable('kospi_chg', 'kospiChgTable');
    renderChgTable('kosdaq_chg', 'kosdaqChgTable');

    // 신고가 통합 테이블 (종료일 기준, 기간 변경 무관)
    var nhData = raw.filter(function(r) {{ return r.d === e; }});
    var nh20 = nhData.filter(function(r) {{ return r.type === 'newhigh_20d'; }}).sort(function(a,b) {{ return b.mktcap - a.mktcap; }}).slice(0, 50);
    var nh120 = nhData.filter(function(r) {{ return r.type === 'newhigh_120d'; }}).sort(function(a,b) {{ return b.mktcap - a.mktcap; }}).slice(0, 50);
    var nh52w = nhData.filter(function(r) {{ return r.type === 'newhigh_52w'; }}).sort(function(a,b) {{ return b.mktcap - a.mktcap; }}).slice(0, 50);
    var maxRows = Math.max(nh20.length, nh120.length, nh52w.length);
    var nhHtml = '';
    for (var i = 0; i < maxRows; i++) {{
        var r20 = nh20[i]; var r120 = nh120[i]; var r52 = nh52w[i];
        nhHtml += '<tr><td class="c">' + (i+1) + '</td>';
        nhHtml += '<td class="c" style="border-left:2px solid #2E7D32">' + (r20 ? sec(r20.code) : '') + '</td><td class="c">' + (r20 ? r20.name : '') + '</td><td class="c">' + (r20 ? fmtVal(r20.mktcap) : '') + '</td>';
        nhHtml += '<td class="c" style="border-left:2px solid #2E7D32">' + (r120 ? sec(r120.code) : '') + '</td><td class="c">' + (r120 ? r120.name : '') + '</td><td class="c">' + (r120 ? fmtVal(r120.mktcap) : '') + '</td>';
        nhHtml += '<td class="c" style="border-left:2px solid #2E7D32">' + (r52 ? sec(r52.code) : '') + '</td><td class="c">' + (r52 ? r52.name : '') + '</td><td class="c">' + (r52 ? fmtVal(r52.mktcap) : '') + '</td>';
        nhHtml += '</tr>';
    }}
    document.getElementById('newHighTable').innerHTML = nhHtml || '<tr><td colspan="10" style="text-align:center;padding:40px;color:#888;">데이터 없음</td></tr>';
}}
refresh();
</script>
</body>
</html>"""

    with open('featured.html', 'w', encoding='utf-8') as f:
        f.write(featured_page.replace('__FEATURED_UPDATED__', now))
    print("Featured page generated: featured.html")

    # ── ETF page ──
    generate_etf_html()

    # ── Hotels ADR page ──
    generate_hotels_html()


def generate_hotels_html():
    """Hotel ADR 페이지 생성 (Booking.com 10호텔 entry 객실 일별 가격)"""
    import pandas as pd

    csv_file = 'hotel_adr.csv'
    if not os.path.exists(csv_file):
        print("hotel_adr.csv not found, skipping hotels.html")
        return
    df = pd.read_csv(csv_file)
    if len(df) == 0:
        print("hotel_adr.csv empty, skipping hotels.html")
        return

    # 가장 최근 collected_at 행만 (당일 매트릭스)
    latest = df['collected_at'].max()
    df_latest = df[df['collected_at'] == latest]

    # 호텔별 도시·등급 메타
    meta = df_latest[['hotel', 'city', 'grade']].drop_duplicates().set_index('hotel').to_dict(orient='index')

    # 매트릭스: 호텔 × lead_days
    pivot = df_latest.pivot(index='hotel', columns='lead_days', values='price_krw')

    # 행 HTML (호텔 카테고리 순으로 정렬: 서울 → 부산 → 제주 → 경주)
    city_order = ['서울', '부산', '제주', '경주']
    grade_order = {'Lux': 0, '5*': 1, '4*': 2}

    def sort_key(hotel_name):
        m = meta.get(hotel_name, {})
        return (city_order.index(m.get('city', '서울')) if m.get('city') in city_order else 99,
                grade_order.get(m.get('grade'), 99))

    rows_html = ''
    for hotel in sorted(pivot.index, key=sort_key):
        m = meta.get(hotel, {})
        rows_html += f'<tr><td class="hotel-name">{hotel}</td>'
        rows_html += f'<td class="hotel-meta">{m.get("city", "")}</td>'
        rows_html += f'<td class="hotel-meta">{m.get("grade", "")}</td>'
        for lead in [7, 14, 30]:
            v = pivot.loc[hotel].get(lead)
            if v is None or pd.isna(v):
                rows_html += '<td class="price-empty">-</td>'
            else:
                rows_html += f'<td class="price">₩{int(v):,}</td>'
        rows_html += '</tr>\n'

    # 데이터 누적 일수
    unique_days = df['collected_at'].str[:10].nunique()

    # 시계열 차트: lead+7 호텔별 라인 (데이터 ≥ 3일 누적 시)
    # Chart.js로 클라이언트 렌더 — PNG를 굽지 않는다. (매 실행마다 바이너리 PNG가
    # 새로 생성돼 working tree에 떠 git pull/merge를 막던 충돌을 근본 제거 +
    # 대시보드 전체 차트 방식을 Chart.js로 통일.)
    chart_card_html = '<div class="card"><p class="note">시계열 차트는 데이터 3일 이상 누적 후 표시됩니다 (현재 %d일).</p></div>' % unique_days
    if unique_days >= 3:
        df_lead7 = df[df['lead_days'] == 7].copy()
        df_lead7['date'] = df_lead7['collected_at'].str[:10]
        # 하루에 여러 번 수집된 경우 마지막 값만 (일일 최신 스냅샷 기준).
        df_lead7 = df_lead7.sort_values('collected_at').drop_duplicates(subset=['date', 'hotel'], keep='last')
        pivot_ts = df_lead7.pivot(index='date', columns='hotel', values='price_krw') / 1000
        ts_labels = [str(d) for d in pivot_ts.index]
        ts_hotels = sorted(pivot_ts.columns, key=sort_key)  # 표와 동일 정렬(도시→등급)
        _palette = ['#1428A0', '#0072CE', '#00854A', '#E0001B', '#FF8200',
                    '#6A1B9A', '#00838F', '#5D4037', '#C2185B', '#558B2F']
        ts_datasets = []
        for i, h in enumerate(ts_hotels):
            ser = pivot_ts[h]
            ts_datasets.append({
                'label': h,
                'data': [None if pd.isna(v) else round(float(v), 1) for v in ser],
                'borderColor': _palette[i % len(_palette)],
                'backgroundColor': _palette[i % len(_palette)],
                'borderWidth': 2, 'pointRadius': 2, 'tension': 0.25, 'spanGaps': True,
            })
        _ts_json = json.dumps({'labels': ts_labels, 'datasets': ts_datasets}, ensure_ascii=False)
        chart_card_html = ("""
  <div class="card">
    <h2 style="margin-top:0;font-size:1.2rem;">시계열 (lead+7일, 천원)</h2>
    <div style="position:relative;height:420px;"><canvas id="hotelAdrChart"></canvas></div>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script>Chart.defaults.font.family = "'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif"; Chart.defaults.devicePixelRatio = 2 * (window.devicePixelRatio || 1); Chart.defaults.elements.line.borderJoinStyle = 'round'; Chart.defaults.elements.line.borderCapStyle = 'round';</script>
  <script>
  (function(){
    var D = __HOTEL_ADR_DATA__;
    new Chart(document.getElementById('hotelAdrChart'), {
      type: 'line',
      data: {labels: D.labels, datasets: D.datasets},
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: {mode: 'index', intersect: false},
        plugins: {
          legend: {position: 'bottom', labels: {boxWidth: 12, font: {size: 12}}},
          tooltip: {callbacks: {label: function(c){ return c.dataset.label + ': ' + (c.parsed.y == null ? '-' : c.parsed.y.toLocaleString() + '천원'); }}}
        },
        scales: {
          x: {grid: {display: false}, ticks: {maxRotation: 0, autoSkip: true, color: '#000'}},
          y: {title: {display: true, text: '1박 가격 (천원)'}, ticks: {color: '#000', callback: function(v){ return v.toLocaleString(); }}}
        }
      }
    });
  })();
  </script>
""").replace('__HOTEL_ADR_DATA__', _ts_json)

    # HTML 생성
    update_time = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>Hotel ADR - Antigravity Dashboard</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: 'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif; background: #f5f5f5; margin: 0; padding: 30px; color: #222; }}
  .home-btn {{ position: fixed; top: 20px; right: 20px; background: #e0e0e0; color: #222; padding: 8px 18px; border-radius: 8px; text-decoration: none; font-size: 15px; font-weight: 600; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 8px; }}
  .meta {{ color: #888; font-size: 13px; margin-bottom: 24px; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  .card {{ background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 24px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ background: #222; color: #fff; padding: 10px 14px; text-align: left; font-weight: 600; font-size: 13px; }}
  td {{ padding: 10px 14px; border-bottom: 1px solid #eee; font-size: 14px; }}
  td.hotel-name {{ font-weight: 600; }}
  td.hotel-meta {{ color: #666; font-size: 13px; }}
  td.price {{ text-align: right; font-feature-settings: 'tnum'; font-weight: 500; }}
  td.price-empty {{ text-align: right; color: #ccc; }}
  tr:hover {{ background: #fafafa; }}
  .note {{ font-size: 13px; color: #666; margin-top: 16px; padding: 12px; background: #fff8e1; border-radius: 8px; border-left: 3px solid #ffc107; }}
  {TOP_NAV_CSS}
</style>
</head>
<body>
{top_nav_html('')}
<div class="container">
  <h1>Hotel ADR — Booking.com</h1>
  <p class="meta">Updated: {update_time} KST · 누적 {unique_days}일 · 매일 12:00 KST 자동 수집</p>

  <div class="card">
    <h2 style="margin-top:0;font-size:1.2rem;">당일 entry 객실 가격 (체크인 lead time별)</h2>
    <table>
      <thead>
        <tr>
          <th>호텔</th><th>도시</th><th>등급</th>
          <th style="text-align:right;">+7일</th>
          <th style="text-align:right;">+14일</th>
          <th style="text-align:right;">+30일</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    <p class="note">※ 각 호텔에서 가장 저렴한 entry 객실 1박 가격 (2인, 환불가능 옵션 우선). Booking.com 기준이라 외국인 가격 포함될 수 있음.</p>
  </div>

  {chart_card_html}
</div>
</body>
</html>
"""

    with open('hotels.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("Hotels page generated: hotels.html")


def generate_etf_html():
    """ETF 대시보드 페이지 생성"""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'etf_collector'))
    try:
        from etf_db import get_all_etf_daily, get_available_dates, get_constituents_for_date
    except ImportError:
        print("ETF DB not available, skipping etf.html")
        return

    dates = get_available_dates()
    if not dates:
        print("No ETF data, skipping etf.html")
        return

    latest = dates[0]
    prev = dates[1] if len(dates) > 1 else None
    daily = get_all_etf_daily()
    constituents = get_constituents_for_date(latest)
    prev_constituents = get_constituents_for_date(prev) if prev else {}

    # JSON 데이터 준비
    import json
    daily_json = json.dumps([
        {'d': r['date'], 'code': r['etf_code'], 'name': r['etf_name'],
         'close': r['close_price'], 'nav': r['nav'], 'vol': r['volume'],
         'aum': r['aum'], 'mcap': r['market_cap']}
        for r in daily
    ], ensure_ascii=False)

    const_json = json.dumps(constituents, ensure_ascii=False)
    prev_const_json = json.dumps(prev_constituents, ensure_ascii=False)
    dates_json = json.dumps(dates)
    prev_date = prev or ''

    page = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETF Dashboard</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif; font-size: 1.05rem; background: #f8f9fa; color: #333; }}
header {{ padding: 20px 24px; margin: 0 0 40px; text-align: center; position: relative; }}
header h1 {{ margin: 0; font-size: 33px; color: #333; font-weight: 700; line-height: 1.2; }}
        .last-updated {{ margin-top: 10px; color: #6c757d; font-size: 15px; font-style: italic; }}
.home-btn {{ position: absolute; top: 20px; right: 24px; padding: 6px 16px; background: #e0e0e0; color: #333; text-decoration: none; border-radius: 8px; font-size: 15px; font-weight: 600; }}
.container {{ max-width: 1800px; margin: 0 auto; padding: 20px; }}
.controls {{ display: flex; gap: 8px; align-items: center; margin-bottom: 16px; }}
.controls input {{ padding: 8px 14px; border: 2px solid #ddd; border-radius: 8px; font-size: 0.9rem; font-family: inherit; outline: none; width: 200px; }}
.controls input:focus {{ border-color: #2d7a3a; }}
.controls select {{ padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 0.85rem; background: #fff; font-family: inherit; }}
.controls label {{ font-size: 0.85rem; color: #666; display: flex; align-items: center; gap: 4px; white-space: nowrap; }}
.section {{ background: #fff; border-radius: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); margin-bottom: 20px; overflow: hidden; }}
.section-header {{ padding: 14px 20px; font-size: 1rem; font-weight: 700; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }}
.section-header .count {{ font-size: 0.8rem; color: #888; font-weight: 400; }}
table {{ width: 100%; border-collapse: collapse; font-size: 16px; }}
thead {{ background: #2d7a3a; }}
th {{ padding: 10px 8px; text-align: center; font-weight: 600; color: #fff; cursor: pointer; white-space: nowrap; }}
th:hover {{ background: #1f5a2a; }}
th .arr {{ font-size: 0.6rem; margin-left: 2px; }}
td {{ padding: 8px 8px; border-bottom: 1px solid #f0f0f0; text-align: center; }}
tbody tr:hover {{ background: #f0f7f2; }}
tbody tr.etf-row {{ cursor: pointer; }}
tbody tr.etf-row:hover {{ background: #f0f7f2; }}
.num {{ text-align: center; font-variant-numeric: tabular-nums; }}
.pos {{ color: #cc0000; font-weight: 600; }}
.neg {{ color: #0055cc; font-weight: 600; }}
.etf-name {{ text-align: center; font-weight: 600; }}
.constituents-row {{ background: #f0f7f2; }}
.constituents-row td {{ padding: 0; }}
.const-table {{ width: 100%; font-size: 0.78rem; }}
.const-table th {{ background: #f0f7f2; color: #333; padding: 6px 8px; font-size: 0.75rem; }}
.const-table td {{ padding: 5px 8px; border-bottom: 1px solid #f0f7f2; }}
.const-table tbody tr:hover {{ background: #f0f7f2; }}
.search-results {{ display: none; }}
.search-results.active {{ display: block; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }}
.updated {{ text-align: center; font-size: 0.75rem; color: #aaa; margin-top: 10px; }}
{TOP_NAV_CSS}
</style>
</head>
<body class="has-sidebar">
{top_nav_html('etf')}
{sidebar_html('etf')}
<header>
    <h1>🏛️ ETF Dashboard</h1>
    <div class="last-updated">Updated: {datetime.now(tz=KST).strftime("%Y-%m-%d %H:%M:%S KST")}</div>
</header>

<div class="container">
    <div class="etf-tabs" style="display:flex;gap:0;margin-bottom:20px;border-bottom:2px solid #2d7a3a;">
        <div class="etf-tab active" onclick="switchEtfTab(0)" style="padding:10px 24px;cursor:pointer;font-weight:600;font-size:16px;color:#666;border:1px solid transparent;border-bottom:none;border-radius:8px 8px 0 0;background:#f0f0f0;">AUM 상위</div>
        <div class="etf-tab" onclick="switchEtfTab(1)" style="padding:10px 24px;cursor:pointer;font-weight:600;font-size:16px;color:#666;border:1px solid transparent;border-bottom:none;border-radius:8px 8px 0 0;background:#f0f0f0;">종목 분석</div>
    </div>
    <div id="etfTab0" class="etf-tab-content">
    <div class="controls">
        <input type="text" id="searchInput" placeholder="종목명 검색" oninput="onSearch()">
        <select id="dateSelect" onchange="onDateChange()"></select>
        <label><input type="checkbox" id="showAll" onchange="render()"> 전체 표시</label>
    </div>

    <div id="searchResults" class="section search-results">
        <div class="section-header">🔍 종목 검색 결과 <span class="count" id="searchCount"></span></div>
        <div style="overflow-x:auto"><table>
            <thead><tr><th onclick="sortSearch(0)" style="cursor:pointer">ETF<span class="sarr" id="sa0"></span></th><th onclick="sortSearch(1)" style="cursor:pointer">비중(%)<span class="sarr" id="sa1"></span></th><th onclick="sortSearch(2)" style="cursor:pointer">AUM<span class="sarr" id="sa2"></span></th><th onclick="sortSearch(3)" style="cursor:pointer">편입금액<span class="sarr" id="sa3"></span></th></tr></thead>
            <tbody id="searchBody"></tbody>
        </table></div>
    </div>

    <div class="section">
        <div class="section-header">AUM 상위 ETF <span class="count" id="mainCount"></span></div>
        <div style="overflow-x:auto"><table>
            <thead><tr>
                <th onclick="doSort(0)">#<span class="arr"></span></th>
                <th onclick="doSort(1)">ETF명<span class="arr"></span></th>
                <th onclick="doSort(2)">AUM<span class="arr"></span></th>
                <th onclick="doSort(3)">NAV<span class="arr"></span></th>
                <th onclick="doSort(4)">종가<span class="arr"></span></th>
                <th onclick="doSort(5)">거래량<span class="arr"></span></th>
            </tr></thead>
            <tbody id="mainBody"></tbody>
        </table></div>
    </div>

    <p class="updated">Data: {latest} | Source: KRX OpenAPI + etfcheck.co.kr</p>
    </div>

    <div id="etfTab1" class="etf-tab-content" style="display:none">
        <div class="section">
            <div class="section-header">📈 순유입 상위 30 <span class="count">({latest})</span></div>
            <div style="overflow-x:auto"><table>
                <thead><tr><th>#</th><th>종목</th><th>오늘 편입금액</th><th>전일 편입금액</th><th>변화</th></tr></thead>
                <tbody id="inflowBody"></tbody>
            </table></div>
        </div>
        <div class="section">
            <div class="section-header">📉 순유출 상위 30 <span class="count">({latest})</span></div>
            <div style="overflow-x:auto"><table>
                <thead><tr><th>#</th><th>종목</th><th>오늘 편입금액</th><th>전일 편입금액</th><th>변화</th></tr></thead>
                <tbody id="outflowBody"></tbody>
            </table></div>
        </div>
        <div class="section">
            <div class="section-header">🆕 신규 편입 종목 <span class="count">(AUM 상위 ETF 기준)</span></div>
            <div style="overflow-x:auto"><table>
                <thead><tr><th>#</th><th>종목</th><th>ETF</th><th>비중(%)</th><th>ETF AUM</th></tr></thead>
                <tbody id="newEntryBody"></tbody>
            </table></div>
        </div>
        <div class="section">
            <div class="section-header">❌ 편출 종목 <span class="count">(AUM 상위 ETF 기준)</span></div>
            <div style="overflow-x:auto"><table>
                <thead><tr><th>#</th><th>종목</th><th>ETF</th><th>비중(%)</th><th>ETF AUM</th></tr></thead>
                <tbody id="exitBody"></tbody>
            </table></div>
        </div>
        <div class="section">
            <div class="section-header">💰 ETF AUM 증감 상위</div>
            <div style="overflow-x:auto"><table>
                <thead><tr><th>#</th><th>ETF</th><th>오늘 AUM</th><th>전일 AUM</th><th>변화</th></tr></thead>
                <tbody id="aumChangeBody"></tbody>
            </table></div>
        </div>
    </div>
</div>

<script>
var allDaily = {daily_json};
var allConst = {const_json};
var prevConst = {prev_const_json};
var dates = {dates_json};

var curDate = dates[0] || '';
var sortCol = 2, sortAsc = false; // default: AUM desc
var openETF = null;

// Init date select
(function() {{
    var sel = document.getElementById('dateSelect');
    dates.forEach(function(d) {{
        var o = document.createElement('option');
        o.value = d; o.textContent = d;
        sel.appendChild(o);
    }});
}})();

function fmtAum(v) {{
    if (!v) return '-';
    var jo = Math.floor(v / 1e12);
    var eok = Math.round((v % 1e12) / 1e8);
    if (jo > 0 && eok > 0) return jo.toLocaleString() + '조 ' + eok.toLocaleString() + '억';
    if (jo > 0) return jo.toLocaleString() + '조';
    return eok.toLocaleString() + '억';
}}

function fmtNum(v) {{
    if (!v && v !== 0) return '-';
    return Number(v).toLocaleString();
}}

function getDaily() {{
    return allDaily.filter(function(r) {{ return r.d === curDate; }});
}}

function pn(s) {{
    var n = parseFloat(String(s).replace(/,/g, ''));
    return isNaN(n) ? -Infinity : n;
}}

function doSort(col) {{
    if (sortCol === col) sortAsc = !sortAsc;
    else {{ sortCol = col; sortAsc = (col <= 1); }}
    render();
}}

function onDateChange() {{
    curDate = document.getElementById('dateSelect').value;
    render();
}}

function render() {{
    var data = getDaily();
    var showAll = document.getElementById('showAll').checked;
    var limit = showAll ? data.length : 30;

    // Sort
    var cols = ['_idx', 'name', 'aum', 'nav', 'close', 'vol'];
    var key = cols[sortCol] || 'aum';
    data.sort(function(a, b) {{
        var va = (key === 'name') ? a[key] : pn(a[key]);
        var vb = (key === 'name') ? b[key] : pn(b[key]);
        if (va < vb) return sortAsc ? -1 : 1;
        if (va > vb) return sortAsc ? 1 : -1;
        return 0;
    }});

    // Update sort arrows
    document.querySelectorAll('th .arr').forEach(function(s, i) {{
        s.textContent = (i === sortCol) ? (sortAsc ? ' ▲' : ' ▼') : '';
    }});

    var rows = data.slice(0, limit);
    var h = '';
    rows.forEach(function(r, i) {{
        var isOpen = (openETF === r.code);
        h += '<tr class="etf-row" onclick="toggleConst(\\''+r.code+'\\')">';
        h += '<td>' + (i+1) + '</td>';
        h += '<td class="etf-name">' + r.name + '</td>';
        h += '<td class="num">' + fmtAum(r.aum) + '</td>';
        h += '<td class="num">' + fmtNum(r.nav) + '</td>';
        h += '<td class="num">' + fmtNum(r.close) + '</td>';
        h += '<td class="num">' + fmtNum(r.vol) + '</td>';
        h += '</tr>';
        if (isOpen) {{
            var cList = allConst[r.code] || [];
            h += '<tr class="constituents-row"><td colspan="6"><table class="const-table">';
            h += '<thead><tr><th>#</th><th>종목명</th><th>종목코드</th><th>비중(%)</th></tr></thead><tbody>';
            cList.forEach(function(c, ci) {{
                h += '<tr><td>' + (ci+1) + '</td><td style="text-align:left">' + c.n + '</td><td>' + c.c + '</td><td class="num">' + (c.w ? c.w.toFixed(2) : '-') + '</td></tr>';
            }});
            if (!cList.length) h += '<tr><td colspan="4" style="color:#aaa;padding:12px">구성종목 데이터 없음</td></tr>';
            h += '</tbody></table></td></tr>';
        }}
    }});
    document.getElementById('mainBody').innerHTML = h;
    document.getElementById('mainCount').textContent = (showAll ? data.length : Math.min(30, data.length)) + '종목';
}}

function toggleConst(code) {{
    openETF = (openETF === code) ? null : code;
    render();
}}

var _srchSortCol = 3, _srchSortAsc = false, _srchMatches = [];
function sortSearch(col) {{
    if (_srchSortCol === col) _srchSortAsc = !_srchSortAsc;
    else {{ _srchSortCol = col; _srchSortAsc = false; }}
    renderSearchResults();
}}
function renderSearchResults() {{
    var ms = _srchMatches.slice();
    ms.sort(function(a,b) {{
        var va, vb;
        if (_srchSortCol === 0) {{ va=a.etfName; vb=b.etfName; return _srchSortAsc?va.localeCompare(vb):vb.localeCompare(va); }}
        if (_srchSortCol === 1) {{ va=a.weight||0; vb=b.weight||0; }}
        else if (_srchSortCol === 2) {{ va=a.aum||0; vb=b.aum||0; }}
        else {{ va=(a.weight&&a.aum)?a.aum*a.weight/100:0; vb=(b.weight&&b.aum)?b.aum*b.weight/100:0; }}
        return _srchSortAsc ? va-vb : vb-va;
    }});
    var h = '';
    ms.forEach(function(m) {{
        var invested = (m.weight && m.aum) ? m.aum * m.weight / 100 : 0;
        h += '<tr><td>' + m.etfName + '</td>';
        h += '<td>' + (m.weight ? m.weight.toFixed(2) : '-') + '</td>';
        h += '<td>' + fmtAum(m.aum) + '</td>';
        h += '<td>' + (invested > 0 ? fmtAum(invested) : '-') + '</td></tr>';
    }});
    if (!h) h = '<tr><td colspan="4" style="padding:20px;color:#aaa;text-align:center">결과 없음</td></tr>';
    document.getElementById('searchBody').innerHTML = h;
    document.getElementById('searchCount').textContent = ms.length + '건';
    for (var i=0;i<4;i++) document.getElementById('sa'+i).textContent = (_srchSortCol===i?(_srchSortAsc?' ▲':' ▼'):'');
}}

function onSearch() {{
    var q = document.getElementById('searchInput').value.trim();
    var panel = document.getElementById('searchResults');
    if (!q) {{ panel.classList.remove('active'); return; }}
    panel.classList.add('active');

    var ql = q.toLowerCase();
    var daily = getDaily();
    var aumMap = {{}};
    daily.forEach(function(r) {{ aumMap[r.code] = r; }});

    // Search constituents
    var matches = [];
    Object.keys(allConst).forEach(function(etfCode) {{
        var stocks = allConst[etfCode];
        stocks.forEach(function(s) {{
            if (s.n.toLowerCase().indexOf(ql) >= 0) {{
                var etf = aumMap[etfCode];
                if (etf) {{
                    matches.push({{ etfName: etf.name, etfCode: etfCode, weight: s.w, aum: etf.aum }});
                }}
            }}
        }});
    }});

    _srchMatches = matches;
    renderSearchResults();
}}

function switchEtfTab(idx) {{
    document.querySelectorAll('.etf-tab').forEach(function(t,i) {{
        t.style.color = i===idx ? '#2d7a3a' : '#666';
        t.style.background = i===idx ? '#fff' : '#f0f0f0';
        t.style.borderColor = i===idx ? '#2d7a3a #2d7a3a transparent' : 'transparent';
        t.style.marginBottom = i===idx ? '-2px' : '0';
    }});
    document.getElementById('etfTab0').style.display = idx===0 ? '' : 'none';
    document.getElementById('etfTab1').style.display = idx===1 ? '' : 'none';
    if (idx===1) renderAnalysis();
}}

var _analysisRendered = false;
function renderAnalysis() {{
    if (_analysisRendered) return;
    _analysisRendered = true;

    var latest = dates[0];
    var prev = dates.length > 1 ? dates[1] : null;
    if (!prev) return;

    // AUM maps
    var todayAum = {{}}, prevAum = {{}};
    allDaily.forEach(function(r) {{
        if (r.d === latest) todayAum[r.code] = r;
        if (r.d === prev) prevAum[r.code] = r;
    }});

    // 1. 종목별 편입금액 계산
    function calcStockAmounts(constData, aumMap) {{
        var result = {{}};
        Object.keys(constData).forEach(function(etfCode) {{
            var etf = aumMap[etfCode];
            if (!etf) return;
            constData[etfCode].forEach(function(s) {{
                var amt = (s.w || 0) * etf.aum / 100;
                if (!result[s.c]) result[s.c] = {{name: s.n, code: s.c, total: 0}};
                result[s.c].total += amt;
            }});
        }});
        return result;
    }}

    var todayAmts = calcStockAmounts(allConst, todayAum);
    var prevAmts = calcStockAmounts(prevConst, prevAum);

    // 순유입/유출
    var changes = [];
    Object.keys(todayAmts).forEach(function(code) {{
        var today = todayAmts[code].total;
        var prev = prevAmts[code] ? prevAmts[code].total : 0;
        changes.push({{name: todayAmts[code].name, code: code, today: today, prev: prev, diff: today - prev}});
    }});
    // 전일에만 있는 종목
    Object.keys(prevAmts).forEach(function(code) {{
        if (!todayAmts[code]) {{
            changes.push({{name: prevAmts[code].name, code: code, today: 0, prev: prevAmts[code].total, diff: -prevAmts[code].total}});
        }}
    }});

    changes.sort(function(a,b) {{ return b.diff - a.diff; }});
    var inflow = changes.slice(0, 30);
    var outflow = changes.slice(-30).reverse();
    outflow.sort(function(a,b) {{ return a.diff - b.diff; }});

    function fmtB(v) {{ if (Math.abs(v) >= 1e12) return (v/1e12).toFixed(1)+'조'; if (Math.abs(v) >= 1e8) return Math.round(v/1e8).toLocaleString()+'억'; return Math.round(v).toLocaleString(); }}
    function diffCls(v) {{ return v > 0 ? 'pos' : v < 0 ? 'neg' : ''; }}

    var h1 = '';
    inflow.forEach(function(r,i) {{
        h1 += '<tr><td>'+(i+1)+'</td><td>'+r.name+'</td><td>'+fmtB(r.today)+'</td><td>'+fmtB(r.prev)+'</td><td class="'+diffCls(r.diff)+'">'+((r.diff>0?'+':'')+fmtB(r.diff))+'</td></tr>';
    }});
    document.getElementById('inflowBody').innerHTML = h1;

    var h2 = '';
    outflow.forEach(function(r,i) {{
        h2 += '<tr><td>'+(i+1)+'</td><td>'+r.name+'</td><td>'+fmtB(r.today)+'</td><td>'+fmtB(r.prev)+'</td><td class="'+diffCls(r.diff)+'">'+((r.diff>0?'+':'')+fmtB(r.diff))+'</td></tr>';
    }});
    document.getElementById('outflowBody').innerHTML = h2;

    // 2. 신규 편입/편출 (AUM 상위 100 ETF 기준)
    var topEtfs = allDaily.filter(function(r){{return r.d===latest;}}).sort(function(a,b){{return b.aum-a.aum;}}).slice(0,100);
    var topCodes = {{}};
    topEtfs.forEach(function(r){{topCodes[r.code]=r;}});

    var newEntries = [], exits = [];
    Object.keys(topCodes).forEach(function(etfCode) {{
        var todayStocks = allConst[etfCode] || [];
        var prevStocks = prevConst[etfCode] || [];
        var prevSet = {{}};
        prevStocks.forEach(function(s) {{ prevSet[s.c] = s; }});
        var todaySet = {{}};
        todayStocks.forEach(function(s) {{ todaySet[s.c] = s; }});

        todayStocks.forEach(function(s) {{
            if (!prevSet[s.c]) {{
                newEntries.push({{stock: s.n, etf: topCodes[etfCode].name, weight: s.w, aum: topCodes[etfCode].aum}});
            }}
        }});
        prevStocks.forEach(function(s) {{
            if (!todaySet[s.c]) {{
                exits.push({{stock: s.n, etf: topCodes[etfCode].name, weight: s.w, aum: topCodes[etfCode].aum}});
            }}
        }});
    }});

    newEntries.sort(function(a,b){{return b.aum-a.aum;}});
    var h3 = '';
    newEntries.slice(0,50).forEach(function(r,i) {{
        h3 += '<tr><td>'+(i+1)+'</td><td>'+r.stock+'</td><td>'+r.etf+'</td><td>'+(r.weight?r.weight.toFixed(2):'-')+'</td><td>'+fmtAum(r.aum)+'</td></tr>';
    }});
    document.getElementById('newEntryBody').innerHTML = h3 || '<tr><td colspan="5" style="padding:20px;color:#aaa;text-align:center">없음</td></tr>';

    exits.sort(function(a,b){{return b.aum-a.aum;}});
    var h4 = '';
    exits.slice(0,50).forEach(function(r,i) {{
        h4 += '<tr><td>'+(i+1)+'</td><td>'+r.stock+'</td><td>'+r.etf+'</td><td>'+(r.weight?r.weight.toFixed(2):'-')+'</td><td>'+fmtAum(r.aum)+'</td></tr>';
    }});
    document.getElementById('exitBody').innerHTML = h4 || '<tr><td colspan="5" style="padding:20px;color:#aaa;text-align:center">없음</td></tr>';

    // 3. ETF AUM 증감
    var aumChanges = [];
    Object.keys(todayAum).forEach(function(code) {{
        var t = todayAum[code];
        var p = prevAum[code];
        if (t && p) {{
            aumChanges.push({{name: t.name, today: t.aum, prev: p.aum, diff: t.aum - p.aum}});
        }}
    }});
    aumChanges.sort(function(a,b){{return Math.abs(b.diff)-Math.abs(a.diff);}});

    var h5 = '';
    aumChanges.slice(0,30).forEach(function(r,i) {{
        h5 += '<tr><td>'+(i+1)+'</td><td>'+r.name+'</td><td>'+fmtAum(r.today)+'</td><td>'+fmtAum(r.prev)+'</td><td class="'+diffCls(r.diff)+'">'+((r.diff>0?'+':'')+fmtB(r.diff))+'</td></tr>';
    }});
    document.getElementById('aumChangeBody').innerHTML = h5;
}}

render();
</script>
</body>
</html>"""

    with open('etf.html', 'w', encoding='utf-8') as f:
        f.write(page)
    print("ETF page generated: etf.html")


if __name__ == "__main__":
    create_dashboard()
