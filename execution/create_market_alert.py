import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import re
import pandas as pd
import FinanceDataReader as fdr
import exchange_calendars as xcals

# KRX 거래 캘린더 (한국 공휴일 포함)
_xkrx = xcals.get_calendar('XKRX')

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
def _load_naver_marcap():
    """네이버 증권 시가총액 순위 페이지에서 code → marcap(억) 딕셔너리"""
    marcap_map = {}
    try:
        for sosok in [0, 1]:  # 0=KOSPI, 1=KOSDAQ
            for page in range(1, 40):
                url = f'https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}'
                r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                r.encoding = 'euc-kr'
                soup = BeautifulSoup(r.text, 'html.parser')
                table = soup.find('table', class_='type_2')
                if not table:
                    break
                found = 0
                for row in table.find_all('tr'):
                    cols = row.find_all('td')
                    if len(cols) < 7:
                        continue
                    a_tag = cols[1].find('a')
                    if not a_tag:
                        continue
                    href = a_tag.get('href', '')
                    m = re.search(r'code=(\d+)', href)
                    code = m.group(1) if m else ''
                    marcap_text = cols[6].get_text(strip=True).replace(',', '')
                    try:
                        marcap_map[code] = int(marcap_text)
                    except ValueError:
                        pass
                    found += 1
                if found == 0:
                    break
        print(f"  네이버 시가총액: {len(marcap_map)}개 종목")
    except Exception as e:
        print(f"  Warning: 네이버 시가총액 로드 실패: {e}")
    return marcap_map


def load_krx_data():
    """이름 → {marcap(억), code} 딕셔너리"""
    result = {}
    # 1) FDR에서 종목코드+이름 매핑
    for listing_type in ['KRX', 'KRX-DESC']:
        try:
            print(f"  KRX 종목 데이터 로드 중 ({listing_type})...")
            krx = fdr.StockListing(listing_type)
            has_marcap = 'Marcap' in krx.columns
            for _, row in krx.iterrows():
                name = str(row.get('Name', '')).strip()
                code = str(row.get('Code', '')).strip()
                if name:
                    cap = (row.get('Marcap', 0) or 0) if has_marcap else 0
                    result[name] = {
                        'marcap': int(cap) // 100_000_000 if cap else None,
                        'code': code,
                    }
            print(f"  → {len(result)}개 종목 (marcap: {'O' if has_marcap else 'X'})")
            break
        except Exception as e:
            print(f"  Warning: {listing_type} 로드 실패: {e}")

    if not result:
        return {}

    # 2) Marcap 없으면 네이버에서 보충
    has_any_marcap = any(v['marcap'] for v in result.values())
    if not has_any_marcap:
        print("  시가총액 데이터 없음 → 네이버에서 보충 중...")
        naver_marcap = _load_naver_marcap()
        for name, info in result.items():
            code = info['code']
            if code in naver_marcap:
                info['marcap'] = naver_marcap[code]

    return result


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
def _get_prev_closes(price_df):
    """전 거래일 기준 종가 시리즈 (오늘 데이터 제외)"""
    if price_df is None or price_df.empty:
        return pd.Series(dtype=float)
    today_kst = datetime.now(tz=KST).date()
    df = price_df[price_df.index.date < today_kst]
    return df['Close'] if not df.empty else pd.Series(dtype=float)


def get_판단일(designation_date_str, category):
    """지정일 포함 MIN_BDAYS 거래일째 = 해제여부 최초판단일 (KRX 실제 거래일 기준, 한국 공휴일 반영)"""
    try:
        d = pd.Timestamp(designation_date_str)
        sessions = _xkrx.sessions_window(d, count=MIN_BDAYS[category])
        return sessions[-1].strftime('%Y-%m-%d')
    except Exception:
        return '-'


