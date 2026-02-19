"""
누적 수익률 계산 로직 테스트
"""
import pandas as pd
import FinanceDataReader as fdr
import sys
from datetime import timedelta

sys.stdout.reconfigure(encoding='utf-8')

WRAP_NAV_FILE = 'Wrap_NAV.xlsx'

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


# 테스트
if __name__ == "__main__":
    print("=== 누적 수익률 계산 테스트 ===\n")

    # 테스트할 종목들
    test_stocks = [
        ('005930', '삼성전자'),  # 기존 보유
        ('277810', '레인보우로보틱스'),  # 2026 신규
        ('006400', '삼성SDI'),  # 2026 신규
        ('000660', 'SK하이닉스'),  # 기존 보유
    ]

    existing_stocks = []
    new_stocks_results = []

    for code, name in test_stocks:
        print(f"\n{name} ({code}) 분석 중...")
        result = calculate_cumulative_return(code, name)

        print(f"  상태: {result['status']}")

        if result['status'] == 'existing':
            print(f"  → 기존 보유 종목 (첫 등장: {result['first_date'].strftime('%Y-%m-%d')})")
            print(f"  → 누적 수익률: 공란 처리")
            existing_stocks.append(name)
        elif result['cumulative_return'] is not None:
            print(f"  가중 평단가: {result['avg_price']:,.0f}원")
            print(f"  현재가: {result['current_price']:,.0f}원")
            print(f"  누적 수익률: {result['cumulative_return']:+.2f}%")
            new_stocks_results.append((name, result['cumulative_return']))
        else:
            print(f"  → 계산 불가 (이유: {result['status']})")

    print("\n\n=== 요약 ===")
    print(f"\n기존 보유 종목 (공란 처리): {len(existing_stocks)}개")
    for stock in existing_stocks:
        print(f"  - {stock}")

    print(f"\n2026 신규 종목 (계산 완료): {len(new_stocks_results)}개")
    for stock, ret in new_stocks_results:
        print(f"  - {stock}: {ret:+.2f}%")
