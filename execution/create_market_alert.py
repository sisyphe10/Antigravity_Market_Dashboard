import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

KST = timezone(timedelta(hours=9))
OUTPUT_FILE = 'market_alert.html'

CATEGORY_META = {
    '투자주의': {
        'menu_index': 1,
        'forward': 'invstcautnisu_sub',
        'color': '#b45309',
        'bg': '#fffbeb',
        'border': '#f59e0b',
        'badge_bg': '#fef3c7',
        'badge_color': '#92400e',
        'icon': '⚠️',
        'columns': ['종목명', '유형', '공시일', '지정일'],
        'has_release': False,
    },
    '투자경고': {
        'menu_index': 2,
        'forward': 'invstwarnisu_sub',
        'color': '#c2410c',
        'bg': '#fff7ed',
        'border': '#f97316',
        'badge_bg': '#ffedd5',
        'badge_color': '#9a3412',
        'icon': '🚨',
        'columns': ['종목명', '공시일', '지정일', '경과일'],
        'has_release': True,
    },
    '투자위험': {
        'menu_index': 3,
        'forward': 'invstriskisu_sub',
        'color': '#b91c1c',
        'bg': '#fff1f2',
        'border': '#ef4444',
        'badge_bg': '#fee2e2',
        'badge_color': '#991b1b',
        'icon': '🛑',
        'columns': ['종목명', '공시일', '지정일', '경과일'],
        'has_release': True,
    },
}

MARKET_BADGE = {
    '유가증권': {'label': 'KOSPI', 'bg': '#dbeafe', 'color': '#1e40af'},
    '코스닥': {'label': 'KOSDAQ', 'bg': '#dcfce7', 'color': '#166534'},
    '코넥스': {'label': 'KONEX', 'bg': '#f3e8ff', 'color': '#6b21a8'},
}

WARN_TYPE_STYLE = {
    '투자경고 지정예고': {'bg': '#fef3c7', 'color': '#92400e', 'bold': True},
    '투자위험 지정예고': {'bg': '#fee2e2', 'color': '#991b1b', 'bold': True},
}


def get_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    })
    session.get(
        'https://kind.krx.co.kr/investwarn/investattentwarnrisky.do?method=investattentwarnriskyMain',
        timeout=15
    )
    return session


def fetch_category(session, category_name, start_date, end_date):
    meta = CATEGORY_META[category_name]
    data = {
        'method': 'investattentwarnriskySub',
        'forward': meta['forward'],
        'menuIndex': str(meta['menu_index']),
        'currentPageSize': '100',
        'pageIndex': '1',
        'orderMode': '3' if meta['has_release'] else '4',
        'orderStat': 'D',
        'marketType': '',
        'startDate': start_date,
        'endDate': end_date,
        'searchCorpName': '',
        'repIsuSrtCd': '',
        'searchCodeType': '',
    }
    try:
        resp = session.post(
            'https://kind.krx.co.kr/investwarn/investattentwarnrisky.do',
            data=data,
            headers={
                'Referer': 'https://kind.krx.co.kr/investwarn/investattentwarnrisky.do?method=investattentwarnriskyMain'
            },
            timeout=15
        )
        resp.encoding = 'utf-8'
        return BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        print(f"  Error fetching {category_name}: {e}")
        return None


