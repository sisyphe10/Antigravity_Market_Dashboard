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

def create_portfolio_tables():
    """포트폴리오 테이블 데이터 생성"""
    print("1. Wrap NAV 파일 읽기...")

    try:
        # NEW 시트에서 포트폴리오 데이터 읽기
        df = pd.read_excel(WRAP_NAV_FILE, sheet_name='NEW')

        # 최신 날짜 데이터만 가져오기
        latest_date = df['날짜'].max()
        df_latest = df[df['날짜'] == latest_date].copy()

        print(f"   최신 날짜: {latest_date.strftime('%Y-%m-%d')}")

        # KRX 종목 리스트 미리 로드
        print("2. KRX 종목 리스트 로드 중...")
        krx = fdr.StockListing('KRX')

        # 포트폴리오별 데이터 생성
        portfolio_data = {}

        for portfolio_name in df_latest['상품명'].unique():
            display_name = PORTFOLIO_DISPLAY_NAMES.get(portfolio_name, portfolio_name)
            print(f"\n3. {display_name} 포트폴리오 처리 중...")

            # 해당 포트폴리오의 종목들
            portfolio_stocks = df_latest[df_latest['상품명'] == portfolio_name].copy()

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

                stocks_info.append({
                    'code': code,
                    'name': stock_name,
                    'sector': sector if sector else 'N/A',
                    'market_cap': market_cap_billions,
                    'weight': weight
                })

                print(f"   - {stock_name} ({code}): {sector}, {market_cap_billions:,.0f}억원, {weight}%")

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
