
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
OUTPUT_FILE = 'market.html'
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
                                <th style="border-left:2px solid #000;">현재가</th>
                                <th>ATH</th>
                                <th>DD</th>
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
                                <td style="border-left:2px solid #000;">{current_price_str}</td>
                                <td>{ath_price_str}</td>
                                <td class="{dd_color_class}">{dd_str}</td>
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
                     '개방형', 'DB 개방형', '목표전환형 2차', 'DB 목표전환형 2차', '목표전환형 1호', 'NH 목표전환형 1호']
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
            '목표전환형 2차': 'DB 목표전환형 2차 / NH 목표전환형 1호',
        }

        today = pd.Timestamp.now().normalize()
        portfolio_sectors = {}

        for portfolio_name, display_name in portfolio_map.items():
            df_p = nav_df[nav_df['상품명'] == portfolio_name].copy()
            if df_p.empty:
                continue

            available_dates = sorted(df_p['날짜'].unique())
            # 16:20 KST 이후에는 당일 주문 포함 (결제는 익일 반영)
            from datetime import timezone, timedelta as _td
            _now_kst = pd.Timestamp.now(tz=timezone(_td(hours=9)))
            _date_cutoff = (_now_kst.normalize() if _now_kst.hour >= 16 else _now_kst.normalize() - pd.Timedelta(days=1)).tz_localize(None)
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
            ('DB 목표전환형 2차', '목표전환형 2차'),
            ('NH 목표전환형 1호', '목표전환형 1호'),
            ('KOSPI', 'KOSPI'),
            ('KOSDAQ', 'KOSDAQ'),
        ]
        chart_colors = {
            '삼성 트루밸류': '#1428A0',
            'NH Value ESG': '#0072CE',
            'DB 개방형': '#00854A',
            'DB 목표전환형 2차': 'rgba(0,133,74,0.8)',
            'NH 목표전환형 1호': 'rgba(0,114,206,0.6)',
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
        <script>Chart.defaults.font.family = "'Inter', 'Noto Sans KR', sans-serif";</script>
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

                var datasets = [];
                var returnLabels = [];

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

                    var base = filteredVals[0];
                    var data;
                    if (chartMode === 'mdd') {
                        var mddVals = calcMDD(filteredVals);
                        data = filteredDates.map(function(d, j) { return { x: d, y: mddVals[j] }; });
                    } else {
                        data = filteredDates.map(function(d, j) {
                            return { x: d, y: Math.round((filteredVals[j] / base - 1) * 10000) / 100 };
                        });
                    }

                    var lastPct = data[data.length - 1].y;
                    var sign = lastPct >= 0 ? '+' : '';
                    returnLabels.push({ name: name, pct: sign + lastPct.toFixed(1) + '%', color: chartColors[name] || '#888' });
                    datasets.push({
                        label: name,
                        data: data,
                        borderColor: chartColors[name] || '#888',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.3
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
                            var val = ds.data[ds.data.length - 1].y;
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

                if (wrapChart) wrapChart.destroy();
                wrapChart = new Chart(document.getElementById('wrapDynamicChart'), {
                    type: 'line',
                    data: { datasets: datasets },
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
            buildChart();
        })();
        </script>
        """.replace('NAV_DATA_PLACEHOLDER', nav_data_json).replace('COLORS_PLACEHOLDER', colors_json).replace('RAW_DATA_PLACEHOLDER', raw_data_json)

        return f"""
        <div class="category-section">
            <h2 class="category-title">{category_label}</h2>
            <div style="display:flex;gap:16px;align-items:flex-start;max-width:1200px;margin:0 auto;">
                <div style="min-width:180px;">{list_html}</div>
                <div style="flex:1;">
                    <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;font-size:13px;">
                        <span style="color:#555;font-weight:600;">기간</span>
                        <input type="text" id="wrapStartDate" value="{first_date}" onchange="formatDateInput(this);updateWrapChart()" style="font-family:inherit;font-size:13px;padding:4px 8px;border:1px solid #d1d5db;border-radius:6px;background:#f9fafb;color:#222;width:110px;text-align:center;" placeholder="YYYY-MM-DD">
                        <span style="color:#888;">~</span>
                        <input type="text" id="wrapEndDate" value="{last_date}" onchange="formatDateInput(this);updateWrapChart()" style="font-family:inherit;font-size:13px;padding:4px 8px;border:1px solid #d1d5db;border-radius:6px;background:#f9fafb;color:#222;width:110px;text-align:center;" placeholder="YYYY-MM-DD">
                    </div>
                    <div style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 4px 6px rgba(0,0,0,0.1);">
                        <canvas id="wrapDynamicChart" style="width:100%;height:500px;"></canvas>
                    </div>
                </div>
            </div>
        </div>
        {js_code}
        """
    except Exception as e:
        print(f"Error building wrap chart section: {e}")
        return ""


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
        # 증권사별 AUM 합계로 증권사 순서 결정, 같은 증권사 내에서는 AUM 내림차순
        broker_total = latest.groupby('증권사')['AUM'].sum().sort_values(ascending=False)
        latest['broker_rank'] = latest['증권사'].map({b: i for i, b in enumerate(broker_total.index)})
        latest = latest.sort_values(['broker_rank', 'AUM'], ascending=[True, False]).drop(columns='broker_rank')
        rows_html = ''
        total_aum = 0
        for _, row in latest.iterrows():
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
        df['label'] = df['증권사'] + ' ' + df['상품명']
        daily = df.groupby([df['날짜'].dt.strftime('%Y-%m-%d'), 'label', '증권사'])['AUM'].sum().reset_index()
        daily.columns = ['date', 'label', 'broker', 'aum']
        dates_sorted = sorted(daily['date'].unique())

        # 테이블과 같은 순서 (latest는 이미 증권사 그룹 + AUM 내림차순)
        all_labels = (latest.apply(lambda r: r['증권사'] + ' ' + r['상품명'], axis=1)).tolist()

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
            vals = []
            for d in dates_sorted:
                v = daily[(daily['date'] == d) & (daily['label'] == label)]['aum'].sum()
                vals.append(round(v / 100_000_000))
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
                        ctx.fillText(Math.round(total) + '억', bar.x, bar.y - 4);
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
                        tooltip: { callbacks: { label: function(ctx) { return ctx.dataset.label + ': ' + Math.round(ctx.raw) + '억'; } } }
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
            <h2 class="category-title">AUM</h2>
            <div style="display:flex;gap:100px;align-items:flex-start;max-width:1400px;margin:0 auto;">
                <div style="min-width:500px;">
                    <table class="portfolio-table" style="white-space:nowrap;width:100%;">
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
            ('삼성 트루밸류', '트루밸류'),
            ('DB 목표전환형 2차', '목표전환형 2차'),
            ('NH 목표전환형 1호', '목표전환형 1호'),
            ('KOSPI', 'KOSPI'),
            ('KOSDAQ', 'KOSDAQ'),
        ]
        periods = ['1D', '1W', '1M', '3M', '6M', '1Y', 'YTD']

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

        def cell_td(val, cell_id):
            s = val if val and val != 'nan' and val != 'None' else ''
            if not s:
                return f'<td id="{cell_id}" class="rt-cell rt-na">-</td>'
            try:
                num = float(s.replace('%', '').strip())
                cls = 'rt-pos' if num > 0 else 'rt-neg' if num < 0 else 'rt-zero'
            except Exception:
                cls = ''
            return f'<td id="{cell_id}" class="rt-cell {cls}">{s}</td>'

        latest_row = all_data.get(latest_date, {})
        rows_html = ''
        for display_name, key in items:
            rows_html += f'<tr><td class="rt-name">{display_name}</td>'
            for p in periods:
                rows_html += cell_td(latest_row.get(f'{key}_{p}'), f'rt-{key}-{p}')
            rows_html += '</tr>\n'

        headers = ''.join(f'<th class="rt-ph">{p}</th>' for p in periods)
        data_json = json.dumps(all_data, ensure_ascii=False)
        # sorted date list for floor-lookup in JS
        dates_sorted_json = json.dumps(sorted(date_list))
        items_json = json.dumps([[d, k] for d, k in items], ensure_ascii=False)
        periods_json = json.dumps(periods)

        return f"""
        <div class="category-section">
            <h2 class="category-title">RETURN</h2>
            <div style="max-width:800px;margin:0 auto;background:#fff;border-radius:10px;padding:16px 20px;box-shadow:0 2px 4px rgba(0,0,0,0.08);">
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
                        if (!val || val === 'nan') {{
                            cell.className = 'rt-cell rt-na';
                            cell.textContent = '-';
                        }} else {{
                            var num = parseFloat(val.replace('%', '').trim());
                            var cls = 'rt-cell';
                            if (!isNaN(num)) {{
                                cls += num > 0 ? ' rt-pos' : num < 0 ? ' rt-neg' : ' rt-zero';
                            }}
                            cell.className = cls;
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
                         'INTEREST RATES', 'CRYPTOCURRENCY', 'Memory', 'COMMODITIES']

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
                    'KRX GOLD Trading Volume',
                    'Silver',
                    'Copper',
                    'WTI Crude Oil',
                    'Brent Crude Oil',
                    'Natural Gas',
                    'Wheat Futures',
                    'Sprott Physical Uranium Trust',
                    'SCFI Comprehensive Index',
                    'KRX ETS  KAU25',
                    'KRX ETS Trading Volume'
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
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Market Data Dashboard</title>
    <link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=Noto+Sans+KR:wght@400;500;700&display=swap' rel='stylesheet'>
    <style>
        :root {{
            --bg-color: #f8f9fa;
            --card-bg: #ffffff;
            --text-color: #333333;
            --accent-color: #2d7a3a;
            --category-bg: #eeeeee;
        }}

        body {{
            font-family: 'Inter', 'Noto Sans KR', sans-serif;
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
    <header style="position:relative;">
        <h1>📊 Market Data Dashboard</h1>
        <div class="last-updated">Updated: {now}</div>
        <a href="index.html" style="position:absolute;top:20px;right:24px;padding:6px 16px;background:#e0e0e0;color:#333;text-decoration:none;border-radius:8px;font-size:0.85rem;font-weight:600;">🏠 Home</a>
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

    # ── Generate index.html (Landing page) ──
    landing_page = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Age of Emergence</title>
    <link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=Noto+Sans+KR:wght@400;500;700&display=swap' rel='stylesheet'>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Inter', 'Noto Sans KR', sans-serif; background: #f8f9fa; color: #333; min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px 20px; }}
        h1 {{ font-size: 2.2rem; font-weight: 800; margin-bottom: 48px; color: #111; }}
        .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; max-width: 800px; width: 100%; }}
        .card {{ background: #fff; border-radius: 14px; padding: 28px 24px; text-decoration: none; color: #333; box-shadow: 0 2px 12px rgba(0,0,0,0.06); border-left: 5px solid #ccc; transition: transform 0.15s, box-shadow 0.15s; display: block; }}
        .card:hover {{ transform: translateY(-4px); box-shadow: 0 8px 24px rgba(0,0,0,0.1); }}
        .card .icon {{ font-size: 1.8rem; margin-bottom: 12px; }}
        .card .title {{ font-size: 1.05rem; font-weight: 700; margin-bottom: 4px; }}
        .card .desc {{ font-size: 0.8rem; color: #888; line-height: 1.4; }}
        footer {{ margin-top: 48px; color: #bbb; font-size: 0.75rem; }}
    </style>
</head>
<body>
    <h1>Age of Emergence</h1>
    <div class="cards">
        <a href="market.html" class="card" style="border-left-color:#2d7a3a">
            <div class="icon">📊</div>
            <div class="title">Market</div>
            <div class="desc">Memory, Commodity, Crypto, FX, Index, Interest Rates</div>
        </a>
        <a href="wrap.html" class="card" style="border-left-color:#1e40af">
            <div class="icon">📈</div>
            <div class="title">WRAP</div>
            <div class="desc">Chart, Return, AUM, Portfolio</div>
        </a>
        <a href="market_alert.html" class="card" style="border-left-color:#c2410c">
            <div class="icon">🚦</div>
            <div class="title">투자유의종목</div>
            <div class="desc">투자주의 · 투자경고 · 투자위험 현황</div>
        </a>
        <a href="universe.html" class="card" style="border-left-color:#6B21A8">
            <div class="icon">🌐</div>
            <div class="title">Universe</div>
            <div class="desc">투자 유니버스 종목 리스트</div>
        </a>
        <a href="seibro.html" class="card" style="border-left-color:#0369a1">
            <div class="icon">🏦</div>
            <div class="title">SEIBro</div>
            <div class="desc">US 매수결제 TOP 50</div>
        </a>
        <a href="featured.html" class="card" style="border-left-color:#d97706">
            <div class="icon">⭐</div>
            <div class="title">Featured</div>
            <div class="desc">거래대금 TOP 30, 회전율 TOP 30</div>
        </a>
        <a href="etf.html" class="card" style="border-left-color:#6366f1">
            <div class="icon">🏛️</div>
            <div class="title">ETF</div>
            <div class="desc">AUM · 구성종목 · 비중 검색</div>
        </a>
        <a href="journal.html" class="card" style="border-left-color:#333;position:relative;">
            <div class="icon">📝</div>
            <div class="title">Journal</div>
            <div class="desc">투자일지</div>
            <div style="position:absolute;bottom:10px;right:14px;font-size:0.85rem;opacity:0.5;">🔒</div>
        </a>
        <a href="architecture.html" class="card" style="border-left-color:#666;position:relative;">
            <div class="icon">🗂️</div>
            <div class="title">Architecture</div>
            <div class="desc">워크플로우 아키텍처</div>
            <div style="position:absolute;bottom:10px;right:14px;font-size:0.85rem;opacity:0.5;">🔒</div>
        </a>
    </div>
    <footer>Age of Emergence</footer>
</body>
</html>"""

    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(landing_page)
    print("Landing page generated: index.html")

    # ── Generate wrap.html (WRAP + Portfolio + Sector) ──
    wrap_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WRAP</title>
    <link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=Noto+Sans+KR:wght@400;500;700&display=swap' rel='stylesheet'>
    <style>
        :root {{ --bg-color: #f8f9fa; --card-bg: #ffffff; --text-color: #333333; }}
        body {{ font-family: 'Inter', 'Noto Sans KR', sans-serif; background-color: var(--bg-color); color: var(--text-color); margin: 0; padding: 20px; }}
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
        .portfolio-section-wrapper {{ max-width: 1600px; margin: 0 auto; }}
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
        .rt-nh {{ width:130px; padding:7px 10px; text-align:left; font-weight:600; color:#111; border-bottom:2px solid #111; background:#f0f0f0; }}
        .rt-ph {{ padding:7px 10px; text-align:center; font-weight:600; color:#111; border-bottom:2px solid #111; background:#f0f0f0; white-space:nowrap; min-width:54px; }}
        .rt-name {{ padding:8px 10px; font-weight:600; border-bottom:1px solid #eee; white-space:nowrap; }}
        .rt-cell {{ padding:8px 10px; text-align:center; border-bottom:1px solid #eee; font-variant-numeric:tabular-nums; white-space:nowrap; }}
        .rt-pos {{ color:#cc0000; font-weight:600; }}
        .rt-neg {{ color:#0055cc; font-weight:600; }}
        .rt-zero {{ color:#555; }}
        .rt-na {{ color:#bbb; }}
        .rt-table tbody tr:hover td {{ background:#f9fafb; }}
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

    <div id="mainContent" class="pw-hidden">
    <header style="position:relative;">
        <h1>📈 WRAP</h1>
        <div class="last-updated">Updated: {now}</div>
        <a href="index.html" style="position:absolute;top:20px;right:24px;padding:6px 16px;background:#e0e0e0;color:#333;text-decoration:none;border-radius:8px;font-size:0.85rem;font-weight:600;">🏠 Home</a>
    </header>

    {wrap_html}

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
    <link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=Noto+Sans+KR:wght@400;500;700&display=swap' rel='stylesheet'>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', 'Noto Sans KR', sans-serif; font-size: 1.05rem; background: #f8f9fa; color: #333; }
        header { background: #fff; padding: 24px; text-align: center; border-bottom: 1px solid #eee; }
        header h1 { font-size: 33px; color: #6B21A8; }
        .nav-group { margin-top: 10px; }
        .nav-button { display: inline-block; padding: 6px 16px; border-radius: 6px; text-decoration: none; color: #fff; font-size: 0.85rem; font-weight: 600; background: #333; }
        .content { padding: 24px; max-width: 1600px; margin: 0 auto; }
        .tabs { display: flex; gap: 0; margin-bottom: 20px; border-bottom: 2px solid #6B21A8; }
        .tab { padding: 10px 24px; cursor: pointer; font-weight: 600; font-size: 16px; color: #666; border: 1px solid transparent; border-bottom: none; border-radius: 8px 8px 0 0; background: #f0f0f0; }
        .tab.active { color: #6B21A8; background: #fff; border-color: #6B21A8 #6B21A8 transparent; margin-bottom: -2px; }
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
        .csel-item:hover { background: #e9e0f5; }
        .csel-item.selected { background: #6B21A8; color: #fff; }
        .sector-group { margin-bottom: 24px; }
        .sector-group h3 { font-size: 18px; color: #6B21A8; margin-bottom: 8px; padding: 8px 0; border-bottom: 1px solid #6B21A8; }
        table { width: 100%; border-collapse: collapse; font-size: 16px; table-layout: fixed; }
        thead { background: #e9ecef; }
        th { padding: 12px 6px; text-align: center; font-weight: 600; color: #000; border-bottom: 2px solid #000; cursor: pointer; white-space: nowrap; overflow: hidden; }
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
        #tab0 th:nth-child(n+8) { width: 7%; }
        tbody tr:hover { background: #f5f5f5; }
        .positive { color: #cc0000; font-weight: 600; }
        .negative { color: #0055cc; font-weight: 600; }
        footer { text-align: center; padding: 24px; color: #999; font-size: 14px; }
    </style>
</head>
<body>
<header>
    <div style="max-width:1600px;margin:0 auto;padding:0 24px;position:relative;">
        <h1>Universe</h1>
        <div style="margin-top:10px;color:#6c757d;font-style:italic;font-size:15px;">Updated: __UNIVERSE_UPDATED__</div>
        <div style="position:absolute;top:20px;right:24px;display:flex;gap:8px;">
            <a href="https://docs.google.com/spreadsheets/d/1KR9RJN53G-yJtnowQbg5bcAiIBfrkIeNqN_PO2UOCTM/edit" target="_blank" style="background:#6B21A8;color:#fff;font-size:15px;font-weight:600;text-decoration:none;padding:6px 16px;border-radius:8px;">Sheet</a>
            <a href="index.html" style="padding:6px 16px;background:#e0e0e0;color:#333;text-decoration:none;border-radius:8px;font-size:15px;font-weight:600;">Home</a>
        </div>
    </div>
</header>
<div class="content">
    <div class="tabs">
        <div class="tab active" onclick="switchTab(0)">종목 리스트</div>
        <div class="tab" onclick="switchTab(1)">섹터 수익률</div>
    </div>
    <div id="tab0" class="tab-content active">
    <div class="filters">
        <div class="csel-wrap" id="cselCurWrap">
            <div class="csel-display" id="cselCurDisplay" onclick="toggleCselId('cselCurList')">통화 전체</div>
            <div class="csel-list" id="cselCurList"></div>
        </div>
        <div class="csel-wrap" id="cselSecWrap">
            <div class="csel-display" id="cselSecDisplay" onclick="toggleCselId('cselSecList')">섹터 전체</div>
            <div class="csel-list" id="cselSecList"></div>
        </div>
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
            <th onclick="doSort(7)">YTD</th>
            <th onclick="doSort(8)">1D</th>
            <th onclick="doSort(9)">1W</th>
            <th onclick="doSort(10)">1M</th>
            <th onclick="doSort(11)">3M</th>
            <th onclick="doSort(12)">6M</th>
            <th onclick="doSort(13)">1Y</th>
        </tr></thead>
        <tbody id="tbody"><tr><td colspan="14" style="padding:40px;color:#888;">로딩 중...</td></tr></tbody>
    </table>
    </div>
    <div id="tab1" class="tab-content">
        <div class="filters">
            <div class="csel-wrap" id="cselWrap">
                <div class="csel-display" id="cselDisplay" onclick="toggleCselId('cselList')">전체</div>
                <div class="csel-list" id="cselList"></div>
            </div>
        </div>
        <div id="sectorContent"><p style="padding:40px;color:#888;">로딩 중...</p></div>
    </div>
</div>
<footer>Antigravity Universe</footer>
<script>
var D=[],sortCol=-1,sortAsc=true;
var headers=['#','통화','섹터','티커','기업명','시가총액','가격','YTD','1D','1W','1M','3M','6M','1Y'];
var numCols=[0,5,6,7,8,9,10,11,12,13];
var pctCols=[7,8,9,10,11,12,13];

fetch('https://sheets.googleapis.com/v4/spreadsheets/1KR9RJN53G-yJtnowQbg5bcAiIBfrkIeNqN_PO2UOCTM/values/universe?key=AIzaSyCHPiRby5FVAIKDwneZHy1KGl3SfycjZEw')
.then(function(r){return r.json()}).then(function(data){
    D=(data.values||[]).slice(1).map(function(r){return r.slice(0,14)});
    var c={},sec={};
    D.forEach(function(r){if(r[1])c[r[1]]=1;if(r[2])sec[r[2]]=1;});
    var ch='<div class="csel-item selected" data-v="">통화 전체</div>';
    Object.keys(c).sort().forEach(function(v){ch+='<div class="csel-item" data-v="'+v+'">'+v+'</div>';});
    document.getElementById('cselCurList').innerHTML=ch;
    document.getElementById('cselCurList').addEventListener('click',function(e){var item=e.target.closest('.csel-item');if(item)pickCselCur(item.getAttribute('data-v'),item.textContent);});
    var sh='<div class="csel-item selected" data-v="">섹터 전체</div>';
    Object.keys(sec).sort().forEach(function(v){sh+='<div class="csel-item" data-v="'+v+'">'+v+'</div>';});
    document.getElementById('cselSecList').innerHTML=sh;
    document.getElementById('cselSecList').addEventListener('click',function(e){var item=e.target.closest('.csel-item');if(item)pickCselSec(item.getAttribute('data-v'),item.textContent);});
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
            var va=isN?pn(a[sortCol]):(a[sortCol]||'');
            var vb=isN?pn(b[sortCol]):(b[sortCol]||'');
            if(va<vb)return sortAsc?-1:1;
            if(va>vb)return sortAsc?1:-1;
            return 0;
        });
    }
    var h='';
    f.forEach(function(r,idx){
        h+='<tr>';
        for(var i=0;i<14;i++){
            var v=(i===0)?(idx+1):r[i]||'';if(i===3&&v.indexOf(':')>=0)v=v.split(':').pop();var cls='';
            if(pctCols.indexOf(i)>=0&&v){var n=parseFloat(String(v).replace(/%/g,''));if(!isNaN(n))cls=n>0?' class="positive"':n<0?' class="negative"':'';}
            var bg=(i===7)?' style="background:#f3f0ff;"':'';
            h+='<td'+cls+bg+'>'+v+'</td>';
        }
        h+='</tr>';
    });
    if(!h)h='<tr><td colspan="14" style="padding:40px;color:#888;">데이터 없음</td></tr>';
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
        var lh = '<div class="csel-item selected" data-v="">전체</div>';
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

    // 섹터별 집계 (시총 가중평균)
    var agg = {};
    filtered.forEach(function(r) {
        var sec = r[2] || '기타';
        if(!agg[sec]) agg[sec] = {cnt:0, ytd:[], d1:[], w1:[], m1:[], m3:[], m6:[], y1:[]};
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
        var vals = [r[7],r[8],r[9],r[10],r[11],r[12],r[13]];
        var arrs = [g.ytd,g.d1,g.w1,g.m1,g.m3,g.m6,g.y1];
        for(var i=0;i<7;i++) {
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

    var colMap = [null,null,'cnt','ytd','d1','w1','m1','m3','m6','y1'];
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
        stocksBySec[sec].push({name:r[4]||'',ticker:r[3]||'',cur:r[1]||'',mcap:mcapStr,mcapVal:mcapVal,
            ytd:r[7]||'',d1:r[8]||'',w1:r[9]||'',m1:r[10]||'',m3:r[11]||'',m6:r[12]||'',y1:r[13]||''});
    });
    for(var k in stocksBySec) stocksBySec[k].sort(function(a,b){return b.mcapVal-a.mcapVal;});

    var secHeaders = ['#','섹터','종목수','YTD','1D','1W','1M','3M','6M','1Y'];
    var html = '<table style="width:100%;table-layout:fixed;border-collapse:collapse"><thead><tr>';
    secHeaders.forEach(function(h,i) {
        var bg = i===3?' style="background:#f3f0ff;cursor:pointer"':' style="cursor:pointer"';
        html += '<th'+bg+' onclick="sortSector('+i+')">' + h + (_secSortCol===i ? (_secSortAsc?' ▲':' ▼') : '') + '</th>';
    });
    html += '</tr></thead><tbody>';
    secs.forEach(function(sec,idx) {
        var g = agg[sec];
        var vals = [wavg(g.ytd),wavg(g.d1),wavg(g.w1),wavg(g.m1),wavg(g.m3),wavg(g.m6),wavg(g.y1)];
        html += '<tr style="cursor:pointer" onclick="toggleSec('+idx+')">';
        html += '<td>' + (idx+1) + '</td><td style="font-weight:600">' + sec + '</td><td>' + g.cnt + '</td>';
        vals.forEach(function(v,i) {
            var bg = i===0?' style="background:#f3f0ff"':'';
            html += '<td class="'+cls(v)+'"'+bg+'>' + fv(v) + '</td>';
        });
        html += '</tr>';
        // 하위 종목 행 (숨김)
        var stocks = stocksBySec[sec] || [];
        stocks.forEach(function(s) {
            var tk = s.ticker.indexOf(':')>=0 ? s.ticker.split(':').pop() : s.ticker;
            var label = s.cur==='KRW' ? s.name : tk;
            function sc(v){if(!v)return'-';var n=parseFloat(String(v).replace(/%/g,'').replace(/,/g,''));if(isNaN(n))return v;return(n>0?'<span class="positive">+':'<span class="negative">')+Math.round(n)+'%</span>';}
            html += '<tr class="sec-detail sec-'+idx+'" style="display:none;background:#f0f0f0;font-size:14px">';
            html += '<td></td><td colspan="2" style="padding-left:96px;text-align:left">- '+label+'</td>';
            html += '<td style="background:#f3f0ff">'+sc(s.ytd)+'</td><td>'+sc(s.d1)+'</td><td>'+sc(s.w1)+'</td><td>'+sc(s.m1)+'</td><td>'+sc(s.m3)+'</td><td>'+sc(s.m6)+'</td><td>'+sc(s.y1)+'</td>';
            html += '</tr>';
        });
    });
    html += '</tbody></table>';

    document.getElementById('sectorContent').innerHTML = html;
}
</script>
</body>
</html>"""

    with open('universe.html', 'w', encoding='utf-8') as f:
        f.write(universe_page.replace('__UNIVERSE_UPDATED__', now))
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
    <link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=Noto+Sans+KR:wght@400;500;700&display=swap' rel='stylesheet'>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>Chart.defaults.font.family = "'Inter', 'Noto Sans KR', sans-serif";</script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Inter', 'Noto Sans KR', sans-serif; background: #f8f9fa; color: #333; }}
        header {{ background: #fff; padding: 24px; text-align: center; border-bottom: 1px solid #eee; }}
        header h1 {{ font-size: 1.8rem; color: #0369a1; }}
        .nav-group {{ margin-top: 10px; }}
        .nav-button {{ display: inline-block; padding: 6px 16px; border-radius: 6px; text-decoration: none; color: #fff; font-size: 0.85rem; font-weight: 600; background: #333; }}
        .subtitle {{ color: #888; font-size: 0.85rem; margin-top: 4px; }}
        .content {{ padding: 24px; max-width: 1200px; margin: 0 auto; }}
        .section {{ background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
        .section h2 {{ font-size: 1.1rem; color: #333; margin-bottom: 16px; }}
        .date-bar {{ display: flex; align-items: center; gap: 8px; margin-bottom: 16px; font-size: 13px; flex-wrap: wrap; }}
        .date-bar input {{ font-family: inherit; font-size: 13px; padding: 4px 8px; border: 1px solid #d1d5db; border-radius: 6px; background: #f9fafb; color: #222; width: 110px; text-align: center; }}
        .date-bar span {{ color: #888; }}
        .date-bar label {{ color: #555; font-weight: 600; }}
        .stats-row {{ display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }}
        .stat-card {{ background: #fff; border-radius: 10px; padding: 16px 20px; flex: 1; min-width: 160px; border-left: 4px solid #0369a1; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
        .stat-card .label {{ font-size: 0.8rem; color: #888; margin-bottom: 4px; }}
        .stat-card .value {{ font-size: 1.3rem; font-weight: 700; color: #333; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
        thead {{ background: #e9ecef; }}
        th {{ padding: 10px 12px; text-align: center; font-weight: 600; color: #000; border-bottom: 2px solid #000; }}
        td {{ padding: 9px 12px; border-bottom: 1px solid #dee2e6; }}
        td.name {{ text-align: left; max-width: 400px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
        td.rank {{ text-align: center; font-weight: 600; }}
        tbody tr:hover {{ background: #f5f5f5; }}
        footer {{ text-align: center; padding: 24px; color: #999; font-size: 0.8rem; }}
    </style>
</head>
<body>
<header style="position:relative;">
    <h1>SEIBro US Settlement TOP 50</h1>
    <div class="subtitle">Overseas Securities Buy Settlement - US Market</div>
    <a href="index.html" style="position:absolute;top:20px;right:24px;padding:6px 16px;background:#e0e0e0;color:#333;text-decoration:none;border-radius:8px;font-size:0.85rem;font-weight:600;">🏠 Home</a>
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
                borderColor: '#0369a1',
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

    featured_page = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Featured</title>
    <link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=Noto+Sans+KR:wght@400;500;700&display=swap' rel='stylesheet'>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Inter', 'Noto Sans KR', sans-serif; background: #f8f9fa; color: #333; }}
        header {{ background: #fff; padding: 24px; text-align: center; border-bottom: 1px solid #eee; position: relative; }}
        header h1 {{ font-size: 1.8rem; color: #333; }}
        .subtitle {{ color: #888; font-size: 0.85rem; margin-top: 4px; }}
        .content {{ padding: 24px; max-width: 1400px; margin: 0 auto; }}
        .section {{ background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
        .section h2 {{ font-size: 1.1rem; color: #333; margin-bottom: 16px; }}
        .date-bar {{ display: flex; align-items: center; gap: 8px; margin-bottom: 20px; font-size: 13px; flex-wrap: wrap; }}
        .date-bar input {{ font-family: inherit; font-size: 13px; padding: 4px 8px; border: 1px solid #d1d5db; border-radius: 6px; background: #f9fafb; color: #222; width: 110px; text-align: center; }}
        .date-bar label {{ color: #555; font-weight: 600; }}
        .tables {{ display: flex; gap: 24px; flex-wrap: wrap; }}
        .tables > div {{ flex: 1; min-width: 500px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
        thead {{ background: #2E7D32; }}
        th {{ padding: 8px 6px; text-align: center; font-weight: 600; color: #fff; font-size: 0.78rem; border: 1px solid #1B5E20; }}
        td {{ padding: 6px 6px; border: 1px solid #ddd; }}
        td.c {{ text-align: center; font-variant-numeric: tabular-nums; }}
        tbody tr:nth-child(even) {{ background: #E8F5E9; }}
        tbody tr:nth-child(odd) {{ background: #fff; }}
        tbody tr:hover {{ background: #C8E6C9; }}
        .section h2 {{ background: #E67E22; color: #fff; padding: 8px 12px; border-radius: 4px; font-size: 0.95rem; }}
        .pos {{ color: #cc0000; font-weight: 600; }}
        .neg {{ color: #0055cc; font-weight: 600; }}
        footer {{ text-align: center; padding: 24px; color: #999; font-size: 0.8rem; }}
    </style>
</head>
<body>
<header style="position:relative;">
    <h1>Featured</h1>
    <div class="subtitle">Daily Market Highlights</div>
    <a href="index.html" style="position:absolute;top:20px;right:24px;padding:6px 16px;background:#e0e0e0;color:#333;text-decoration:none;border-radius:8px;font-size:0.85rem;font-weight:600;">🏠 Home</a>
</header>
<div class="content">
    <div class="section">
        <div class="date-bar">
            <label>기간</label>
            <input type="text" id="fStartDate" value="{featured_last}" placeholder="YYYY-MM-DD" oninput="tryRefresh()" onchange="refresh()">
            <span>~</span>
            <input type="text" id="fEndDate" value="{featured_last}" placeholder="YYYY-MM-DD" oninput="tryRefresh()" onchange="refresh()">
            <span id="dateLabel" style="color:#888;font-size:12px;"></span>
        </div>
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
<footer>Data source: KRX OpenAPI</footer>
<script>
var raw = {featured_json};
var wics = {wics_json};

function sec(code) {{
    return wics[code] || '';
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
        f.write(featured_page)
    print("Featured page generated: featured.html")

    # ── ETF page ──
    generate_etf_html()


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
    daily = get_all_etf_daily()
    constituents = get_constituents_for_date(latest)

    # JSON 데이터 준비
    import json
    daily_json = json.dumps([
        {'d': r['date'], 'code': r['etf_code'], 'name': r['etf_name'],
         'close': r['close_price'], 'nav': r['nav'], 'vol': r['volume'],
         'aum': r['aum'], 'mcap': r['market_cap']}
        for r in daily
    ], ensure_ascii=False)

    const_json = json.dumps(constituents, ensure_ascii=False)
    dates_json = json.dumps(dates)

    page = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETF Dashboard</title>
<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=Noto+Sans+KR:wght@400;500;700&display=swap' rel='stylesheet'>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Inter', 'Noto Sans KR', sans-serif; background: #f8f9fa; color: #333; }}
header {{ background: #fff; padding: 24px; text-align: center; border-bottom: 1px solid #eee; position: relative; }}
header h1 {{ font-size: 1.6rem; color: #333; }}
.home-btn {{ position: absolute; top: 20px; right: 24px; padding: 6px 16px; background: #e0e0e0; color: #333; text-decoration: none; border-radius: 8px; font-size: 0.85rem; font-weight: 600; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
.controls {{ display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 16px; }}
.controls input {{ padding: 8px 14px; border: 2px solid #ddd; border-radius: 8px; font-size: 0.9rem; font-family: inherit; outline: none; width: 300px; }}
.controls input:focus {{ border-color: #6366f1; }}
.controls select {{ padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 0.85rem; background: #fff; font-family: inherit; }}
.controls label {{ font-size: 0.85rem; color: #666; }}
.section {{ background: #fff; border-radius: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); margin-bottom: 20px; overflow: hidden; }}
.section-header {{ padding: 14px 20px; font-size: 1rem; font-weight: 700; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }}
.section-header .count {{ font-size: 0.8rem; color: #888; font-weight: 400; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
thead {{ background: #4338ca; }}
th {{ padding: 10px 8px; text-align: center; font-weight: 600; color: #fff; cursor: pointer; white-space: nowrap; }}
th:hover {{ background: #3730a3; }}
th .arr {{ font-size: 0.6rem; margin-left: 2px; }}
td {{ padding: 8px 8px; border-bottom: 1px solid #f0f0f0; text-align: center; }}
tbody tr:hover {{ background: #f5f3ff; }}
tbody tr.etf-row {{ cursor: pointer; }}
tbody tr.etf-row:hover {{ background: #ede9fe; }}
.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.pos {{ color: #cc0000; font-weight: 600; }}
.neg {{ color: #0055cc; font-weight: 600; }}
.etf-name {{ text-align: left; font-weight: 600; }}
.constituents-row {{ background: #faf5ff; }}
.constituents-row td {{ padding: 0; }}
.const-table {{ width: 100%; font-size: 0.78rem; }}
.const-table th {{ background: #e9e5f5; color: #333; padding: 6px 8px; font-size: 0.75rem; }}
.const-table td {{ padding: 5px 8px; border-bottom: 1px solid #ede9fe; }}
.const-table tbody tr:hover {{ background: #e9e5f5; }}
.search-results {{ display: none; }}
.search-results.active {{ display: block; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }}
.updated {{ text-align: center; font-size: 0.75rem; color: #aaa; margin-top: 10px; }}
</style>
</head>
<body>
<header>
    <h1>🏛️ ETF Dashboard</h1>
    <a href="index.html" class="home-btn">🏠 Home</a>
</header>

<div class="container">
    <div class="controls">
        <input type="text" id="searchInput" placeholder="종목명 검색 (예: ISC, 삼성전자)" oninput="onSearch()">
        <select id="dateSelect" onchange="onDateChange()"></select>
        <label><input type="checkbox" id="showAll" onchange="render()"> 전체 표시</label>
    </div>

    <div id="searchResults" class="section search-results">
        <div class="section-header">🔍 종목 검색 결과 <span class="count" id="searchCount"></span></div>
        <div style="overflow-x:auto"><table>
            <thead><tr><th>ETF</th><th>비중(%)</th><th>AUM</th></tr></thead>
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

<script>
var allDaily = {daily_json};
var allConst = {const_json};
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
        h += '<td class="etf-name">' + (isOpen ? '▼ ' : '▶ ') + r.name + '</td>';
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

    // Sort by weight desc
    matches.sort(function(a, b) {{ return (b.weight || 0) - (a.weight || 0); }});

    var h = '';
    matches.forEach(function(m) {{
        h += '<tr><td style="text-align:left">' + m.etfName + '</td>';
        h += '<td class="num">' + (m.weight ? m.weight.toFixed(2) : '-') + '</td>';
        h += '<td class="num">' + fmtAum(m.aum) + '</td></tr>';
    }});
    if (!h) h = '<tr><td colspan="3" style="padding:20px;color:#aaa;text-align:center">결과 없음</td></tr>';
    document.getElementById('searchBody').innerHTML = h;
    document.getElementById('searchCount').textContent = matches.length + '건';
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