def analyze_release(stock, price_df, category):
    """
    Returns:
        판단일        : str       (해제여부 최초판단일)
        current_price : int|None  (전 거래일 종가)
        target_price  : int|None  (해제 가능 주가; 투자주의=None)
        is_15d_high   : bool      (오늘 종가 = 최근 15거래일 최고가 → 해제 불가)
        low_15d       : int|None  (최근 15거래일 최저가)
    """
    desig_date = stock['designation_date']
    판단일      = get_판단일(desig_date, category)

    closes = _get_prev_closes(price_df)

    current_price = int(closes.iloc[-1]) if len(closes) >= 1 else None

    # 투자주의: 주가 조건 없음
    if category == '투자주의':
        return 판단일, current_price, None, False, None

    # 가격 데이터 없으면 주가 분석 불가
    if closes.empty:
        return 판단일, current_price, None, False, None

    # ── 기준 가격: 지정일 이전 종가로 고정 ──────────────────────────────
    desig_ts  = pd.Timestamp(desig_date)
    pre_desig = closes[closes.index < desig_ts]

    # T1: 지정일 전일 종가 × 1.6
    price_pre1d  = pre_desig.iloc[-1]  if len(pre_desig) >= 1  else None
    # T2: 지정일 기준 15거래일 전 종가 × 2.0 (데이터 부족 시 최초 가용일 사용)
    price_pre15d = pre_desig.iloc[-15] if len(pre_desig) >= 15 else (
                   pre_desig.iloc[0]   if not pre_desig.empty   else None)

    T1 = price_pre1d  * 1.6 if price_pre1d  is not None else None
    T2 = price_pre15d * 2.0 if price_pre15d is not None else None
    # 모든 조건 동시 충족(교집합) → 가장 엄격한(낮은) 값을 해제 가능 주가로 사용
    thresholds   = [t for t in [T1, T2] if t is not None]
    target_price = int(min(thresholds)) if thresholds else None

    # ── 15거래일 최고가 조건: 오늘 종가 = 최근 15거래일 최고가이면 해제 불가 ──
    recent_15 = closes.iloc[-15:] if len(closes) >= 15 else closes
    is_15d_high = False
    low_15d     = None
    if current_price is not None and not recent_15.empty:
        is_15d_high = (current_price >= int(recent_15.max()))
        low_15d     = int(recent_15.min())

    return 판단일, current_price, target_price, is_15d_high, low_15d


def analyze_escalation(stock, price_df):
    """
    투자주의 → 투자경고 전환 분석 (지정예고 종목만 해당)
    경고전환가 = min(5거래일전 종가×1.6, 15거래일전 종가×2.0)
    Returns:
        current_price    : int|None
        escalation_price : int|None  (경고전환가; 지정예고 아니면 None)
    """
    closes = _get_prev_closes(price_df)
    current_price = int(closes.iloc[-1]) if len(closes) >= 1 else None

    if stock.get('warn_type') != '투자경고 지정예고':
        return current_price, None

    if len(closes) < 2:
        return current_price, None

    # 5거래일 전 종가 (closes[-1]=어제, closes[-5]=5거래일 전)
    price_5d = closes.iloc[-5] if len(closes) >= 5 else closes.iloc[0]
    # 15거래일 전 종가
    price_15d = closes.iloc[-15] if len(closes) >= 15 else closes.iloc[0]

    T1 = price_5d * 1.6
    T2 = price_15d * 2.0
    escalation_price = int(min(T1, T2))

    return current_price, escalation_price


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
        # 투자경고/위험: 해제일 내림차순(D) → 미해제('-') 종목이 1페이지에 노출
        # 투자주의: 지정일 오름차순(A)
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

        # 코넥스 종목 제외
        if market == 'KONEX':
            continue

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
    jo = val // 10000
    eok = val % 10000
    if jo > 0 and eok > 0:
        return f'{jo:,}조 {eok:,}억원'
    elif jo > 0:
        return f'{jo:,}조원'
    else:
        return f'{eok:,}억원'


