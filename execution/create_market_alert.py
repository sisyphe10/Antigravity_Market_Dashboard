import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import sys
import re
import FinanceDataReader as fdr

sys.stdout.reconfigure(encoding='utf-8')

KST = timezone(timedelta(hours=9))
OUTPUT_FILE = 'market_alert.html'

CATEGORY_META = {
    '투자주의': {
        'menu_index': 1,
        'forward': 'invstcautnisu_sub',
        'color': '#b45309',
        'border': '#f59e0b',
        'icon': '⚠️',
        'has_release': False,
    },
    '투자경고': {
        'menu_index': 2,
        'forward': 'invstwarnisu_sub',
        'color': '#c2410c',
        'border': '#f97316',
        'icon': '🚨',
        'has_release': True,
    },
    '투자위험': {
        'menu_index': 3,
        'forward': 'invstriskisu_sub',
        'color': '#b91c1c',
        'border': '#ef4444',
        'icon': '🛑',
        'has_release': True,
    },
}

MARKET_LABEL = {
    '유가증권': 'KOSPI',
    '코스닥': 'KOSDAQ',
    '코넥스': 'KONEX',
}


def get_session():
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
    session.get(
        'https://kind.krx.co.kr/investwarn/investattentwarnrisky.do?method=investattentwarnriskyMain',
        timeout=15
    )
    return session


def load_marcap_dict():
    """KRX 종목 시가총액 딕셔너리 로드 (이름 → 억원)"""
    try:
        print("  KRX 시가총액 데이터 로드 중...")
        krx = fdr.StockListing('KRX')
        marcap = {}
        for _, row in krx.iterrows():
            name = str(row.get('Name', '')).strip()
            cap = row.get('Marcap', 0)
            if name and cap:
                marcap[name] = int(cap) // 100_000_000  # 억원
        print(f"  → {len(marcap)}개 종목 로드됨")
        return marcap
    except Exception as e:
        print(f"  Warning: 시가총액 로드 실패: {e}")
        return {}


def normalize_name(name):
    return re.sub(r'[\s\(\)㈜]', '', name)


def lookup_marcap(name, marcap_dict):
    if name in marcap_dict:
        return marcap_dict[name]
    norm = normalize_name(name)
    for k, v in marcap_dict.items():
        if normalize_name(k) == norm:
            return v
    return None


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
            headers={'Referer': 'https://kind.krx.co.kr/investwarn/investattentwarnrisky.do?method=investattentwarnriskyMain'},
            timeout=15
        )
        resp.encoding = 'utf-8'
        return BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        print(f"  Error fetching {category_name}: {e}")
        return None


def parse_stocks(soup, category_name, marcap_dict):
    if not soup:
        return []
    table = soup.find('table', class_='list')
    if not table:
        return []

    meta = CATEGORY_META[category_name]
    rows = table.find_all('tr')
    now_naive = datetime.now(tz=KST).replace(tzinfo=None)
    results = []

    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 3:
            continue

        name_td = cols[1]
        name = name_td.get_text(strip=True)
        img = name_td.find('img')
        market_raw = img.get('alt', '') if img else ''
        market = MARKET_LABEL.get(market_raw, market_raw)
        marcap = lookup_marcap(name, marcap_dict)

        date_cols = [cols[i].get_text(strip=True) for i in range(2, len(cols))]

        if meta['has_release']:
            if len(date_cols) < 3:
                continue
            notice_date = date_cols[0]
            designation_date = date_cols[1]
            release_date = date_cols[2]
            if release_date != '-':
                continue
            warn_type = '-'
        else:
            if len(date_cols) < 3:
                continue
            warn_type = date_cols[0]
            notice_date = date_cols[1]
            designation_date = date_cols[2]

        try:
            d = datetime.strptime(designation_date, '%Y-%m-%d')
            elapsed = (now_naive - d).days
        except Exception:
            elapsed = 0

        results.append({
            'name': name,
            'market': market,
            'marcap': marcap,
            'notice_date': notice_date,
            'designation_date': designation_date,
            'elapsed': elapsed,
            'warn_type': warn_type,
        })

    return results


def fmt_marcap(val):
    if val is None:
        return '-'
    if val >= 10000:
        return f'{val / 10000:.1f}조'
    return f'{val:,}억'


def render_table(stocks):
    if not stocks:
        return '<p style="color:#9ca3af;padding:12px 0;font-size:0.85rem">현재 지정 종목 없음</p>'

    rows_html = ''
    for s in stocks:
        elapsed_str = f"{s['elapsed']}일" if s['elapsed'] >= 0 else '-'
        rows_html += f"""
            <tr>
                <td>{s['name']}</td>
                <td>{s['market']}</td>
                <td class="num">{fmt_marcap(s['marcap'])}</td>
                <td class="center">{s['notice_date']}</td>
                <td class="center">{s['designation_date']}</td>
                <td class="center">{elapsed_str}</td>
                <td>{s['warn_type']}</td>
            </tr>"""

    return f"""
        <table class="data-table">
            <thead>
                <tr>
                    <th>종목명</th>
                    <th>시장</th>
                    <th class="num">시가총액</th>
                    <th class="center">공시일</th>
                    <th class="center">지정일</th>
                    <th class="center">경과일</th>
                    <th>유형</th>
                </tr>
            </thead>
            <tbody>{rows_html}
            </tbody>
        </table>"""


