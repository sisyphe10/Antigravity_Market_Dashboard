import pandas as pd
import FinanceDataReader as fdr
import sys
import json
from pathlib import Path

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
    '목표전환형': 'DB 목표전환형'
}

# 주요 종목 섹터 매핑 (수동)
SECTOR_MAPPING = {
    '005930': '반도체',
    '000660': '반도체',
    '352820': '엔터테인먼트',
    '277810': '로봇/자동화',
    '001040': '식품/유통',
    '000150': '중공업',
    '034020': '에너지',
    '006800': '증권',
    '010060': '화학',
    '241560': '건설기계',
    '101490': '전기전자',
    '036810': '반도체장비',
    '006400': '2차전지',
    '034230': '호텔/레저',
    '017800': '기계',
    '003230': '식품',
    '033780': '담배/식음료',
    '196170': '의료기기',
}

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

def get_stock_info(stock_code):
    """종목 코드로 섹터와 시가총액 정보 가져오기"""
    try:
        # 종목 코드를 6자리로 포맷
        code = str(stock_code).zfill(6)

        # FinanceDataReader로 종목 정보 가져오기
        # KRX 상장 종목 리스트
        krx = fdr.StockListing('KRX')
        stock_info = krx[krx['Code'] == code]

        if not stock_info.empty:
            sector = stock_info.iloc[0].get('Sector', 'N/A')
            market_cap = stock_info.iloc[0].get('Marcap', 0)

            # 시가총액을 억 원 단위로 변환
            market_cap_billions = market_cap / 100000000 if market_cap else 0

            return {
                'sector': sector if sector else 'N/A',
                'market_cap': market_cap_billions
            }
        else:
            return {'sector': 'N/A', 'market_cap': 0}
    except Exception as e:
        print(f"  Warning: Could not fetch info for {stock_code}: {e}")
        return {'sector': 'N/A', 'market_cap': 0}

def get_today_return(code):
    """종목의 오늘 수익률 계산"""
    try:
        from datetime import timedelta

        # 최근 5일 데이터 가져오기
        end_date = pd.Timestamp.now()
        start_date = end_date - timedelta(days=5)

        df = fdr.DataReader(code, start=start_date)

        if len(df) < 2:
            return None

        # 최신 종가와 전일 종가
        latest_price = df.iloc[-1]['Close']
        prev_price = df.iloc[-2]['Close']

        # 수익률 계산
        return_pct = ((latest_price - prev_price) / prev_price) * 100

        return return_pct

    except Exception as e:
        print(f"  Warning: Could not fetch today's return for {code}: {e}")
        return None

def calculate_cumulative_return(code, stock_name, portfolio_name='트루밸류'):
    """
    종목의 누적 수익률 계산

    Returns:
        dict: {
            'cumulative_return': float or None,
            'status': str ('2026_new', 'existing', 'resold'),
            'avg_price': float or None,
            'current_price': float or None
        }
    """
    try:
        from datetime import timedelta

        # 기존 종목인 경우 사용자 제공 값 반환 (목표전환형은 신규 펀드이므로 직접 계산)
        if code in EXISTING_STOCK_CUMULATIVE_RETURNS and portfolio_name != '목표전환형':
            return {
                'cumulative_return': EXISTING_STOCK_CUMULATIVE_RETURNS[code],
                'status': 'existing',
                'avg_price': None,
                'current_price': None
            }

        # NEW 시트에서 해당 종목의 거래 이력 가져오기
        df = pd.read_excel(WRAP_NAV_FILE, sheet_name='NEW')
        df['날짜'] = pd.to_datetime(df['날짜'])

        # 해당 포트폴리오의 해당 종목 이력
        stock_history = df[(df['상품명'] == portfolio_name) & (df['코드'] == int(code))].copy()
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
            # 마지막 전량 매도 이후 데이터
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

        # 각 매수 시점의 종가 가져오기
        weighted_sum = 0
        total_weight = 0

        for _, row in purchases.iterrows():
            purchase_date = row['날짜']
            weight = row['비중']

            # 해당 날짜의 종가 가져오기
            try:
                # 해당 날짜 전후 5일 데이터 가져오기
                start_date = purchase_date - timedelta(days=5)
                end_date = purchase_date + timedelta(days=2)

                price_data = fdr.DataReader(code, start=start_date, end=end_date)

                if price_data.empty:
                    continue

                # 해당 날짜 또는 가장 가까운 날짜의 종가
                if purchase_date in price_data.index:
                    close_price = price_data.loc[purchase_date, 'Close']
                else:
                    # 가장 가까운 이전 날짜의 종가
                    available_dates = price_data[price_data.index <= purchase_date]
                    if not available_dates.empty:
                        close_price = available_dates.iloc[-1]['Close']
                    else:
                        # 이후 날짜 중 가장 가까운 날짜
                        close_price = price_data.iloc[0]['Close']

                weighted_sum += close_price * weight
                total_weight += weight

            except Exception as e:
                print(f"    Warning: Could not fetch price for {stock_name} on {purchase_date}: {e}")
                continue

        if total_weight == 0:
            return {'cumulative_return': None, 'status': 'no_valid_prices', 'avg_price': None, 'current_price': None}

        # 가중 평단가 계산
        avg_price = weighted_sum / total_weight

        # 현재가 가져오기
        try:
            current_data = fdr.DataReader(code, start=pd.Timestamp.now() - timedelta(days=5))
            if current_data.empty:
                return {'cumulative_return': None, 'status': 'no_current_price', 'avg_price': avg_price, 'current_price': None}

            current_price = current_data.iloc[-1]['Close']

            # 누적 수익률 계산
            cumulative_return = (current_price / avg_price - 1) * 100

            return {
                'cumulative_return': cumulative_return,
                'status': status,
                'avg_price': avg_price,
                'current_price': current_price,
                'first_date': first_date
            }

        except Exception as e:
            print(f"    Warning: Could not fetch current price for {stock_name}: {e}")
            return {'cumulative_return': None, 'status': 'no_current_price', 'avg_price': avg_price, 'current_price': None}

    except Exception as e:
        print(f"    Error calculating cumulative return for {stock_name}: {e}")
        import traceback
        traceback.print_exc()
        return {'cumulative_return': None, 'status': 'error', 'avg_price': None, 'current_price': None}

