import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import re
import pandas as pd
import FinanceDataReader as fdr

sys.stdout.reconfigure(encoding='utf-8')

KST = timezone(timedelta(hours=9))
OUTPUT_FILE = 'market_alert.html'

# 해제 최소 영업일 기준
MIN_BDAYS = {'투자주의': 5, '투자경고': 10, '투자위험': 10}

CATEGORY_META = {
    '투자주의': {
        'menu_index': 1, 'forward': 'invstcautnisu_sub',
        'color': '#b45309', 'border': '#f59e0b', 'icon': '⚠️',
        'has_release': False,
    },
    '투자경고': {
        'menu_index': 2, 'forward': 'invstwarnisu_sub',
        'color': '#c2410c', 'border': '#f97316', 'icon': '🚨',
        'has_release': True,
    },
    '투자위험': {
        'menu_index': 3, 'forward': 'invstriskisu_sub',
        'color': '#b91c1c', 'border': '#ef4444', 'icon': '🛑',
        'has_release': True,
    },
}

MARKET_LABEL = {'유가증권': 'KOSPI', '코스닥': 'KOSDAQ', '코넥스': 'KONEX'}


# ──────────────────────────────────────────
# KRX 데이터 로드
# ──────────────────────────────────────────
def load_krx_data():
    """이름 → {marcap(억), code} 딕셔너리"""
    try:
        print("  KRX 종목 데이터 로드 중...")
        krx = fdr.StockListing('KRX')
        result = {}
        for _, row in krx.iterrows():
            name = str(row.get('Name', '')).strip()
            cap  = row.get('Marcap', 0) or 0
            code = str(row.get('Code', '')).strip()
            if name:
                result[name] = {
                    'marcap': int(cap) // 100_000_000,
                    'code': code,
                }
        print(f"  → {len(result)}개 종목")
        return result
    except Exception as e:
        print(f"  Warning: KRX 로드 실패: {e}")
        return {}


def normalize_name(name):
    return re.sub(r'[\s\(\)㈜]', '', name)


def lookup_krx(name, krx_data):
    """이름으로 {marcap, code} 반환"""
    if name in krx_data:
        return krx_data[name]
    norm = normalize_name(name)
    for k, v in krx_data.items():
        if normalize_name(k) == norm:
            return v
    return {'marcap': None, 'code': None}


# ──────────────────────────────────────────
# 주가 병렬 조회
# ──────────────────────────────────────────
def _fetch_one(code, start):
    try:
        df = fdr.DataReader(code, start=start)
        if df is not None and not df.empty:
            return code, df
    except Exception:
        pass
    return code, pd.DataFrame()


def fetch_all_prices(codes, days_back=35):
    """여러 종목 가격 병렬 조회 → {code: DataFrame}"""
    start = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    price_cache = {}
    unique_codes = [c for c in set(codes) if c]
    if not unique_codes:
        return price_cache
    print(f"  주가 데이터 병렬 조회 중 ({len(unique_codes)}종목)...")
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_fetch_one, c, start): c for c in unique_codes}
        for fut in as_completed(futures):
            code, df = fut.result()
            price_cache[code] = df
    ok = sum(1 for df in price_cache.values() if not df.empty)
    print(f"  → {ok}/{len(unique_codes)}개 성공")
    return price_cache


# ──────────────────────────────────────────
# 영업일 계산
# ──────────────────────────────────────────
def count_bdays(designation_date_str):
    """지정일 다음날부터 오늘까지 영업일 수 (한국 공휴일 미반영, 주말만 제외)"""
    try:
        d_start = pd.Timestamp(designation_date_str) + pd.offsets.BDay(1)
        d_end   = pd.Timestamp.now().normalize()
        if d_end < d_start:
            return 0
        return len(pd.bdate_range(d_start, d_end))
    except Exception:
        return 0