def render_table(stocks, category, price_cache):
    if not stocks:
        return '<p style="color:#9ca3af;padding:12px 0;font-size:0.85rem">현재 지정 종목 없음</p>'

    today_str  = datetime.now(tz=KST).strftime('%Y-%m-%d')
    today_ts   = pd.Timestamp.now().normalize()
    rows_html  = ''
    for s in stocks:
        price_df  = price_cache.get(s['code']) if s['code'] else None
        판단일, current_price, target_price, is_15d_high, low_15d = analyze_release(s, price_df, category)

        elapsed_str  = f"{s['elapsed']}일"
        cur_str      = f'{current_price:,}원' if current_price is not None else '-'

        # 판단일 기준 구분
        판단일_passed  = (판단일 != '-' and 판단일 <= today_str)
        if not 판단일_passed and 판단일 != '-':
            판단일_ts    = pd.Timestamp(판단일)
            bdays_left   = len(pd.bdate_range(today_ts + pd.offsets.BDay(1), 판단일_ts))
            판단일_임박   = bdays_left <= 5
        else:
            판단일_임박   = False

        # 배경색: 판단일 도달=#fca5a5(진한), 5영업일 이내=#fee2e2(연한), 나머지=없음
        if category == '투자주의':
            row_bg = ''
        elif 판단일_passed:
            row_bg = ' style="background-color:#fca5a5"'
        elif 판단일_임박:
            row_bg = ' style="background-color:#fee2e2"'
        else:
            row_bg = ''

        # 해제 가능 주가 셀: 판단일 경과 + 가격조건 충족 + 15일 최고가 아님 → 굵게
        if target_price is None:
            tgt_str = '-'
        elif 판단일_passed and not is_15d_high and current_price is not None and current_price <= target_price:
            tgt_str = f'<span style="font-weight:700">{target_price:,}원</span>'
        else:
            tgt_str = f'{target_price:,}원'

        if is_15d_high:
            high_str = '<span style="color:#ef4444;font-weight:700">최고가</span>'
        elif low_15d is not None:
            high_str = '-'
        else:
            high_str = ''

        rows_html += f"""
            <tr{row_bg}>
                <td>{s['name']}</td>
                <td>{s['market']}</td>
                <td class="num">{fmt_marcap(s['marcap'])}</td>
                <td class="center">{s['notice_date']}</td>
                <td class="center">{s['designation_date']}</td>
                <td class="center">{elapsed_str}</td>
                <td class="center">{판단일}</td>
                <td class="num">{cur_str}</td>
                <td class="center">{high_str}</td>
                <td class="num">{tgt_str}</td>
            </tr>"""

    return f"""
        <div style="overflow-x:auto">
        <table class="data-table tbl-warn">
            <thead>
                <tr>
                    <th>종목명</th>
                    <th>시장</th>
                    <th>시가총액</th>
                    <th>공시일</th>
                    <th>지정일</th>
                    <th>경과일</th>
                    <th>판단일</th>
                    <th>현재가</th>
                    <th>15일 최고가</th>
                    <th>해제 가능 주가</th>
                </tr>
            </thead>
            <tbody>{rows_html}
            </tbody>
        </table>
        </div>"""


def render_table_주의(stocks, price_cache):
    """투자주의 전용 테이블 (지정유형 + 경고전환가 컬럼)"""
    if not stocks:
        return '<p style="color:#9ca3af;padding:12px 0;font-size:0.85rem">현재 지정 종목 없음</p>'

    rows_html = ''
    for s in stocks:
        price_df = price_cache.get(s['code']) if s['code'] else None
        current_price, escalation_price = analyze_escalation(s, price_df)

        cur_str = f'{current_price:,}원' if current_price is not None else '-'

        # 지정유형
        warn_type = s.get('warn_type', '-')
        is_예고 = (warn_type == '투자경고 지정예고')
        if is_예고:
            type_str = f'<span style="color:#dc2626;font-weight:700">{warn_type}</span>'
        else:
            type_str = warn_type

        # 경고전환가 (지정예고만)
        if escalation_price is not None:
            if current_price is not None and current_price >= escalation_price:
                esc_str = f'<span style="color:#dc2626;font-weight:700">{escalation_price:,}원 ⚠</span>'
            else:
                esc_str = f'{escalation_price:,}원'
        else:
            esc_str = '-'

        row_bg = ' style="background-color:#fef2f2"' if is_예고 else ''

        rows_html += f"""
            <tr{row_bg}>
                <td>{s['name']}</td>
                <td>{s['market']}</td>
                <td class="num">{fmt_marcap(s['marcap'])}</td>
                <td class="center">{type_str}</td>
                <td class="center">{s['notice_date']}</td>
                <td class="center">{s['designation_date']}</td>
                <td class="num">{cur_str}</td>
                <td class="num">{esc_str}</td>
            </tr>"""

    return f"""
        <div style="overflow-x:auto">
        <table class="data-table">
            <thead>
                <tr>
                    <th>종목명</th>
                    <th>시장</th>
                    <th class="num">시가총액</th>
                    <th class="center">지정유형</th>
                    <th class="center">공시일</th>
                    <th class="center">지정일</th>
                    <th class="num">현재가</th>
                    <th class="num">경고전환가</th>
                </tr>
            </thead>
            <tbody>{rows_html}
            </tbody>
        </table>
        </div>"""