def create_portfolio_tables():
    """포트폴리오 테이블 데이터 생성"""
    print("1. Wrap NAV 파일 읽기...")

    try:
        # NEW 시트에서 포트폴리오 데이터 읽기
        df = pd.read_excel(WRAP_NAV_FILE, sheet_name='NEW')

        print(f"   전체 날짜 범위: {df['날짜'].min()} ~ {df['날짜'].max()}")

        # KRX 종목 리스트 미리 로드
        print("2. KRX 종목 리스트 로드 중...")
        krx = fdr.StockListing('KRX')

        # 포트폴리오별 데이터 생성
        portfolio_data = {}

        # 동일한 포트폴리오 그룹 정의
        same_portfolios = ['트루밸류', 'Value ESG', '개방형 랩']
        combined_name = '삼성 트루밸류 / NH Value ESG / DB 개방형'

        processed = set()

        # 모든 포트폴리오 이름 가져오기
        all_portfolios = df['상품명'].unique()

        for portfolio_name in all_portfolios:
            # 이미 처리된 포트폴리오는 스킵
            if portfolio_name in processed:
                continue

            # 동일한 포트폴리오 3개는 하나로 합치기
            if portfolio_name in same_portfolios:
                display_name = combined_name
                # 첫 번째 포트폴리오 데이터만 사용 (어차피 동일)
                use_portfolio = '트루밸류'
                # 나머지는 처리됨으로 표시
                processed.update(same_portfolios)
            else:
                display_name = PORTFOLIO_DISPLAY_NAMES.get(portfolio_name, portfolio_name)
                use_portfolio = portfolio_name
                processed.add(portfolio_name)

            print(f"\n3. {display_name} 포트폴리오 처리 중...")

            # 해당 포트폴리오의 최신 날짜 데이터
            portfolio_df = df[df['상품명'] == use_portfolio].copy()
            if portfolio_df.empty:
                continue

            latest_portfolio_date = portfolio_df['날짜'].max()
            portfolio_stocks = portfolio_df[portfolio_df['날짜'] == latest_portfolio_date].copy()

            print(f"   최신 날짜: {latest_portfolio_date}")

            # 비중이 0인 종목 제외
            portfolio_stocks = portfolio_stocks[portfolio_stocks['비중'] > 0]

            # 비중 순으로 정렬
            portfolio_stocks = portfolio_stocks.sort_values('비중', ascending=False)

            # 각 종목에 대해 정보 수집
            stocks_info = []
            for idx, row in portfolio_stocks.iterrows():
                code = str(row['코드']).zfill(6)
                stock_name = row['종목']
                weight = row['비중']

                # 종목 정보 가져오기
                stock_data = krx[krx['Code'] == code]

                if not stock_data.empty:
                    # 섹터는 수동 매핑 사용
                    sector = SECTOR_MAPPING.get(code, '기타')
                    market_cap = stock_data.iloc[0].get('Marcap', 0)
                    market_cap_billions = market_cap / 100000000 if market_cap else 0
                else:
                    sector = '기타'
                    market_cap_billions = 0

                # 오늘 수익률 계산
                today_return = get_today_return(code)

                # 누적 수익률 계산
                cumulative_result = calculate_cumulative_return(code, stock_name, use_portfolio)
                cumulative_return = cumulative_result.get('cumulative_return')

                stocks_info.append({
                    'code': code,
                    'name': stock_name,
                    'sector': sector if sector else 'N/A',
                    'market_cap': market_cap_billions,
                    'weight': weight,
                    'today_return': today_return,
                    'cumulative_return': cumulative_return
                })

                return_str = f"{today_return:+.2f}%" if today_return is not None else "N/A"
                cumulative_str = f"{cumulative_return:+.2f}%" if cumulative_return is not None else "N/A"
                print(f"   - {stock_name} ({code}): {sector}, {market_cap_billions:,.0f}억원, {weight}%, 오늘: {return_str}, 누적: {cumulative_str}")

            portfolio_data[display_name] = stocks_info

        # JSON 파일로 저장
        print(f"\n4. 결과 저장 중... ({OUTPUT_FILE})")
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