# ──────────────────────────────────────────
# 해제 조건 분석
# ──────────────────────────────────────────
def analyze_release(stock, price_df, category):
    """
    Returns:
        imminence  : str  (해제 임박 컬럼)
        rel_price  : str  (해제 가능 주가 컬럼)
    """
    desig_date = stock['designation_date']
    bd_elapsed = count_bdays(desig_date)
    min_bd     = MIN_BDAYS[category]
    remaining  = max(0, min_bd - bd_elapsed)

    # ── 기간 미달 ──
    if remaining > 0:
        return f'D-{remaining}일', '-'

    # ── 투자주의: 기간만 충족하면 해제 (주가 조건 없음) ──
    if category == '투자주의':
        return '해제 가능', '-'

    # ── 투자경고/위험: 주가 조건 체크 ──
    if price_df is None or price_df.empty or len(price_df) < 6:
        return '기간 경과', '-'

    closes = price_df['Close']
    current    = closes.iloc[-1]
    price_5d   = closes.iloc[-6]  if len(closes) >= 6  else None
    price_15d  = closes.iloc[-16] if len(closes) >= 16 else None
    max_15d    = closes.iloc[-15:].max()

    T1 = price_5d  * 1.6 if price_5d  is not None else None
    T2 = price_15d * 2.0 if price_15d is not None else None

    cond1 = (current > T1)        if T1 is not None else False
    cond2 = (current > T2)        if T2 is not None else False
    cond3 = (current >= max_15d)  # 15일 최고가

    # 3가지 모두 충족 → 해제 불가
    if cond1 and cond2 and cond3:
        # 가장 쉬운 목표: max(T1, T2) 이하로 내려가면 cond1 or cond2 깨짐
        thresholds = [t for t in [T1, T2] if t is not None]
        target = max(thresholds) if thresholds else None
        rel_price = f'{int(target):,}원 이하' if target else '-'
        return '조건 미충족', rel_price

    # 하나라도 불충족 → 해제 가능
    return '해제 가능', '조건 충족'


# ──────────────────────────────────────────
# KIND 데이터 수집
# ──────────────────────────────────────────
def get_session():
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
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
        'currentPageSize': '100', 'pageIndex': '1',
        'orderMode': '3' if meta['has_release'] else '4',
        'orderStat': 'D', 'marketType': '',
        'startDate': start_date, 'endDate': end_date,
        'searchCorpName': '', 'repIsuSrtCd': '', 'searchCodeType': '',
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
        print(f"  Error: {category_name} 조회 실패: {e}")
        return None


def parse_stocks(soup, category_name, krx_data):
    if not soup:
        return []
    table = soup.find('table', class_='list')
    if not table:
        return []

    meta     = CATEGORY_META[category_name]
    now_naive = datetime.now(tz=KST).replace(tzinfo=None)
    results  = []

    for row in table.find_all('tr'):
        cols = row.find_all('td')
        if len(cols) < 3:
            continue

        name_td    = cols[1]
        name       = name_td.get_text(strip=True)
        img        = name_td.find('img')
        market_raw = img.get('alt', '') if img else ''
        market     = MARKET_LABEL.get(market_raw, market_raw)

        krx_info   = lookup_krx(name, krx_data)
        marcap     = krx_info['marcap']
        code       = krx_info['code']

        date_cols  = [cols[i].get_text(strip=True) for i in range(2, len(cols))]

        if meta['has_release']:
            if len(date_cols) < 3:
                continue
            notice_date, designation_date, release_date = date_cols[0], date_cols[1], date_cols[2]
            if release_date != '-':
                continue
            warn_type = '-'
        else:
            if len(date_cols) < 3:
                continue
            warn_type, notice_date, designation_date = date_cols[0], date_cols[1], date_cols[2]

        try:
            elapsed = (now_naive - datetime.strptime(designation_date, '%Y-%m-%d')).days
        except Exception:
            elapsed = 0

        results.append({
            'name': name, 'market': market,
            'marcap': marcap, 'code': code,
            'notice_date': notice_date,
            'designation_date': designation_date,
            'elapsed': elapsed,
            'warn_type': warn_type,
        })

    return results


