import pandas as pd
import FinanceDataReader as fdr
import sys
import json
import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# Windows console encoding fix
sys.stdout.reconfigure(encoding='utf-8')

# Constants
WRAP_NAV_FILE = 'Wrap_NAV.xlsx'
OUTPUT_FILE = 'portfolio_data.json'
EXISTING_STOCK_BASIS_FILE = 'existing_stock_basis.json'

# 포트폴리오 표시 이름 매핑
PORTFOLIO_DISPLAY_NAMES = {
    '트루밸류': '삼성 트루밸류',
    'Value ESG': 'NH Value ESG',
    '개방형 랩': 'DB 개방형',
    # '목표전환형 5차': 'DB 목표전환형 5차',  # DB 5차 완료 (2026-06-19 청산, +7.72%) / NH 4호 (+5.38%) 페어 청산
    # '목표전환형 3호': 'NH 목표전환형 3호',  # NH 3호 완료 (2026-05-27 청산, 목표달성)
    # '목표전환형 4차': 'DB 목표전환형 4차',  # DB 4차 완료 (2026-05-27 청산, 목표달성)
    # '목표전환형 2호': 'NH 목표전환형 2호',  # NH 2호 완료 (2026-05-06, +7.26%, 목표 6.5% 초과)
    # '목표전환형 3차': 'DB 목표전환형 3차',  # DB 3차 완료 (2026-05-06, +7.97%, 목표 7.5% 초과)
    # '목표전환형': 'DB 목표전환형',  # DB 1차 완료 (2026-02-25 청산, 목표 7.5% 달성)
    # '목표전환형 2차': 'DB 목표전환형 2차 / NH 목표전환형 1호',  # 2차+1호 완료 (2026-04-15, DB 7.5% / NH 6.5% 달성)
}

# 표시 제외 포트폴리오 (역사 데이터는 보존하되 대시보드에서 숨김)
EXCLUDED_PORTFOLIOS = {'목표전환형', '목표전환형 1호', '목표전환형 2호', '목표전환형 2차', '목표전환형 3차', '목표전환형 3호', '목표전환형 4차', '목표전환형 5차', '목표전환형 4호'}