def fetch_shortsell_overheated(session, date_str):
    """KIND 당일공시에서 공매도 과열종목 지정 공시 수집"""
    data = {
        'method': 'searchTodayDisclosureSub',
        'forward': 'todaydisclosure_sub',
        'currentPageSize': '100',
        'pageIndex': '1',
        'orderMode': '0',
        'orderStat': 'D',
        'marketType': '',
        'searchCorpName': '',
        'searchType': 'A',
        'keyword': '',
        'todayFlag': 'N',
        'selDate': date_str,
    }
    try:
        resp = session.post(
            'https://kind.krx.co.kr/disclosure/todaydisclosure.do',
            data=data,
            headers={'Referer': 'https://kind.krx.co.kr/disclosure/todaydisclosure.do?method=searchTodayDisclosureMain'},
            timeout=15
        )
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        print(f"  공매도 과열종목 조회 실패: {e}")
        return []

    results = []
    for row in soup.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 4:
            continue
        title = cells[2].get_text(strip=True)
        if '공매도 과열종목' not in title and '공매도 거래 금지' not in title:
            continue
        time_str = cells[0].get_text(strip=True)
        name = cells[1].get_text(strip=True)
        market = cells[3].get_text(strip=True)
        results.append({
            'time': time_str,
            'name': name,
            'title': title,
            'market': '코스피' if '유가증권' in market else '코스닥' if '코스닥' in market else market,
            'date': date_str,
        })
    return results


def render_shortsell_section(stocks, krx_data=None):
    """공매도 과열종목 HTML 섹션"""
    if not stocks:
        return ''
    rows_html = ''
    for s in stocks:
        marcap_val = krx_data.get(s['name'], {}).get('marcap') if krx_data else None
        rows_html += f"""<tr>
<td style="font-weight:600">{s['name']}</td>
<td>{s['market']}</td>
<td class="num">{fmt_marcap(marcap_val)}</td>
<td>{s['title']}</td>
<td>{s['date']}</td>
</tr>"""
    return f"""
    <section class="section">
        <div class="section-header" style="border-left:4px solid #6366f1">
            <span class="section-title" style="color:#4338ca">🔻 공매도 과열종목</span>
            <span class="section-count">{len(stocks)}종목</span>
        </div>
        <div style="overflow-x:auto">
        <table class="data-table tbl-shortsell">
        <thead><tr>
            <th>종목</th><th>시장</th><th>시가총액</th><th>지정유형</th><th>공시일</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
        </table>
        </div>
    </section>"""