def parse_stocks(soup, category_name):
    if not soup:
        return []
    table = soup.find('table', class_='list')
    if not table:
        return []

    meta = CATEGORY_META[category_name]
    rows = table.find_all('tr')
    results = []

    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 3:
            continue

        # 종목명 + 시장구분
        name_td = cols[1]
        name = name_td.get_text(strip=True)
        img = name_td.find('img')
        market_raw = img.get('alt', '') if img else ''
        market = MARKET_BADGE.get(market_raw, {'label': market_raw, 'bg': '#e5e7eb', 'color': '#374151'})

        # 종목코드
        a_tag = name_td.find('a', id='companysum')
        code = ''
        if a_tag:
            oc = a_tag.get('onclick', '')
            m = re.search(r"'(\d+)'", oc)
            if m:
                code = m.group(1).zfill(6)

        # 날짜 컬럼 파싱
        date_cols = [cols[i].get_text(strip=True) for i in range(2, len(cols))]

        if meta['has_release']:
            # 투자경고/위험: [공시일, 지정일, 해제일]
            if len(date_cols) < 3:
                continue
            notice_date = date_cols[0]
            designation_date = date_cols[1]
            release_date = date_cols[2]

            if release_date != '-':
                continue  # 이미 해제됨

            # 경과일 계산
            try:
                d = datetime.strptime(designation_date, '%Y-%m-%d')
                elapsed = (datetime.now(tz=KST).replace(tzinfo=None) - d).days
            except Exception:
                elapsed = 0

            results.append({
                'name': name,
                'market': market,
                'market_raw': market_raw,
                'code': code,
                'notice_date': notice_date,
                'designation_date': designation_date,
                'elapsed': elapsed,
                'warn_type': None,
            })
        else:
            # 투자주의: [유형, 공시일, 지정일]
            if len(date_cols) < 3:
                continue
            warn_type = date_cols[0]
            notice_date = date_cols[1]
            designation_date = date_cols[2]

            results.append({
                'name': name,
                'market': market,
                'market_raw': market_raw,
                'code': code,
                'notice_date': notice_date,
                'designation_date': designation_date,
                'elapsed': 0,
                'warn_type': warn_type,
            })

    return results


def market_badge_html(market_info):
    return (f'<span class="mkt-badge" '
            f'style="background:{market_info["bg"]};color:{market_info["color"]}">'
            f'{market_info["label"]}</span>')


def render_warn_type(warn_type):
    if not warn_type:
        return ''
    style = WARN_TYPE_STYLE.get(warn_type, {})
    bg = style.get('bg', '#f3f4f6')
    color = style.get('color', '#374151')
    bold = 'font-weight:700;' if style.get('bold') else ''
    return f'<span class="type-badge" style="background:{bg};color:{color};{bold}">{warn_type}</span>'


def render_table(stocks, category_name):
    meta = CATEGORY_META[category_name]

    if not stocks:
        return '<div class="empty-msg">현재 지정 종목 없음</div>'

    if meta['has_release']:
        rows_html = ''
        for s in stocks:
            elapsed_cls = 'elapsed elapsed-long' if s['elapsed'] >= 7 else 'elapsed'
            elapsed_html = f'<span class="{elapsed_cls}">{s["elapsed"]}일</span>'
            rows_html += f"""
            <tr>
                <td>{s['name']}<br>{market_badge_html(s['market'])}</td>
                <td class="center">{s['notice_date']}</td>
                <td class="center desig-date">{s['designation_date']}</td>
                <td class="center">{elapsed_html}</td>
            </tr>"""

        return f"""
        <table class="alert-table">
            <thead>
                <tr>
                    <th>종목명</th>
                    <th>공시일</th>
                    <th>지정일</th>
                    <th>경과일</th>
                </tr>
            </thead>
            <tbody>{rows_html}
            </tbody>
        </table>"""
    else:
        # 투자주의: 지정일 기준 최근 거래일만 (오늘 또는 직전 거래일)
        rows_html = ''
        for s in stocks:
            type_html = render_warn_type(s['warn_type'])
            rows_html += f"""
            <tr>
                <td>{s['name']}<br>{market_badge_html(s['market'])}</td>
                <td>{type_html}</td>
                <td class="center">{s['notice_date']}</td>
                <td class="center desig-date">{s['designation_date']}</td>
            </tr>"""

        return f"""
        <table class="alert-table">
            <thead>
                <tr>
                    <th>종목명</th>
                    <th>유형</th>
                    <th>공시일</th>
                    <th>지정일</th>
                </tr>
            </thead>
            <tbody>{rows_html}
            </tbody>
        </table>"""


