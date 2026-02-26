import pandas as pd
import FinanceDataReader as fdr
import sys
import json
from pathlib import Path
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# Windows console encoding fix
sys.stdout.reconfigure(encoding='utf-8')

# Constants
WRAP_NAV_FILE = 'Wrap_NAV.xlsx'
OUTPUT_FILE = 'portfolio_data.json'

# 포트폴리오 표시 이름 매핑
PORTFOLIO_DISPLAY_NAMES = {
    '트루밸류': '삼성 트루밸류',
    'Value ESG': 'NH Value ESG',
    '개방형 랩': 'DB 개방형',
    # '목표전환형': 'DB 목표전환형',  # 1차 완료 (6% 목표달성, 2026-02-25 청산)
}

# 표시 제외 포트폴리오 (역사 데이터는 보존하되 대시보드에서 숨김)
EXCLUDED_PORTFOLIOS = {'목표전환형'}

# 기존 종목 누적 수익률 매핑 (사용자 제공 값)
EXISTING_STOCK_CUMULATIVE_RETURNS = {
    '005930': 200.0,  # 삼성전자
    '000660': 203.0,  # SK하이닉스
    '352820': 70.0,   # 하이브
    '000150': 1.0,    # 두산
    '034020': 42.0,   # 두산에너빌리티
    '006800': 150.0,  # 미래에셋증권
    '001040': 88.0,   # CJ
    '010060': 55.0,   # OCI홀딩스
}


def fetch_price_data(code):
    """종목의 최근 가격 데이터를 가져오기 (스레드에서 호출)"""
    try:
        end_date = pd.Timestamp.now()
        start_date = end_date - timedelta(days=90)  # 누적수익률 계산에도 사용하므로 넉넉히
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


def calculate_cumulative_return(code, stock_name, portfolio_name, nav_df, price_df):
    """
    종목의 누적 수익률 계산 (캐시된 데이터 사용)
    """
    try:
        # 기존 종목인 경우 사용자 제공 값 반환 (목표전환형은 신규 펀드이므로 직접 계산)
        if code in EXISTING_STOCK_CUMULATIVE_RETURNS and portfolio_name != '목표전환형':
            return {
                'cumulative_return': EXISTING_STOCK_CUMULATIVE_RETURNS[code],
                'status': 'existing',
                'avg_price': None,
                'current_price': None
            }

        # 해당 포트폴리오의 해당 종목 이력
        stock_history = nav_df[(nav_df['상품명'] == portfolio_name) & (nav_df['코드'] == int(code))].copy()
        stock_history = stock_history.sort_values('날짜')

        if stock_history.empty:
            return {'cumulative_return': None, 'status': 'not_found', 'avg_price': None, 'current_price': None}

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
                'first_date': first_date
            }

        # 비중이 0이 아닌 매수 데이터만 추출
        purchases = stock_history[stock_history['비중'] > 0].copy()

        if purchases.empty:
            return {'cumulative_return': None, 'status': 'no_purchases', 'avg_price': None, 'current_price': None}

        # 오늘 처음 편입된 종목은 수익률 미표시
        today_norm = pd.Timestamp.now().normalize()
        if purchases['날짜'].min() >= today_norm:
            return {'cumulative_return': None, 'status': 'today_new', 'avg_price': None, 'current_price': None}

        # 캐시된 가격 데이터가 없으면 계산 불가
        if price_df is None or price_df.empty:
            return {'cumulative_return': None, 'status': 'no_price_data', 'avg_price': None, 'current_price': None}

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
            return {'cumulative_return': None, 'status': 'no_valid_prices', 'avg_price': None, 'current_price': None}

        avg_price = weighted_sum / total_weight
        current_price = price_df.iloc[-1]['Close']
        cumulative_return = (current_price / avg_price - 1) * 100

        return {
            'cumulative_return': cumulative_return,
            'status': status,
            'avg_price': avg_price,
            'current_price': current_price,
            'first_date': first_date
        }

    except Exception as e:
        print(f"    Error calculating cumulative return for {stock_name}: {e}")
        import traceback
        traceback.print_exc()
        return {'cumulative_return': None, 'status': 'error', 'avg_price': None, 'current_price': None}