def generate_html(stocks_주의, stocks_경고, stocks_위험, price_cache, stocks_공매도=None, krx_data=None):
    now = datetime.now(tz=KST).strftime('%Y-%m-%d %H:%M:%S KST')

    def section(category_name, stocks):
        meta  = CATEGORY_META[category_name]
        count = len(stocks)
        if category_name == '투자주의':
            table_html = render_table_주의(stocks, price_cache)
        else:
            table_html = render_table(stocks, category_name, price_cache)
        return f"""
    <section class="section">
        <div class="section-header" style="border-left:4px solid {meta['border']}">
            <span class="section-title" style="color:{meta['color']}">{meta['icon']} {category_name}</span>
            <span class="section-count">{count}종목</span>
        </div>
        {table_html}
    </section>"""

    note_주의 = (
        '<p class="note"><b>투자경고 지정예고</b>: 투자주의 지정과 동시에 투자경고 지정예고가 된 종목. '
        '경고전환가 = min(5거래일전 종가×1.6, 15거래일전 종가×2.0) — '
        '현재가가 경고전환가를 초과하면 투자경고로 전환될 수 있음. '
        '<span style="color:#dc2626">⚠</span> 표시는 현재가 ≥ 경고전환가.</p>'
    )

    note_경고위험 = (
        '<p class="note"><b>해제 가능 주가</b>: (지정일 전일 종가×1.6)과 (지정일 전 15거래일 종가×2.0) 중 낮은 값 — 모든 조건 동시 충족 필요 (급등 유형 기준). '
        '판단일 경과 + 현재가 ≤ 해제 가능 주가 + 당일이 15거래일 최고가가 아닐 때 해제 가능. '
        '<span style="color:#ef4444">15일 최고가</span> 표시 시 가격 조건 충족이나 최고가 조건으로 해제 불가.</p>'
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>투자유의종목 현황</title>
    <link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=Noto+Sans+KR:wght@400;500;700&display=swap' rel='stylesheet'>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', 'Noto Sans KR', sans-serif;
            background: #f8f9fa; color: #1f2937; padding: 24px;
            max-width: 1200px; margin: 0 auto;
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
            padding: 6px 16px; background: #e0e0e0; color: #333;
            text-decoration: none; border-radius: 8px;
            font-size: 0.85rem; font-weight: 600;
        }}
        .back-btn:hover {{ background: #ccc; }}
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
            width: 100%; border-collapse: collapse; font-size: 0.82rem;
            table-layout: fixed;
        }}
        .data-table.tbl-warn {{ /* 투자위험/경고 공통 */ }}
        .data-table.tbl-warn th:nth-child(1),
        .data-table.tbl-warn td:nth-child(1) {{ width: 14%; }} /* 종목명 */
        .data-table.tbl-warn th:nth-child(2),
        .data-table.tbl-warn td:nth-child(2) {{ width: 8%; }}  /* 시장 */
        .data-table.tbl-warn th:nth-child(3),
        .data-table.tbl-warn td:nth-child(3) {{ width: 11%; }} /* 시가총액 */
        .data-table.tbl-warn th:nth-child(4),
        .data-table.tbl-warn td:nth-child(4) {{ width: 11%; }} /* 공시일 */
        .data-table.tbl-warn th:nth-child(5),
        .data-table.tbl-warn td:nth-child(5) {{ width: 11%; }} /* 지정일 */
        .data-table.tbl-warn th:nth-child(6),
        .data-table.tbl-warn td:nth-child(6) {{ width: 7%; }}  /* 경과일 */
        .data-table.tbl-warn th:nth-child(7),
        .data-table.tbl-warn td:nth-child(7) {{ width: 11%; }} /* 판단일 */
        .data-table.tbl-warn th:nth-child(8),
        .data-table.tbl-warn td:nth-child(8) {{ width: 10%; }} /* 현재가 */
        .data-table.tbl-warn th:nth-child(9),
        .data-table.tbl-warn td:nth-child(9) {{ width: 9%; }}  /* 15일 최고가 */
        .data-table.tbl-warn th:nth-child(10),
        .data-table.tbl-warn td:nth-child(10) {{ width: 10%; }} /* 해제가능주가 */
        .data-table.tbl-shortsell th:nth-child(1),
        .data-table.tbl-shortsell td:nth-child(1) {{ width: 13%; }} /* 종목 */
        .data-table.tbl-shortsell th:nth-child(2),
        .data-table.tbl-shortsell td:nth-child(2) {{ width: 13%; }} /* 시장 */
        .data-table.tbl-shortsell th:nth-child(3),
        .data-table.tbl-shortsell td:nth-child(3) {{ width: 13%; }} /* 시가총액 */
        .data-table.tbl-shortsell th:nth-child(4),
        .data-table.tbl-shortsell td:nth-child(4) {{ width: 48%; }} /* 지정유형 */
        .data-table.tbl-shortsell th:nth-child(5),
        .data-table.tbl-shortsell td:nth-child(5) {{ width: 13%; }} /* 공시일 */
        .data-table th {{
            padding: 8px 10px; text-align: center;
            font-size: 0.74rem; font-weight: 600; color: #6b7280;
            border-bottom: 1px solid #e5e7eb; background: #f9fafb;
            white-space: nowrap; cursor: pointer; user-select: none;
        }}
        .data-table th:hover {{ color: #111; }}
        .data-table th .sort-arrow {{ font-size: 0.6rem; margin-left: 2px; color: #aaa; }}
        .data-table td {{
            padding: 6px 10px; border-bottom: 1px solid #f3f4f6;
            color: #374151; white-space: nowrap; font-size: 0.8rem;
            text-align: center;
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
            <a href="index.html" class="back-btn">🏠 Home</a>
        </div>
    </header>

    {section('투자위험', stocks_위험)}
    {section('투자경고', stocks_경고)}
    {section('투자주의', stocks_주의)}
    {render_shortsell_section(stocks_공매도 or [], krx_data)}

    <div class="section" style="background:#f9fafb">
        {note_주의}
        {note_경고위험}
    </div>

    <footer>
        출처: <a href="https://kind.krx.co.kr" target="_blank">한국거래소 KIND</a> &nbsp;|&nbsp;
        투자주의: 금일 지정 기준 &nbsp;|&nbsp; 투자경고/위험: 현재 지정 중 기준 &nbsp;|&nbsp;
        본 자료는 참고용이며 투자 조언이 아닙니다
    </footer>
    <script>
    document.querySelectorAll('.data-table th').forEach(function(th) {{
        th.innerHTML = th.innerHTML + '<span class="sort-arrow"></span>';
        th.addEventListener('click', function() {{
            var table = th.closest('table');
            var tbody = table.querySelector('tbody');
            var rows = Array.from(tbody.querySelectorAll('tr'));
            var idx = Array.from(th.parentNode.children).indexOf(th);
            var asc = th.dataset.sort !== 'asc';
            // 같은 테이블의 다른 th 정렬 표시 제거
            th.parentNode.querySelectorAll('th .sort-arrow').forEach(function(s) {{ s.textContent = ''; }});
            th.querySelector('.sort-arrow').textContent = asc ? ' ▲' : ' ▼';
            th.dataset.sort = asc ? 'asc' : 'desc';
            rows.sort(function(a, b) {{
                var ac = a.children[idx], bc = b.children[idx];
                if (!ac || !bc) return 0;
                var av = ac.textContent.trim(), bv = bc.textContent.trim();
                // 숫자 파싱 (콤마, 억원, 조, 원 등 제거)
                var an = parseFloat(av.replace(/[^0-9.\-]/g, '')), bn = parseFloat(bv.replace(/[^0-9.\-]/g, ''));
                if (!isNaN(an) && !isNaN(bn)) {{
                    // 조 단위 보정
                    if (av.includes('조')) an *= 10000;
                    if (bv.includes('조')) bn *= 10000;
                    return asc ? an - bn : bn - an;
                }}
                return asc ? av.localeCompare(bv, 'ko') : bv.localeCompare(av, 'ko');
            }});
            rows.forEach(function(r) {{ tbody.appendChild(r); }});
        }});
    }});
    </script>
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
    # 투자주의는 5영업일 유효 → 최근 10일(≈5영업일+주말) 범위로 조회
    start_10 = (now_kst - timedelta(days=10)).strftime('%Y-%m-%d')

    krx_data = load_krx_data()
    session  = get_session()

    print("  투자주의 조회 중...")
    stocks_주의 = parse_stocks(fetch_category(session, '투자주의', start_10, today), '투자주의', krx_data)
    # 종목명 기준 중복 제거: 가장 최근 지정일 1건만 유지
    seen = {}
    for s in stocks_주의:
        name = s['name']
        if name not in seen or s['designation_date'] > seen[name]['designation_date']:
            seen[name] = s
    stocks_주의 = list(seen.values())
    print(f"    → {len(stocks_주의)}건")

    print("  투자경고 조회 중...")
    stocks_경고 = parse_stocks(fetch_category(session, '투자경고', start_90, today), '투자경고', krx_data)
    print(f"    → {len(stocks_경고)}건")

    print("  투자위험 조회 중...")
    stocks_위험 = parse_stocks(fetch_category(session, '투자위험', start_90, today), '투자위험', krx_data)
    print(f"    → {len(stocks_위험)}건")

    # 경고/위험: T1(지정일 전일), T2(지정일 전 15거래일) 기준 → 지정일이 최대 90일 전까지 가능
    # 넉넉하게 120일 확보 (90일 지정 + 15거래일×1.5 = ~113 calendar days)
    codes_경고위험 = [s['code'] for s in stocks_경고 + stocks_위험 if s['code']]
    price_cache   = fetch_all_prices(codes_경고위험, days_back=120)

    # 투자주의: 지정예고 종목은 경고전환가 계산에 15거래일 필요 → 35일치
    codes_예고 = {s['code'] for s in stocks_주의
                  if s['code'] and s.get('warn_type') == '투자경고 지정예고'}
    codes_예고_only = [c for c in codes_예고 if c not in price_cache]
    if codes_예고_only:
        price_cache.update(fetch_all_prices(codes_예고_only, days_back=35))

    # 나머지 투자주의: 현재가만 필요 → 3일치
    codes_주의_only = [c for c in {s['code'] for s in stocks_주의 if s['code']}
                      if c not in price_cache]
    if codes_주의_only:
        price_cache.update(fetch_all_prices(codes_주의_only, days_back=3))

    # 시가총액 1,000억원 이하 제외
    MIN_MARCAP = 1000  # 억원
    before = (len(stocks_주의), len(stocks_경고), len(stocks_위험))
    stocks_주의 = [s for s in stocks_주의 if s.get('marcap') and s['marcap'] >= MIN_MARCAP]
    stocks_경고 = [s for s in stocks_경고 if s.get('marcap') and s['marcap'] >= MIN_MARCAP]
    stocks_위험 = [s for s in stocks_위험 if s.get('marcap') and s['marcap'] >= MIN_MARCAP]
    after = (len(stocks_주의), len(stocks_경고), len(stocks_위험))
    filtered = sum(b - a for b, a in zip(before, after))
    if filtered:
        print(f"  시가총액 {MIN_MARCAP}억 미만 {filtered}건 제외")

    # 공매도 과열종목 (당일 + 전일 공시)
    print("  공매도 과열종목 조회 중...")
    stocks_공매도 = []
    for d in [today, (now_kst - timedelta(days=1)).strftime('%Y-%m-%d')]:
        stocks_공매도.extend(fetch_shortsell_overheated(session, d))
    # 중복 제거 (같은 종목명+날짜)
    seen_ss = set()
    unique_공매도 = []
    for s in stocks_공매도:
        key = (s['name'], s['date'])
        if key not in seen_ss:
            seen_ss.add(key)
            unique_공매도.append(s)
    stocks_공매도 = unique_공매도
    print(f"    → {len(stocks_공매도)}건")

    print("\n📝 HTML 생성 중...")
    html = generate_html(stocks_주의, stocks_경고, stocks_위험, price_cache, stocks_공매도, krx_data)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✅ 완료: {OUTPUT_FILE}")
    print(f"   투자주의 {len(stocks_주의)}건 / 투자경고 {len(stocks_경고)}건 / 투자위험 {len(stocks_위험)}건 / 공매도 과열 {len(stocks_공매도)}건")


if __name__ == '__main__':
    create_market_alert()