# ──────────────────────────────────────────
# HTML 렌더링
# ──────────────────────────────────────────
def fmt_marcap(val):
    if val is None:
        return '-'
    if val >= 10000:
        return f'{val / 10000:.1f}조'
    return f'{val:,}억'


IMMINENCE_STYLE = {
    '해제 가능':   'color:#166534;font-weight:600',
    '조건 미충족': 'color:#991b1b;font-weight:600',
    '기간 경과':   'color:#6b7280',
}


def render_table(stocks, category, price_cache):
    if not stocks:
        return '<p style="color:#9ca3af;padding:12px 0;font-size:0.85rem">현재 지정 종목 없음</p>'

    rows_html = ''
    for s in stocks:
        price_df  = price_cache.get(s['code']) if s['code'] else None
        imminence, rel_price = analyze_release(s, price_df, category)

        elapsed_str = f"{s['elapsed']}일"
        imm_style   = IMMINENCE_STYLE.get(imminence, 'color:#374151')
        # D-N일은 남은 일수에 따라 색상
        if imminence.startswith('D-'):
            n = int(imminence.replace('D-', '').replace('일', ''))
            imm_style = 'color:#d97706;font-weight:600' if n <= 2 else 'color:#374151'

        rows_html += f"""
            <tr>
                <td>{s['name']}</td>
                <td>{s['market']}</td>
                <td class="num">{fmt_marcap(s['marcap'])}</td>
                <td class="center">{s['notice_date']}</td>
                <td class="center">{s['designation_date']}</td>
                <td class="center">{elapsed_str}</td>
                <td>{s['warn_type']}</td>
                <td class="center" style="{imm_style}">{imminence}</td>
                <td class="center">{rel_price}</td>
            </tr>"""

    return f"""
        <div style="overflow-x:auto">
        <table class="data-table">
            <thead>
                <tr>
                    <th>종목명</th>
                    <th>시장</th>
                    <th class="num">시가총액</th>
                    <th class="center">공시일</th>
                    <th class="center">지정일 ▼</th>
                    <th class="center">경과일</th>
                    <th>유형</th>
                    <th class="center">해제 임박</th>
                    <th class="center">해제 가능 주가</th>
                </tr>
            </thead>
            <tbody>{rows_html}
            </tbody>
        </table>
        </div>"""