# 편입일 이전부터 보유 중인 종목의 평균 매수가 (existing_stock_basis.json 로드)
# 이후 누적 수익률은 (current_price / avg_price - 1) * 100 로 매일 계산
def _load_existing_stock_basis():
    try:
        with open(EXISTING_STOCK_BASIS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {code: info['avg_price'] for code, info in data.get('stocks', {}).items()}
    except Exception as e:
        print(f"  Warning: {EXISTING_STOCK_BASIS_FILE} 로드 실패: {e}")
        return {}

EXISTING_STOCK_AVG_PRICES = _load_existing_stock_basis()


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


def fetch_price_data(code):
    """종목의 최근 가격 데이터를 가져오기 (스레드에서 호출)"""
    try:
        end_date = pd.Timestamp.now()
        start_date = end_date - timedelta(days=365*30)  # 30년치 (역대 최고가 DD 계산용)
        df = fdr.DataReader(code, start=start_date)
        return code, df
    except Exception as e:
        print(f"  Warning: Could not fetch price for {code}: {e}")
        return code, pd.DataFrame()


def get_today_return_from_cache(price_df):
    """캐시된 가격 데이터에서 오늘 수익률 계산"""
    if price_df is None or len(price_df) < 2:
        return None
    latest_price = price_df.iloc[-1]['Close']
    prev_price = price_df.iloc[-2]['Close']
    return ((latest_price - prev_price) / prev_price) * 100


def get_inclusion_date(code, portfolio_name, nav_df):
    """포트폴리오 NAV 이력에서 종목 편입일(마지막 전량매도 이후 첫 비중>0 날짜) 반환.
    RSI '편입 이후' 기준점으로 사용. 추적 개시 전부터 보유한 기존 종목은
    NAV 첫 등장일(추적 개시일)을 자동 반환하므로 별도 하드코딩 불필요."""
    try:
        hist = nav_df[(nav_df['상품명'] == portfolio_name) & (nav_df['코드'] == int(code))]
        if hist.empty:
            return None
        hist = hist.sort_values('날짜')
        zero_dates = hist[hist['비중'] == 0]['날짜']
        if not zero_dates.empty:
            hist = hist[hist['날짜'] > zero_dates.max()]
        purchases = hist[hist['비중'] > 0]
        if purchases.empty:
            return None
        return purchases['날짜'].min()
    except Exception:
        return None


def calculate_cumulative_return(code, stock_name, portfolio_name, nav_df, price_df):
    """
    종목의 누적 수익률 계산 (캐시된 데이터 사용)
    """
    try:
        # 편입일 이전부터 보유 중인 종목: existing_stock_basis.json 의 avg_price로 매일 재계산
        # (목표전환형 시리즈는 신규 펀드이므로 직접 계산 경로로)
        if code in EXISTING_STOCK_AVG_PRICES and not portfolio_name.startswith('목표전환형'):
            avg_price = EXISTING_STOCK_AVG_PRICES[code]
            if price_df is None or price_df.empty:
                return {'cumulative_return': None, 'status': 'existing', 'avg_price': avg_price,
                        'current_price': None, 'dd': None, 'all_time_high': None}
            current_price = float(price_df.iloc[-1]['Close'])
            cumulative_return = (current_price / avg_price - 1) * 100
            all_time_high = float(price_df['Close'].max())
            dd = (current_price / all_time_high - 1) * 100 if all_time_high > 0 else None
            return {
                'cumulative_return': cumulative_return,
                'status': 'existing',
                'avg_price': avg_price,
                'current_price': current_price,
                'dd': dd,
                'all_time_high': all_time_high,
            }

        # 해당 포트폴리오의 해당 종목 이력
        stock_history = nav_df[(nav_df['상품명'] == portfolio_name) & (nav_df['코드'] == int(code))].copy()
        stock_history = stock_history.sort_values('날짜')

        if stock_history.empty:
            return {'cumulative_return': None, 'status': 'not_found', 'avg_price': None, 'current_price': None, 'dd': None, 'all_time_high': None}

        # 첫 등장일 확인
        first_date = stock_history['날짜'].min()
        is_2026_new = first_date.year >= 2026

        # 전량 매도 시점 찾기 (weight = 0)
        zero_weight_dates = stock_history[stock_history['비중'] == 0]['날짜'].tolist()

        # 마지막 전량 매도 이후의 데이터만 사용
        if zero_weight_dates:
            last_zero_date = max(zero_weight_dates)
            stock_history = stock_history[stock_history['날짜'] > last_zero_date]
            status = 'resold'
        else:
            status = '2026_new' if is_2026_new else 'existing'

        # 기존 보유 종목은 공란 처리
        if status == 'existing':
            return {
                'cumulative_return': None,
                'status': 'existing',
                'avg_price': None,
                'current_price': None,
                'first_date': first_date,
                'dd': None,
                'all_time_high': None
            }

        # 비중이 0이 아닌 매수 데이터만 추출
        purchases = stock_history[stock_history['비중'] > 0].copy()

        if purchases.empty:
            return {'cumulative_return': None, 'status': 'no_purchases', 'avg_price': None, 'current_price': None, 'dd': None, 'all_time_high': None}

        # 오늘 처음 편입된 종목은 수익률 미표시
        today_norm = pd.Timestamp.now().normalize()
        if purchases['날짜'].min() >= today_norm:
            return {'cumulative_return': None, 'status': 'today_new', 'avg_price': None, 'current_price': None, 'dd': None, 'all_time_high': None}

        # 캐시된 가격 데이터가 없으면 계산 불가
        if price_df is None or price_df.empty:
            return {'cumulative_return': None, 'status': 'no_price_data', 'avg_price': None, 'current_price': None, 'dd': None, 'all_time_high': None}

        # 각 매수 시점의 종가 가져오기 (캐시된 데이터에서)
        weighted_sum = 0
        total_weight = 0

        for _, row in purchases.iterrows():
            purchase_date = row['날짜']
            weight = row['비중']

            try:
                if purchase_date in price_df.index:
                    close_price = price_df.loc[purchase_date, 'Close']
                else:
                    available_dates = price_df[price_df.index <= purchase_date]
                    if not available_dates.empty:
                        close_price = available_dates.iloc[-1]['Close']
                    else:
                        close_price = price_df.iloc[0]['Close']

                weighted_sum += close_price * weight
                total_weight += weight
            except Exception as e:
                print(f"    Warning: Could not get price for {stock_name} on {purchase_date}: {e}")
                continue

        if total_weight == 0:
            return {'cumulative_return': None, 'status': 'no_valid_prices', 'avg_price': None, 'current_price': None, 'dd': None, 'all_time_high': None}

        avg_price = weighted_sum / total_weight
        current_price = price_df.iloc[-1]['Close']
        cumulative_return = (current_price / avg_price - 1) * 100

        # DD: 역대 최고가 대비 현재가 하락률
        all_time_high = price_df['Close'].max()
        dd = (current_price / all_time_high - 1) * 100 if all_time_high > 0 else None

        return {
            'cumulative_return': cumulative_return,
            'status': status,
            'avg_price': avg_price,
            'current_price': current_price,
            'first_date': first_date,
            'dd': dd,
            'all_time_high': all_time_high
        }

    except Exception as e:
        print(f"    Error calculating cumulative return for {stock_name}: {e}")
        import traceback
        traceback.print_exc()
        return {'cumulative_return': None, 'status': 'error', 'avg_price': None, 'current_price': None, 'dd': None, 'all_time_high': None}


def create_portfolio_tables():
    """포트폴리오 테이블 데이터 생성"""
    print("1. Wrap NAV 파일 읽기...")

    try:
        # NEW 시트에서 포트폴리오 데이터 읽기 (1회만)
        nav_df = pd.read_excel(WRAP_NAV_FILE, sheet_name='NEW')
        nav_df['날짜'] = pd.to_datetime(nav_df['날짜'])

        print(f"   전체 날짜 범위: {nav_df['날짜'].min()} ~ {nav_df['날짜'].max()}")

        # 오늘 KST (D-1 기준 weight_prev 계산 + latest_portfolio_date 컷오프 공용)
        from datetime import timezone, timedelta as _td
        _today_kst = pd.Timestamp.now(tz=timezone(_td(hours=9))).normalize().tz_localize(None)

        # 시장 지수 가격 시계열 (RSI = 편입 이후 종목 수익률 − 동일 기간 지수 수익률, %p)
        # KRX는 KOSPI/KOSDAQ만 매핑 (KONEX 등은 RSI 미표시).
        # fdr KS11/KQ11은 data.krx LOGOUT 차단 → universe.html RSI(1M)과 동일하게 yfinance ^KS11/^KQ11 사용.
        INDEX_PRICE_SERIES = {'KOSPI': None, 'KOSDAQ': None}
        try:
            import yfinance as yf
            _idx_start = (pd.Timestamp.now() - pd.DateOffset(years=3)).strftime('%Y-%m-%d')
            for mkt, ticker in [('KOSPI', '^KS11'), ('KOSDAQ', '^KQ11')]:
                try:
                    closes = yf.Ticker(ticker).history(start=_idx_start, auto_adjust=False)['Close'].dropna()
                    if getattr(closes.index, 'tz', None) is not None:
                        closes.index = closes.index.tz_localize(None)
                    closes.index = closes.index.normalize()
                    INDEX_PRICE_SERIES[mkt] = closes if not closes.empty else None
                    print(f"  지수 {mkt} ({ticker}): {len(closes)}일 (RSI 편입 이후 기준)")
                except Exception as e:
                    print(f"  Warning: 지수 {mkt} 로드 실패 (RSI 미표시): {e}")
        except Exception as e:
            print(f"  Warning: yfinance import 실패 (RSI 미표시): {e}")

        # KRX 종목 리스트 미리 로드 (KRX → KRX-DESC fallback)
        print("2. KRX 종목 리스트 로드 중...")
        krx = pd.DataFrame(columns=['Code', 'Marcap'])
        for listing_type in ['KRX', 'KRX-DESC']:
            try:
                print(f"  {listing_type} 시도...")
                krx = fdr.StockListing(listing_type)
                has_marcap = 'Marcap' in krx.columns
                print(f"  → {len(krx)}개 종목 (Marcap: {'O' if has_marcap else 'X'})")
                break
            except Exception as e:
                print(f"  Warning: {listing_type} 로드 실패: {e}")

        # Marcap 컬럼 없으면 네이버에서 보충
        if 'Marcap' not in krx.columns or krx['Marcap'].sum() == 0:
            print("  시가총액 데이터 없음 → 네이버에서 보충 중...")
            naver_marcap = _load_naver_marcap()
            if 'Code' in krx.columns:
                krx['Marcap'] = krx['Code'].map(
                    lambda c: naver_marcap.get(c, 0) * 100_000_000  # 억→원 변환
                ).fillna(0)
            print(f"  → 네이버 시가총액 {len(naver_marcap)}개 매핑 완료")

        # Code 시트에서 FICS 섹터 매핑 로드
        code_df = pd.read_excel(WRAP_NAV_FILE, sheet_name='Code')
        code_df['종목코드'] = code_df['종목코드'].apply(lambda x: str(x).zfill(6))
        sector_map = dict(zip(code_df['종목코드'], code_df['섹터']))

        # WRAP Order 탭 종목명/코드 양방향 자동완성용 마스터 (외부 API CORS 차단 우회)
        master_rows = []
        for _, r in code_df.iterrows():
            name = r.get('종목명')
            code = r.get('종목코드')
            sector = r.get('섹터')
            if not isinstance(code, str) or not code or pd.isna(name):
                continue
            master_rows.append({
                'code': code,
                'name': str(name),
                'sector': '' if pd.isna(sector) else str(sector),
            })
        with open('stock_master.json', 'w', encoding='utf-8') as f:
            json.dump(master_rows, f, ensure_ascii=False)
        print(f"stock_master.json 생성: {len(master_rows)}종목")

        # === 포트폴리오 그룹 정의 (동일 종목/비중을 공유하여 합쳐서 표시) ===
        # sources: Wrap_NAV.xlsx 상품명 / combined: 표시 결합명 / use: 데이터 가져올 포트폴리오
        PORTFOLIO_GROUPS = [
            {
                'sources': ['트루밸류', 'Value ESG', '개방형 랩'],
                'combined': '삼성 트루밸류 / NH Value ESG / DB 개방형',
                'use': '트루밸류',
            },
            # NH 4호 + DB 5차 페어 완료 (2026-06-19 청산, 목표달성) — 다음 페어 출시 시 sources 재추가
            # {
            #     'sources': ['목표전환형 5차', '목표전환형 4호'],
            #     'combined': 'NH 목표전환형 4호 / DB 목표전환형 5차',
            #     'use': '목표전환형 5차',
            # },
            # NH 3호 + DB 4차 페어 완료 (2026-05-27 청산, 목표달성) — 다음 페어 출시 시 sources 재추가
            # {
            #     'sources': ['목표전환형 3호', '목표전환형 4차'],
            #     'combined': 'NH 목표전환형 3호 / DB 목표전환형 4차',
            #     'use': '목표전환형 3호',
            # },
        ]

        today = pd.Timestamp.now().normalize()

        # 포트폴리오별 종목 구성을 미리 계산
        portfolio_configs = []
        all_codes = set()

        processed = set()
        for portfolio_name in nav_df['상품명'].unique():
            if portfolio_name in processed:
                continue

            if portfolio_name in EXCLUDED_PORTFOLIOS:
                processed.add(portfolio_name)
                continue

            # 그룹 매칭
            group = next((g for g in PORTFOLIO_GROUPS if portfolio_name in g['sources']), None)
            if group:
                display_name = group['combined']
                use_portfolio = group['use']
                processed.update(group['sources'])
            else:
                display_name = PORTFOLIO_DISPLAY_NAMES.get(portfolio_name, portfolio_name)
                use_portfolio = portfolio_name
                processed.add(portfolio_name)

            portfolio_df = nav_df[nav_df['상품명'] == use_portfolio].copy()
            if portfolio_df.empty:
                continue

            available_dates = sorted(portfolio_df['날짜'].unique())
            # today_date = 오늘 이하 가장 최근 (당일 최종 저장분 포함) → Order 탭 변경후 baseline
            # disp_date  = 오늘 미만 가장 최근 (전일/D-1 공식 구성) → 대시보드 PORTFOLIO 표·/update 메시지
            # 당일 finalize된 주문은 다음 거래일부터 표·메시지에 반영 (Order 탭은 즉시 반영).
            dates_le_today = [d for d in available_dates if d <= _today_kst]
            dates_lt_today = [d for d in available_dates if d < _today_kst]
            today_date = dates_le_today[-1] if dates_le_today else available_dates[-1]
            disp_date = dates_lt_today[-1] if dates_lt_today else today_date

            def _composition(date):
                rows = portfolio_df[(portfolio_df['날짜'] == date) & (portfolio_df['비중'] > 0)]
                comp = {}
                for _, r in rows.iterrows():
                    c = str(int(r['코드'])).zfill(6)
                    comp[c] = {'name': r['종목'], 'weight': float(r['비중'])}
                return comp

            today_comp = _composition(today_date)
            disp_comp = _composition(disp_date)

            # 표시 종목 = 오늘 ∪ D-1 (편출된 종목도 D-1 뷰에 남기고, Order 탭 편출 표시용)
            union_codes = list(disp_comp.keys()) + [c for c in today_comp if c not in disp_comp]
            union_stocks = []
            for c in union_codes:
                info = today_comp.get(c) or disp_comp.get(c)
                union_stocks.append({
                    'code': c,
                    'name': info['name'],
                    'weight': today_comp.get(c, {}).get('weight', 0.0),      # 오늘(Order 탭 변경후)
                    'weight_prev': disp_comp.get(c, {}).get('weight', 0.0),  # D-1(표·메시지 표시용)
                })
            # 표시(D-1) 기준 정렬: weight_prev desc → weight desc
            union_stocks.sort(key=lambda s: (s['weight_prev'], s['weight']), reverse=True)
            all_codes.update(s['code'] for s in union_stocks)

            # 당일 finalize된 주문 변경 내역 (아직 표·메시지에 미반영분)
            order_change = None
            if today_date > disp_date:
                added, removed, changed = [], [], []
                for c, info in today_comp.items():
                    if c not in disp_comp:
                        added.append({'name': info['name'], 'weight': info['weight']})
                    elif abs(disp_comp[c]['weight'] - info['weight']) > 1e-9:
                        changed.append({'name': info['name'], 'from': disp_comp[c]['weight'], 'to': info['weight']})
                for c, info in disp_comp.items():
                    if c not in today_comp:
                        removed.append({'name': info['name'], 'weight': info['weight']})
                if added or removed or changed:
                    order_change = {
                        'date': pd.Timestamp(today_date).strftime('%Y-%m-%d'),
                        'added': added, 'changed': changed, 'removed': removed,
                    }

            portfolio_configs.append({
                'display_name': display_name,
                'use_portfolio': use_portfolio,
                'today_date': today_date,
                'disp_date': disp_date,
                'union_stocks': union_stocks,
                'portfolio_df': portfolio_df,
                'order_change': order_change,
            })

        # === 모든 종목 가격을 병렬로 조회 ===
        print(f"\n3. {len(all_codes)}개 종목 가격 병렬 조회 중...")
        price_cache = {}

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_price_data, code): code for code in all_codes}
            for future in as_completed(futures):
                code, price_df = future.result()
                price_cache[code] = price_df
                if not price_df.empty:
                    print(f"   ✓ {code} ({len(price_df)}일)")
                else:
                    print(f"   ✗ {code} (데이터 없음)")

        print(f"   가격 조회 완료!")

        # === 포트폴리오별 데이터 생성 ===
        portfolio_data = {}

        for config in portfolio_configs:
            display_name = config['display_name']
            use_portfolio = config['use_portfolio']
            today_date = config['today_date']
            disp_date = config['disp_date']
            union_stocks = config['union_stocks']
            portfolio_df = config['portfolio_df']

            print(f"\n4. {display_name} 포트폴리오 처리 중...")
            print(f"   표시 기준 날짜(D-1): {disp_date} / 오늘 구성 날짜: {today_date}")

            stocks_info = []
            for u in union_stocks:
                code = u['code']
                stock_name = u['name']
                weight = u['weight']            # 오늘(Order 탭 변경후)
                weight_prev = u['weight_prev']  # D-1(표·메시지 표시용)

                stock_data = krx[krx['Code'] == code]
                sector = sector_map.get(code, '기타')
                if pd.isna(sector):
                    sector = '기타'

                if not stock_data.empty:
                    market_cap = stock_data.iloc[0].get('Marcap', 0)
                    market_cap_billions = market_cap / 100000000 if market_cap else 0
                else:
                    market_cap_billions = 0

                price_df = price_cache.get(code)

                # 누적 수익률 계산 (오늘 편입 여부도 함께 확인)
                cumulative_result = calculate_cumulative_return(code, stock_name, use_portfolio, nav_df, price_df)
                is_today_new = (cumulative_result.get('status') == 'today_new')

                # 오늘 처음 편입된 종목은 수익률/기여도/누적 미표시
                if is_today_new:
                    today_return = None
                    contribution = None
                    cumulative_return = None
                else:
                    today_return = get_today_return_from_cache(price_df)
                    cumulative_return = cumulative_result.get('cumulative_return')
                    # 기여도는 표·메시지(D-1 뷰) 기준이므로 weight_prev로 계산.
                    # (평소엔 weight_prev == weight, finalize 당일만 D-1 비중 사용)
                    contribution = (weight_prev / 100) * (today_return / 100) * 1000 if today_return is not None else None

                # DD: price_df에서 직접 계산 (역대 최고가 대비)
                dd = None
                current_price = None
                ath_price = None
                if price_df is not None and not price_df.empty:
                    try:
                        ath_price = float(price_df['Close'].max())
                        current_price = float(price_df.iloc[-1]['Close'])
                        if ath_price > 0:
                            dd = (current_price / ath_price - 1) * 100
                    except:
                        pass

                # RSI = 편입 이후 종목 수익률 − 동일 기간 시장 지수 수익률 (%p). 양수 = 시장 대비 초과.
                # 기준점 = 편입일(마지막 전량매도 이후 첫 비중>0 날짜) 당일 종가(on-or-before, 누적수익률과 동일).
                # 종목·지수 모두 같은 편입일부터 현재까지 측정 → 동일 종목도 포트폴리오별 편입일 다르면 RSI 다름.
                rsi = None
                incl_date = None if is_today_new else get_inclusion_date(code, use_portfolio, nav_df)
                if incl_date is not None and price_df is not None and not price_df.empty:
                    try:
                        market = str(stock_data.iloc[0].get('Market', '') or '').upper() if not stock_data.empty else ''
                        idx_key = 'KOSPI' if 'KOSPI' in market else ('KOSDAQ' if 'KOSDAQ' in market else None)
                        idx_series = INDEX_PRICE_SERIES.get(idx_key) if idx_key else None
                        if idx_series is not None and not idx_series.empty:
                            s_base_rows = price_df[price_df.index <= incl_date]
                            i_base_rows = idx_series[idx_series.index <= incl_date]
                            if not s_base_rows.empty and not i_base_rows.empty:
                                s_base = float(s_base_rows.iloc[-1]['Close'])
                                i_base = float(i_base_rows.iloc[-1])
                                s_last = float(price_df.iloc[-1]['Close'])
                                i_last = float(idx_series.iloc[-1])
                                if s_base > 0 and i_base > 0:
                                    rsi = ((s_last / s_base) - (i_last / i_base)) * 100
                    except Exception:
                        pass

                stocks_info.append({
                    'code': code,
                    'name': stock_name,
                    'sector': sector if sector else 'N/A',
                    'market_cap': market_cap_billions,
                    'weight': weight,
                    'weight_prev': weight_prev,
                    'today_return': today_return,
                    'contribution': contribution,
                    'cumulative_return': cumulative_return,
                    'current_price': current_price,
                    'ath_price': ath_price,
                    'dd': dd,
                    'rsi': rsi,
                    'is_today_new': is_today_new
                })

                new_str = " [신규]" if is_today_new else ""
                return_str = f"{today_return:+.2f}%" if today_return is not None else "-"
                contribution_str = f"{contribution:+.2f}" if contribution is not None else "-"
                cumulative_str = f"{cumulative_return:+.2f}%" if cumulative_return is not None else "-"
                dd_str = f"{dd:.1f}%" if dd is not None else "-"
                print(f"   - {stock_name} ({code}){new_str}: {sector}, {market_cap_billions:,.0f}억원, {weight}%, 오늘: {return_str}, 기여도: {contribution_str}, 누적: {cumulative_str}, DD: {dd_str}")

            portfolio_data[display_name] = stocks_info

        # 당일 finalize된 주문 변경 내역 (다음 거래일 표·메시지 반영 예정) — /update 메시지에서 사용
        order_changes = {c['display_name']: c['order_change'] for c in portfolio_configs if c.get('order_change')}
        if order_changes:
            portfolio_data['_order_changes'] = order_changes

        # JSON 파일로 저장
        print(f"\n5. 결과 저장 중... ({OUTPUT_FILE})")
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(portfolio_data, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 완료! 총 {len(portfolio_data)}개 포트폴리오 처리됨")
        return portfolio_data

    except Exception as e:
        print(f"\n❌ 에러 발생: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    create_portfolio_tables()