def generate_html(stocks_주의, stocks_경고, stocks_위험):
    now = datetime.now(tz=KST).strftime('%Y-%m-%d %H:%M:%S KST')

    def section(category_name, stocks):
        meta = CATEGORY_META[category_name]
        count = len(stocks)
        return f"""
    <section class="section">
        <div class="section-header" style="border-left:4px solid {meta['border']}">
            <span class="section-title" style="color:{meta['color']}">{meta['icon']} {category_name}</span>
            <span class="section-count">{count}종목</span>
        </div>
        {render_table(stocks)}
    </section>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>투자유의종목 현황</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
            background: #f8f9fa;
            color: #1f2937;
            padding: 24px;
        }}

        header {{
            background: #000;
            border-radius: 10px;
            padding: 18px 24px;
            margin-bottom: 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 10px;
        }}

        header h1 {{ color: #fff; font-size: 1.5rem; font-weight: 700; }}

        .header-right {{
            display: flex;
            align-items: center;
            gap: 16px;
        }}

        .last-updated {{ color: #9ca3af; font-size: 0.8rem; }}

        .back-btn {{
            padding: 6px 16px;
            background: #2d7a3a;
            color: #fff;
            text-decoration: none;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 600;
        }}
        .back-btn:hover {{ background: #357abd; }}

        .section {{
            background: #fff;
            border-radius: 8px;
            margin-bottom: 20px;
            padding: 20px 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        }}

        .section-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding-left: 12px;
            margin-bottom: 14px;
        }}

        .section-title {{ font-size: 1rem; font-weight: 700; }}
        .section-count {{ font-size: 0.8rem; color: #6b7280; }}

        .data-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.86rem;
        }}

        .data-table th {{
            padding: 8px 10px;
            text-align: left;
            font-size: 0.76rem;
            font-weight: 600;
            color: #6b7280;
            border-bottom: 1px solid #e5e7eb;
            background: #f9fafb;
        }}

        .data-table th.num, .data-table td.num {{ text-align: right; }}
        .data-table th.center, .data-table td.center {{ text-align: center; }}

        .data-table td {{
            padding: 8px 10px;
            border-bottom: 1px solid #f3f4f6;
            color: #374151;
        }}

        .data-table tbody tr:last-child td {{ border-bottom: none; }}
        .data-table tbody tr:hover td {{ background: #f9fafb; }}

        footer {{
            text-align: center;
            padding: 16px;
            color: #9ca3af;
            font-size: 0.75rem;
        }}
        footer a {{ color: #9ca3af; }}
    </style>
</head>
<body>
    <header>
        <h1>🚦 투자유의종목 현황</h1>
        <div class="header-right">
            <span class="last-updated">Updated: {now}</span>
            <a href="index.html" class="back-btn">← Dashboard</a>
        </div>
    </header>

    {section('투자주의', stocks_주의)}
    {section('투자경고', stocks_경고)}
    {section('투자위험', stocks_위험)}

    <footer>
        출처: <a href="https://kind.krx.co.kr" target="_blank">한국거래소 KIND</a> &nbsp;|&nbsp;
        투자주의: 금일 지정 기준 &nbsp;|&nbsp; 투자경고/위험: 현재 지정 중 기준 &nbsp;|&nbsp;
        본 자료는 참고용이며 투자 조언이 아닙니다
    </footer>
</body>
</html>"""


def create_market_alert():
    print("📡 KIND 투자유의종목 데이터 수집 중...")
    now_kst = datetime.now(tz=KST)
    today = now_kst.strftime('%Y-%m-%d')
    start_90 = (now_kst - timedelta(days=90)).strftime('%Y-%m-%d')

    marcap_dict = load_marcap_dict()
    session = get_session()

    print("  투자주의 조회 중...")
    soup_주의 = fetch_category(session, '투자주의', today, today)
    stocks_주의 = parse_stocks(soup_주의, '투자주의', marcap_dict)
    print(f"    → {len(stocks_주의)}건")

    print("  투자경고 조회 중...")
    soup_경고 = fetch_category(session, '투자경고', start_90, today)
    stocks_경고 = parse_stocks(soup_경고, '투자경고', marcap_dict)
    print(f"    → {len(stocks_경고)}건")

    print("  투자위험 조회 중...")
    soup_위험 = fetch_category(session, '투자위험', start_90, today)
    stocks_위험 = parse_stocks(soup_위험, '투자위험', marcap_dict)
    print(f"    → {len(stocks_위험)}건")

    print("\n📝 HTML 생성 중...")
    html = generate_html(stocks_주의, stocks_경고, stocks_위험)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✅ 완료: {OUTPUT_FILE}")
    print(f"   투자주의 {len(stocks_주의)}건 / 투자경고 {len(stocks_경고)}건 / 투자위험 {len(stocks_위험)}건")


if __name__ == '__main__':
    create_market_alert()