def generate_html(stocks_주의, stocks_경고, stocks_위험, price_cache):
    now = datetime.now(tz=KST).strftime('%Y-%m-%d %H:%M:%S KST')

    def section(category_name, stocks):
        meta  = CATEGORY_META[category_name]
        count = len(stocks)
        return f"""
    <section class="section">
        <div class="section-header" style="border-left:4px solid {meta['border']}">
            <span class="section-title" style="color:{meta['color']}">{meta['icon']} {category_name}</span>
            <span class="section-count">{count}종목</span>
        </div>
        {render_table(stocks, category_name, price_cache)}
    </section>"""

    note_경고위험 = (
        '<p class="note">해제 가능 주가: 5거래일 전 종가×1.6 또는 15거래일 전 종가×2.0 중 높은 값 이하 시 가격 조건 충족 (급등 유형 기준). '
        '최종 해제는 당일 15일 최고가 여부도 포함하여 종합 판단.</p>'
    )

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
            background: #f8f9fa; color: #1f2937; padding: 24px;
        }}
        header {{
            background: #000; border-radius: 10px; padding: 18px 24px;
            margin-bottom: 24px; display: flex; align-items: center;
            justify-content: space-between; flex-wrap: wrap; gap: 10px;
        }}
        header h1 {{ color: #fff; font-size: 1.5rem; font-weight: 700; }}
        .header-right {{ display: flex; align-items: center; gap: 16px; }}
        .last-updated {{ color: #9ca3af; font-size: 0.8rem; }}
        .back-btn {{
            padding: 6px 16px; background: #2d7a3a; color: #fff;
            text-decoration: none; border-radius: 6px;
            font-size: 0.85rem; font-weight: 600;
        }}
        .back-btn:hover {{ background: #357abd; }}
        .section {{
            background: #fff; border-radius: 8px; margin-bottom: 20px;
            padding: 20px 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        }}
        .section-header {{
            display: flex; align-items: center; gap: 12px;
            padding-left: 12px; margin-bottom: 14px;
        }}
        .section-title {{ font-size: 1rem; font-weight: 700; }}
        .section-count {{ font-size: 0.8rem; color: #6b7280; }}
        .note {{
            font-size: 0.75rem; color: #9ca3af; margin-top: 10px;
            line-height: 1.5;
        }}
        .data-table {{
            width: 100%; border-collapse: collapse; font-size: 0.86rem;
        }}
        .data-table th {{
            padding: 8px 10px; text-align: left;
            font-size: 0.76rem; font-weight: 600; color: #6b7280;
            border-bottom: 1px solid #e5e7eb; background: #f9fafb;
            white-space: nowrap;
        }}
        .data-table th.num, .data-table td.num {{ text-align: right; }}
        .data-table th.center, .data-table td.center {{ text-align: center; }}
        .data-table td {{
            padding: 8px 10px; border-bottom: 1px solid #f3f4f6;
            color: #374151; white-space: nowrap;
        }}
        .data-table tbody tr:last-child td {{ border-bottom: none; }}
        .data-table tbody tr:hover td {{ background: #f9fafb; }}
        footer {{
            text-align: center; padding: 16px; color: #9ca3af; font-size: 0.75rem;
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

    <div class="section" style="background:#f9fafb">
        {note_경고위험}
    </div>

    <footer>
        출처: <a href="https://kind.krx.co.kr" target="_blank">한국거래소 KIND</a> &nbsp;|&nbsp;
        투자주의: 금일 지정 기준 &nbsp;|&nbsp; 투자경고/위험: 현재 지정 중 기준 &nbsp;|&nbsp;
        본 자료는 참고용이며 투자 조언이 아닙니다
    </footer>
</body>
</html>"""


# ──────────────────────────────────────────
# 메인
# ──────────────────────────────────────────
def create_market_alert():
    print("📡 KIND 투자유의종목 데이터 수집 중...")
    now_kst  = datetime.now(tz=KST)
    today    = now_kst.strftime('%Y-%m-%d')
    start_90 = (now_kst - timedelta(days=90)).strftime('%Y-%m-%d')

    krx_data = load_krx_data()
    session  = get_session()

    print("  투자주의 조회 중...")
    stocks_주의 = parse_stocks(fetch_category(session, '투자주의', today, today), '투자주의', krx_data)
    print(f"    → {len(stocks_주의)}건")

    print("  투자경고 조회 중...")
    stocks_경고 = parse_stocks(fetch_category(session, '투자경고', start_90, today), '투자경고', krx_data)
    print(f"    → {len(stocks_경고)}건")

    print("  투자위험 조회 중...")
    stocks_위험 = parse_stocks(fetch_category(session, '투자위험', start_90, today), '투자위험', krx_data)
    print(f"    → {len(stocks_위험)}건")

    # 경고/위험만 주가 필요 (주의는 가격 조건 없음)
    all_stocks  = stocks_경고 + stocks_위험
    codes_needed = [s['code'] for s in all_stocks if s['code']]
    price_cache = fetch_all_prices(codes_needed, days_back=35)

    print("\n📝 HTML 생성 중...")
    html = generate_html(stocks_주의, stocks_경고, stocks_위험, price_cache)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✅ 완료: {OUTPUT_FILE}")
    print(f"   투자주의 {len(stocks_주의)}건 / 투자경고 {len(stocks_경고)}건 / 투자위험 {len(stocks_위험)}건")


if __name__ == '__main__':
    create_market_alert()
