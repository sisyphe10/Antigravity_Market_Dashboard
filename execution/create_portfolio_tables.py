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

# 단일 출처 레지스트리 (execution/wrap_config.py)
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wrap_config

# Constants
WRAP_NAV_FILE = 'Wrap_NAV.xlsx'
OUTPUT_FILE = 'portfolio_data.json'
EXISTING_STOCK_BASIS_FILE = 'existing_stock_basis.json'

# 포트폴리오 표시 이름 매핑 — 단일 출처: execution/wrap_config.py
PORTFOLIO_DISPLAY_NAMES = wrap_config.portfolio_display_names()

# 표시 제외 포트폴리오 (역사 데이터 보존, 대시보드 숨김) — 비활성 상품 자동 파생
EXCLUDED_PORTFOLIOS = wrap_config.excluded_portfolios()

# 편입일 이전부터 보유 중인 종목의 평균 매수가 (existing_stock_basis.json 로드)
# 이후 누적 수익률은 (current_price / avg_price - 1) * 100 로 매일 계산
def _load_existing_stock_basis():
    try:
        with open(EXISTING_STOCK_BASIS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        prices = {code: info['avg_price'] for code, info in data.get('stocks', {}).items()}
        basis_date = pd.to_datetime(data['basis_date']) if data.get('basis_date') else None
        return prices, basis_date
    except Exception as e:
        print(f"  Warning: {EXISTING_STOCK_BASIS_FILE} 로드 실패: {e}")
        return {}, None

# EXISTING_STOCK_AVG_PRICES: 추적 개시 전부터 보유 중인 종목의 고정 평균 매수가.
# EXISTING_BASIS_DATE: 그 기준가가 유효한 날짜(basis_date). 이 날짜 이후 신규 편입한
# 포트폴리오는 고정 basis가 아니라 자기 편입 시점부터 직접 계산해야 한다(포트별 편입가 반영).
EXISTING_STOCK_AVG_PRICES, EXISTING_BASIS_DATE = _load_existing_stock_basis()


def _load_naver_meta():
    """네이버 증권 시가총액 순위 페이지 → {code: {'marcap': 억원 int, 'market': 'KOSPI'|'KOSDAQ'}}"""
    meta_map = {}
    try:
        for sosok, market in ((0, 'KOSPI'), (1, 'KOSDAQ')):
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
                        meta_map[code] = {'marcap': int(marcap_text), 'market': market}
                    except ValueError:
                        pass
                    found += 1
                if found == 0:
                    break
        print(f"  네이버 시가총액: {len(meta_map)}개 종목")
    except Exception as e:
        print(f"  Warning: 네이버 시가총액 로드 실패: {e}")
    return meta_map


def _load_fdr_listing_meta():
    """FDR 종목 리스팅(KRX → KRX-DESC) → {code: {'marcap': 억원, 'market': str}}. 실패 시 빈 dict.
    (data.krx가 클라우드 IP를 차단하는 환경에서는 둘 다 실패할 수 있다 → 호출측이 네이버 폴백)"""
    for listing_type in ['KRX', 'KRX-DESC']:
        try:
            print(f"  {listing_type} 시도...")
            krx = fdr.StockListing(listing_type)
            if krx is None or len(krx) == 0 or 'Code' not in krx.columns:
                print(f"  Warning: {listing_type} 결과 비어있음")
                continue
            has_marcap = 'Marcap' in krx.columns
            meta = {}
            for _, r in krx.iterrows():
                code = str(r['Code']).zfill(6)
                marcap = 0
                if has_marcap and pd.notna(r.get('Marcap')) and r.get('Marcap'):
                    marcap = float(r['Marcap']) / 100000000  # 원 → 억원
                meta[code] = {
                    'marcap': marcap,
                    'market': str(r.get('Market', '') or '').upper(),
                }
            print(f"  → {len(meta)}개 종목 (Marcap: {'O' if has_marcap else 'X'})")
            return meta
        except Exception as e:
            print(f"  Warning: {listing_type} 로드 실패: {e}")
    return {}


def load_stock_meta(codes):
    """종목 시가총액(억원)·시장구분(RSI 지수 매핑용) 확보 — KIS 우선 → FDR 리스팅 → 네이버.
    반환: {code: {'marcap': float(억원), 'market': str}}. 어떤 실패에서도 예외를 올리지 않는다.
    (2026-07-07 data.krx의 GHA IP 차단으로 시총 0·RSI null 전멸 → KIS 전환. 네이버 폴백은
    과거 빈 리스팅 프레임 위에 매핑되어 무효화되던 버그를 dict 직접 사용으로 수정.)"""
    codes = [c for c in dict.fromkeys(codes) if c]
    meta = {}

    def _still_missing():
        return [c for c in codes
                if c not in meta or not meta[c]['marcap'] or not meta[c]['market']]

    # 1) KIS (inquire_price: 시총 억원 + 대표시장명 — VM/GHA/로컬 공통 동작)
    try:
        import kis_marcap
        kis_meta = kis_marcap.fetch_stock_meta(codes)
        for c, m in kis_meta.items():
            meta[c] = {'marcap': m.get('marcap', 0), 'market': m.get('market', '')}
        print(f"  KIS 시가총액/시장구분: {len(kis_meta)}/{len(codes)}종목")
    except Exception as e:
        print(f"  Warning: KIS 시가총액 조회 실패: {e}")

    # 2) FDR 리스팅 폴백 — KIS 미확보분만 보충 (전부 확보됐으면 스킵)
    if _still_missing():
        fdr_meta = _load_fdr_listing_meta()
        for c in _still_missing():
            f = fdr_meta.get(c)
            if not f:
                continue
            cur = meta.setdefault(c, {'marcap': 0, 'market': ''})
            if not cur['marcap'] and f['marcap']:
                cur['marcap'] = f['marcap']
            if not cur['market'] and f['market']:
                cur['market'] = f['market']

    # 3) 네이버 폴백 — 코드→값 dict 직접 병합
    if _still_missing():
        naver = _load_naver_meta()
        for c in _still_missing():
            n = naver.get(c)
            if not n:
                continue
            cur = meta.setdefault(c, {'marcap': 0, 'market': ''})
            if not cur['marcap'] and n['marcap']:
                cur['marcap'] = n['marcap']
            if not cur['market'] and n['market']:
                cur['market'] = n['market']

    got_mc = sum(1 for c in codes if meta.get(c, {}).get('marcap'))
    got_mk = sum(1 for c in codes if meta.get(c, {}).get('market'))
    print(f"  확보: 시가총액 {got_mc}/{len(codes)}, 시장구분 {got_mk}/{len(codes)}")
    return meta


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


def find_current_run_start(code, portfolio_name, nav_df):
    """현재 연속 보유 구간(run)의 시작일 반환.
    NEW 시트는 리밸런싱일마다 '전체 보유 종목 스냅샷'이므로, 어떤 리밸런싱일에
    종목이 빠져 있으면(=비중 0 행이 없더라도) 그날 매도된 것으로 본다.
    명시적 비중=0 행도 부재로 처리. 따라서 '매도 후 재편입'(라운드트립) 시
    직전 보유분 매수가가 원가에 섞이지 않고, 마지막 재편입일부터 다시 측정한다."""
    try:
        port = nav_df[nav_df['상품명'] == portfolio_name]
        if port.empty:
            return None
        all_dates = sorted(pd.to_datetime(port['날짜'].unique()))
        present = set(pd.to_datetime(
            port[(port['코드'] == int(code)) & (port['비중'] > 0)]['날짜']))
        if not present:
            return None
        run_start = None
        for d in reversed(all_dates):
            if d in present:
                run_start = d
            else:
                break
        return run_start
    except Exception:
        return None


def get_inclusion_date(code, portfolio_name, nav_df):
    """포트폴리오 NAV 이력에서 종목 편입일(현재 연속 보유 구간 시작일) 반환.
    RSI '편입 이후' 기준점으로 사용 — 누적수익률 기준점(run_start)과 동일.
    추적 개시 전부터 보유한 기존 종목은 NAV 첫 등장일을 자동 반환."""
    return find_current_run_start(code, portfolio_name, nav_df)


def calculate_cumulative_return(code, stock_name, portfolio_name, nav_df, price_df):
    """
    종목의 누적 수익률 계산 (캐시된 데이터 사용)
    """
    try:
        # 현재 연속 보유 구간(run) 시작일 — (상품명, 코드) 단위. 포트폴리오별 편입 시점/라운드트립 반영.
        run_start = find_current_run_start(code, portfolio_name, nav_df)

        # 편입일 이전부터 보유 중인 종목: existing_stock_basis.json 의 avg_price로 매일 재계산.
        # 단, 그 고정 basis(2026-02-12 등)는 추적 개시 전부터 '연속 보유 중'인 포트폴리오에만 유효하다.
        # basis_date 이후 신규 편입한 포트폴리오(신규 펀드·라운드트립 재편입)는 자기 편입 시점부터
        # 직접 계산해야 포트별로 다른 누적수익률이 나온다 → 고정 basis 미적용.
        # (목표전환형 시리즈는 신규 펀드이므로 애초에 직접 계산 경로로)
        held_since_before_basis = (
            EXISTING_BASIS_DATE is None
            or (run_start is not None and run_start <= EXISTING_BASIS_DATE)
        )
        if (code in EXISTING_STOCK_AVG_PRICES
                and not portfolio_name.startswith('목표전환형')
                and held_since_before_basis):
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

        # run_start(현재 연속 보유 구간 시작일)은 함수 상단에서 이미 계산됨.
        # NEW 시트 스냅샷에서 '부재(매도)'도 경계로 인식 → 라운드트립 재편입 시 직전 매수가 혼입 방지.
        if run_start is None:
            return {'cumulative_return': None, 'status': 'no_purchases', 'avg_price': None, 'current_price': None, 'dd': None, 'all_time_high': None}

        # 현재 run 이후 데이터만 사용 (직전 라운드트립 매수가 혼입 방지)
        stock_history = stock_history[stock_history['날짜'] >= run_start]
        if run_start > first_date:
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

        # 원가법 평균단가 (2026-07-08 산식 교정): 리밸런싱 스냅포트 행을 전부 '매수'로
        # 평균내던 옛 방식은 비중이 불변이어도 이후 스냅샷 종가가 원가에 섞여 수익률을
        # 희석시켰다(테크윙: 실제 -29.6% → -16.1% 표시). 이제 **비중 증가분(delta)만**
        # 그 날짜 종가로 추가 매수로 반영하고, 비중 불변·감소 시 평균단가는 유지한다
        # (매도는 평균단가를 바꾸지 않는 표준 원가법).
        avg_price = None
        pos_weight = 0.0

        for _, row in purchases.iterrows():
            purchase_date = row['날짜']
            weight = float(row['비중'])
            delta = weight - pos_weight

            if delta > 1e-9:  # 비중 비교 엡실론 — 주문변경 diff와 동일 컨벤션
                try:
                    if purchase_date in price_df.index:
                        close_price = price_df.loc[purchase_date, 'Close']
                    else:
                        available_dates = price_df[price_df.index <= purchase_date]
                        if not available_dates.empty:
                            close_price = available_dates.iloc[-1]['Close']
                        else:
                            close_price = price_df.iloc[0]['Close']

                    if avg_price is None or pos_weight <= 0:
                        avg_price = float(close_price)
                    else:
                        avg_price = (avg_price * pos_weight + float(close_price) * delta) / weight
                    pos_weight = weight  # 단가 확보 성공 시에만 전진
                except Exception as e:
                    print(f"    Warning: Could not get price for {stock_name} on {purchase_date}: {e}")
                    # 단가 확보 실패 → pos_weight도 유지. 실패한 증가분은 다음 성공하는
                    # 증가 시점의 delta에 합산돼 만회된다 (유령 비중으로 원가가 조용히
                    # 대체되는 것 방지 — codex 리뷰 지적).
            else:
                pos_weight = weight  # 비중 유지/감소는 가격 불필요 — 항상 갱신 (원가 불변)

        if avg_price is None:
            return {'cumulative_return': None, 'status': 'no_valid_prices', 'avg_price': None, 'current_price': None, 'dd': None, 'all_time_high': None}
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
        # KOSPI/KOSDAQ는 기준가 시트(KIS 확정지수) 우선 — 야후 ^KS11/^KQ11 지연·잠정값 회피.
        # 실패한 지수만 야후 폴백(data.krx LOGOUT 차단으로 fdr 불가).
        INDEX_PRICE_SERIES = {'KOSPI': None, 'KOSDAQ': None}
        try:
            _nav = pd.read_excel(WRAP_NAV_FILE, sheet_name='기준가')
            _nav.columns = [str(c).strip() for c in _nav.columns]
            if 'Date' in _nav.columns:
                _nav['Date'] = pd.to_datetime(_nav['Date'])
                _nav = _nav.set_index('Date').sort_index()
                for mkt in ('KOSPI', 'KOSDAQ'):
                    if mkt in _nav.columns:
                        s = _nav[mkt].dropna()
                        s.index = s.index.normalize()
                        INDEX_PRICE_SERIES[mkt] = s if not s.empty else None
                        print(f"  지수 {mkt} (KIS 기준가): {len(s)}일 (RSI 편입 이후 기준)")
        except Exception as e:
            print(f"  Warning: 기준가 시트 로드 실패 → 야후 폴백: {e}")
        _missing = [m for m in ('KOSPI', 'KOSDAQ') if INDEX_PRICE_SERIES[m] is None]
        if _missing:
            try:
                import yfinance as yf
                _idx_start = (pd.Timestamp.now() - pd.DateOffset(years=3)).strftime('%Y-%m-%d')
                _tk = {'KOSPI': '^KS11', 'KOSDAQ': '^KQ11'}
                for mkt in _missing:
                    try:
                        closes = yf.Ticker(_tk[mkt]).history(start=_idx_start, auto_adjust=False)['Close'].dropna()
                        if getattr(closes.index, 'tz', None) is not None:
                            closes.index = closes.index.tz_localize(None)
                        closes.index = closes.index.normalize()
                        INDEX_PRICE_SERIES[mkt] = closes if not closes.empty else None
                        print(f"  지수 {mkt} (야후 폴백): {len(closes)}일 (RSI 편입 이후 기준)")
                    except Exception as e:
                        print(f"  Warning: 지수 {mkt} 야후 폴백 실패 (RSI 미표시): {e}")
            except Exception as e:
                print(f"  Warning: yfinance import 실패 (RSI 미표시): {e}")

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

        # === 포트폴리오 그룹 정의 (동일 종목/비중 합쳐 표시) — 단일 출처: execution/wrap_config.py ===
        # sources: nav_key / combined: 결합 표시명 / use: 대표 nav_key (활성 멤버 있는 그룹만 생성)
        PORTFOLIO_GROUPS = wrap_config.portfolio_groups()

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
            _today_norm = pd.Timestamp(today_date).normalize()
            if (not dates_lt_today) and (_today_norm == _today_kst) and today_comp:
                # 오늘 신규 개시된 펀드 (전일 구성 자체가 없음) — 전체 구성을 신규로 표시.
                # 일반 diff는 today_date>disp_date를 요구하나, 개시일엔 disp_date가 today로 폴백돼 잡히지 않음.
                added = sorted(
                    ({'name': info['name'], 'weight': info['weight']} for info in today_comp.values()),
                    key=lambda x: x['weight'], reverse=True)
                order_change = {
                    'date': _today_norm.strftime('%Y-%m-%d'),
                    'added': added, 'changed': [], 'removed': [], 'new_fund': True,
                }
            elif today_date > disp_date:
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

        # === 종목 시가총액/시장구분 로드 (KIS 우선 → FDR 리스팅 → 네이버) ===
        print(f"\n2. {len(all_codes)}개 종목 시가총액/시장구분 로드 중 (KIS 우선)...")
        stock_meta = load_stock_meta(sorted(all_codes))

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

                smeta = stock_meta.get(code) or {}
                sector = sector_map.get(code, '기타')
                if pd.isna(sector):
                    sector = '기타'

                market_cap_billions = smeta.get('marcap', 0) or 0

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
                        market = str(smeta.get('market', '') or '').upper()
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

        # 포트폴리오 단위 YTD·누적수익률(기준가 기반, 전일까지 확정분) — /update 메시지에서 오늘 실시간 등락과 복리 결합해 표시.
        # · nav_ytd_d1: 레지스트리 base_price 기준(일반형=전략 리셋일 2025-12-30 값, 목표전환형=개시일 1000) = 대시보드 YTD/RETURN 표와 동일.
        # · nav_cum_d1: 기준가 컬럼 최초값(설정일 1000) 기준 = 펀드 전체 운용기간 누적.
        #   (목표전환형은 개시=연초라 YTD==누적으로 동일값)
        # 오늘 개시 펀드(기준가 컬럼 없음)는 None → 봇에서 0으로 보고 오늘 등락만 반영.
        portfolio_meta = {}
        try:
            base_map = {p.nav_key: p.base_price for p in wrap_config.PRODUCTS}
            nav_px = pd.read_excel(WRAP_NAV_FILE, sheet_name='기준가')
            nav_px.columns = [str(c).strip() for c in nav_px.columns]
            if 'Date' in nav_px.columns:
                nav_px['Date'] = pd.to_datetime(nav_px['Date'])
                nav_px = nav_px.set_index('Date').sort_index()
                for cfg in portfolio_configs:
                    disp = cfg['display_name']
                    nav_key = cfg['use_portfolio']
                    ytd_base = base_map.get(nav_key)
                    nav_ytd_d1 = None
                    nav_cum_d1 = None
                    if nav_key in nav_px.columns:
                        full = nav_px[nav_key].dropna()
                        col = full[full.index < _today_kst]  # 전일(D-1)까지 확정분만
                        if not col.empty:
                            last = float(col.iloc[-1])
                            if ytd_base:
                                nav_ytd_d1 = (last / ytd_base - 1) * 100
                            incep_base = float(full.iloc[0])  # 설정일 기준가(최초 유효값)
                            if incep_base:
                                nav_cum_d1 = (last / incep_base - 1) * 100
                    portfolio_meta[disp] = {'nav_ytd_d1': nav_ytd_d1, 'nav_cum_d1': nav_cum_d1}
        except Exception as e:
            print(f"  Warning: _portfolio_meta(YTD/누적수익률) 계산 실패: {e}")
        if portfolio_meta:
            portfolio_data['_portfolio_meta'] = portfolio_meta

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