def create_portfolio_tables():
    """포트폴리오 테이블 데이터 생성"""
    print("1. Wrap NAV 파일 읽기...")

    try:
        # NEW 시트에서 포트폴리오 데이터 읽기 (1회만)
        nav_df = pd.read_excel(WRAP_NAV_FILE, sheet_name='NEW')
        nav_df['날짜'] = pd.to_datetime(nav_df['날짜'])

        print(f"   전체 날짜 범위: {nav_df['날짜'].min()} ~ {nav_df['날짜'].max()}")

        # KRX 종목 리스트 미리 로드
        print("2. KRX 종목 리스트 로드 중...")
        krx = fdr.StockListing('KRX')

        # Code 시트에서 FICS 섹터 매핑 로드
        code_df = pd.read_excel(WRAP_NAV_FILE, sheet_name='Code')
        code_df['종목코드'] = code_df['종목코드'].apply(lambda x: str(x).zfill(6))
        sector_map = dict(zip(code_df['종목코드'], code_df['섹터']))

        # === 전체 종목 코드 수집 (중복 제거) ===
        same_portfolios = ['트루밸류', 'Value ESG', '개방형 랩']
        combined_name = '삼성 트루밸류 / NH Value ESG / DB 개방형'
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

            if portfolio_name in same_portfolios:
                display_name = combined_name
                use_portfolio = '트루밸류'
                processed.update(same_portfolios)
            else:
                display_name = PORTFOLIO_DISPLAY_NAMES.get(portfolio_name, portfolio_name)
                use_portfolio = portfolio_name
                processed.add(portfolio_name)

            portfolio_df = nav_df[nav_df['상품명'] == use_portfolio].copy()
            if portfolio_df.empty:
                continue

            available_dates = sorted(portfolio_df['날짜'].unique())
            # 23:00 이전에는 당일 주문 제외 (결제는 익일 반영)
            _now = pd.Timestamp.now()
            _date_cutoff = _now.normalize() if _now.hour >= 23 else _now.normalize() - pd.Timedelta(days=1)
            prev_dates = [d for d in available_dates if d <= _date_cutoff]
            if prev_dates:
                latest_portfolio_date = prev_dates[-1]
            else:
                latest_portfolio_date = available_dates[-1]

            portfolio_stocks = portfolio_df[portfolio_df['날짜'] == latest_portfolio_date].copy()
            portfolio_stocks = portfolio_stocks[portfolio_stocks['비중'] > 0]
            portfolio_stocks = portfolio_stocks.sort_values('비중', ascending=False)

            codes_in_portfolio = [str(row['코드']).zfill(6) for _, row in portfolio_stocks.iterrows()]
            all_codes.update(codes_in_portfolio)

            portfolio_configs.append({
                'display_name': display_name,
                'use_portfolio': use_portfolio,
                'latest_date': latest_portfolio_date,
                'stocks': portfolio_stocks,
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
            latest_portfolio_date = config['latest_date']
            portfolio_stocks = config['stocks']

            print(f"\n4. {display_name} 포트폴리오 처리 중...")
            print(f"   기준 날짜: {latest_portfolio_date} (전거래일)")

            stocks_info = []
            for idx, row in portfolio_stocks.iterrows():
                code = str(row['코드']).zfill(6)
                stock_name = row['종목']
                weight = row['비중']

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
                    contribution = (weight / 100) * (today_return / 100) * 1000 if today_return is not None else None

                stocks_info.append({
                    'code': code,
                    'name': stock_name,
                    'sector': sector if sector else 'N/A',
                    'market_cap': market_cap_billions,
                    'weight': weight,
                    'today_return': today_return,
                    'contribution': contribution,
                    'cumulative_return': cumulative_return,
                    'is_today_new': is_today_new
                })

                new_str = " [신규]" if is_today_new else ""
                return_str = f"{today_return:+.2f}%" if today_return is not None else "-"
                contribution_str = f"{contribution:+.2f}" if contribution is not None else "-"
                cumulative_str = f"{cumulative_return:+.2f}%" if cumulative_return is not None else "-"
                print(f"   - {stock_name} ({code}){new_str}: {sector}, {market_cap_billions:,.0f}억원, {weight}%, 오늘: {return_str}, 기여도: {contribution_str}, 누적: {cumulative_str}")

            portfolio_data[display_name] = stocks_info

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