def generate_html(stocks_주의, stocks_경고, stocks_위험):
    now = datetime.now(tz=KST).strftime('%Y-%m-%d %H:%M:%S KST')

    def section_html(category_name, stocks):
        meta = CATEGORY_META[category_name]
        count = len(stocks)
        table = render_table(stocks, category_name)
        return f"""
    <section class="alert-section" style="border-left:4px solid {meta['border']}">
        <div class="section-header" style="background:{meta['bg']};border-bottom:1px solid {meta['border']}">
            <div class="section-title" style="color:{meta['color']}">
                {meta['icon']} {category_name}
                <span class="count-badge" style="background:{meta['badge_bg']};color:{meta['badge_color']}">{count}종목</span>
            </div>
            <div class="section-desc">{get_desc(category_name)}</div>
        </div>
        <div class="section-body">
            {table}
        </div>
    </section>"""

    def get_desc(name):
        descs = {
            '투자주의': '금일 지정 종목 · 5영업일 후 자동 해제 · 거래 제약 없음',
            '투자경고': '신용융자 금지 · 위탁증거금 100% · 대용증권 불인정',
            '투자위험': '신용거래 전면 금지 · 지정일 1일 매매정지 · 위탁증거금 100%',
        }
        return descs.get(name, '')

    s주의 = section_html('투자주의', stocks_주의)
    s경고 = section_html('투자경고', stocks_경고)
    s위험 = section_html('투자위험', stocks_위험)

    total = len(stocks_주의) + len(stocks_경고) + len(stocks_위험)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>투자유의종목 현황</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            font-family: 'Segoe UI', Roboto, 'Malgun Gothic', sans-serif;
            background: #f8f9fa;
            color: #1f2937;
            padding: 24px;
            min-height: 100vh;
        }}

        header {{
            background: #000;
            border-radius: 12px;
            padding: 20px 28px;
            margin-bottom: 28px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 12px;
        }}

        .header-left h1 {{
            color: #fff;
            font-size: 1.8rem;
            font-weight: 700;
        }}

        .header-left .subtitle {{
            color: #9ca3af;
            font-size: 0.85rem;
            margin-top: 4px;
        }}

        .header-right {{
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 8px;
        }}

        .last-updated {{
            color: #6b7280;
            font-size: 0.82rem;
            font-style: italic;
        }}

        .back-btn {{
            display: inline-block;
            padding: 7px 18px;
            background: #2d7a3a;
            color: #fff;
            text-decoration: none;
            border-radius: 8px;
            font-size: 0.88rem;
            font-weight: 600;
        }}

        .back-btn:hover {{ background: #357abd; }}

        /* 요약 카드 */
        .summary-bar {{
            display: flex;
            gap: 16px;
            margin-bottom: 28px;
            flex-wrap: wrap;
        }}

        .summary-card {{
            flex: 1;
            min-width: 160px;
            border-radius: 10px;
            padding: 16px 20px;
            display: flex;
            align-items: center;
            gap: 14px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }}

        .summary-icon {{ font-size: 2rem; }}

        .summary-label {{
            font-size: 0.82rem;
            color: #6b7280;
            margin-bottom: 2px;
        }}

        .summary-count {{
            font-size: 1.8rem;
            font-weight: 700;
            line-height: 1;
        }}

        /* 섹션 */
        .alert-section {{
            background: #fff;
            border-radius: 10px;
            margin-bottom: 24px;
            overflow: hidden;
            box-shadow: 0 1px 4px rgba(0,0,0,0.07);
        }}

        .section-header {{
            padding: 16px 20px;
        }}

        .section-title {{
            font-size: 1.15rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .count-badge {{
            font-size: 0.78rem;
            padding: 2px 10px;
            border-radius: 12px;
            font-weight: 600;
        }}

        .section-desc {{
            font-size: 0.78rem;
            color: #6b7280;
            margin-top: 4px;
        }}

        .section-body {{
            padding: 0 20px 20px;
        }}

        /* 테이블 */
        .alert-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.88rem;
            margin-top: 16px;
        }}

        .alert-table thead tr {{
            background: #f9fafb;
            border-bottom: 2px solid #e5e7eb;
        }}

        .alert-table th {{
            padding: 10px 12px;
            text-align: left;
            font-size: 0.78rem;
            font-weight: 600;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}

        .alert-table th.center,
        .alert-table td.center {{ text-align: center; }}

        .alert-table tbody tr {{
            border-bottom: 1px solid #f3f4f6;
            transition: background 0.15s;
        }}

        .alert-table tbody tr:hover {{ background: #fafafa; }}

        .alert-table td {{
            padding: 10px 12px;
            vertical-align: middle;
            line-height: 1.4;
        }}

        .mkt-badge {{
            display: inline-block;
            font-size: 0.7rem;
            padding: 1px 7px;
            border-radius: 10px;
            font-weight: 600;
            margin-top: 3px;
        }}

        .type-badge {{
            display: inline-block;
            font-size: 0.75rem;
            padding: 2px 8px;
            border-radius: 6px;
        }}

        .desig-date {{
            font-weight: 600;
        }}

        .elapsed {{
            display: inline-block;
            padding: 2px 8px;
            background: #f3f4f6;
            border-radius: 10px;
            font-size: 0.82rem;
            color: #374151;
        }}

        .elapsed-long {{
            background: #fee2e2;
            color: #991b1b;
        }}

        .empty-msg {{
            text-align: center;
            padding: 24px;
            color: #9ca3af;
            font-size: 0.9rem;
        }}

        footer {{
            text-align: center;
            padding: 20px;
            color: #9ca3af;
            font-size: 0.78rem;
        }}

        footer a {{ color: #6b7280; }}
    </style>
</head>
<body>
    <header>
        <div class="header-left">
            <h1>🚦 투자유의종목 현황</h1>
            <div class="subtitle">한국거래소(KRX) 시장경보제도 · 투자주의 / 투자경고 / 투자위험</div>
        </div>
        <div class="header-right">
            <div class="last-updated">Updated: {now}</div>
            <a href="index.html" class="back-btn">← Dashboard</a>
        </div>
    </header>

    <div class="summary-bar">
        <div class="summary-card" style="background:#fffbeb;border:1px solid #fde68a">
            <div class="summary-icon">⚠️</div>
            <div>
                <div class="summary-label">투자주의</div>
                <div class="summary-count" style="color:#b45309">{len(stocks_주의)}</div>
            </div>
        </div>
        <div class="summary-card" style="background:#fff7ed;border:1px solid #fed7aa">
            <div class="summary-icon">🚨</div>
            <div>
                <div class="summary-label">투자경고</div>
                <div class="summary-count" style="color:#c2410c">{len(stocks_경고)}</div>
            </div>
        </div>
        <div class="summary-card" style="background:#fff1f2;border:1px solid #fecdd3">
            <div class="summary-icon">🛑</div>
            <div>
                <div class="summary-label">투자위험</div>
                <div class="summary-count" style="color:#b91c1c">{len(stocks_위험)}</div>
            </div>
        </div>
        <div class="summary-card" style="background:#f0fdf4;border:1px solid #bbf7d0">
            <div class="summary-icon">📋</div>
            <div>
                <div class="summary-label">전체</div>
                <div class="summary-count" style="color:#166534">{total}</div>
            </div>
        </div>
    </div>

    {s주의}
    {s경고}
    {s위험}

    <footer>
        데이터 출처: <a href="https://kind.krx.co.kr" target="_blank">한국거래소 KIND</a> &nbsp;|&nbsp;
        투자주의는 금일 지정 종목, 투자경고/위험은 현재 지정 중인 종목 기준 &nbsp;|&nbsp;
        본 자료는 참고용이며 투자 조언이 아닙니다
    </footer>
</body>
</html>"""


def create_market_alert():
    print("📡 KIND 투자유의종목 데이터 수집 중...")
    now_kst = datetime.now(tz=KST)
    today = now_kst.strftime('%Y-%m-%d')
    # 투자주의: 오늘만 (금일 지정 종목)
    # 투자경고/위험: 최근 90일 범위에서 현재 해제 안 된 것
    start_90 = (now_kst - timedelta(days=90)).strftime('%Y-%m-%d')

    session = get_session()

    # ── 투자주의 ──
    print("  투자주의 조회 중...")
    soup_주의 = fetch_category(session, '투자주의', today, today)
    stocks_주의 = parse_stocks(soup_주의, '투자주의')
    print(f"    → {len(stocks_주의)}건 (금일 지정)")

    # ── 투자경고 ──
    print("  투자경고 조회 중...")
    soup_경고 = fetch_category(session, '투자경고', start_90, today)
    stocks_경고 = parse_stocks(soup_경고, '투자경고')
    print(f"    → {len(stocks_경고)}건 (현재 지정 중)")

    # ── 투자위험 ──
    print("  투자위험 조회 중...")
    soup_위험 = fetch_category(session, '투자위험', start_90, today)
    stocks_위험 = parse_stocks(soup_위험, '투자위험')
    print(f"    → {len(stocks_위험)}건 (현재 지정 중)")

    print("\n📝 HTML 생성 중...")
    html = generate_html(stocks_주의, stocks_경고, stocks_위험)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✅ 완료: {OUTPUT_FILE}")
    print(f"   투자주의 {len(stocks_주의)}건 / 투자경고 {len(stocks_경고)}건 / 투자위험 {len(stocks_위험)}건")


if __name__ == '__main__':
    create_market_alert()
