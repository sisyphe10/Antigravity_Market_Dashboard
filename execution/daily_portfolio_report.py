import os
import sys
import asyncio
import logging
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta
from telegram import Bot

# Windows console encoding fix
sys.stdout.reconfigure(encoding='utf-8')

# 로깅 설정
logging.basicConfig(level=logging.INFO)

file_name = 'Wrap_NAV.xlsx'

def get_day_of_week_kor():
    """한글 요일 반환"""
    days = ["월", "화", "수", "목", "금", "토", "일"]
    return days[datetime.now().weekday()]

def get_latest_nav():
    """최신 기준가 가져오기"""
    df = pd.read_excel(file_name, sheet_name='기준가')
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date')
    
    latest_date = df.index[-1]
    latest_row = df.loc[latest_date]
    
    # 필요한 상품만 추출
    nav_data = {
        '삼성 트루밸류': latest_row.get('트루밸류', 0),
        'NH Value ESG': latest_row.get('Value ESG', 0),
        'DB 개방형 랩': latest_row.get('자문형 랩', 0)
    }
    
    return latest_date, nav_data

def get_latest_returns():
    """최신 수익률 가져오기"""
    df = pd.read_excel(file_name, sheet_name='수익률')
    
    if len(df) == 0:
        return {}
    
    latest_row = df.iloc[-1]
    
    # 트루밸류, KOSPI, KOSDAQ 수익률 추출
    returns_data = {}
    
    for product in ['트루밸류', 'KOSPI', 'KOSDAQ']:
        returns_data[product] = {
            '1D': latest_row.get(f'{product}_1D', 'N/A'),
            '1W': latest_row.get(f'{product}_1W', 'N/A'),
            '1M': latest_row.get(f'{product}_1M', 'N/A'),
            '3M': latest_row.get(f'{product}_3M', 'N/A'),
            '6M': latest_row.get(f'{product}_6M', 'N/A'),
            '1Y': latest_row.get(f'{product}_1Y', 'N/A'),
            'YTD': latest_row.get(f'{product}_YTD', 'N/A')
        }
    
    return returns_data

def calculate_contributions():
    """종목별 기여도 계산 (트루밸류 기준)"""
    # 포트폴리오 구성 읽기
    df_portfolio = pd.read_excel(file_name, sheet_name='NEW')
    df_portfolio = df_portfolio[df_portfolio['상품명'] == '트루밸류']
    
    if len(df_portfolio) == 0:
        return [], []
    
    # 최신 날짜의 포트폴리오 구성
    df_portfolio['날짜'] = pd.to_datetime(df_portfolio['날짜'])
    latest_date = df_portfolio['날짜'].max()
    df_latest = df_portfolio[df_portfolio['날짜'] == latest_date]
    
    # 비중이 0인 종목 제외
    df_latest = df_latest[df_latest['비중'] > 0]
    
    contributions = []
    
    for _, row in df_latest.iterrows():
        # 종목코드 컬럼 사용
        code = row.get('종목코드')
        
        if pd.isna(code):
            continue
            
        code = str(code).strip().zfill(6)
        stock_name = row['종목']
        weight = row['비중']  # 퍼센트 단위
        
        try:
            # 최근 7일 데이터 가져오기
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)
            
            df_stock = fdr.DataReader(code, start=start_date, end=end_date)
            
            if len(df_stock) >= 2:
                # 전일 대비 변동률
                latest_price = df_stock['Close'].iloc[-1]
                prev_price = df_stock['Close'].iloc[-2]
                latest_date_actual = df_stock.index[-1]
                prev_date_actual = df_stock.index[-2]
                change_pct = ((latest_price - prev_price) / prev_price) * 100
                
                # 기여도 = 비중 × 변동률
                contribution = (weight / 100) * change_pct
                
                logging.info(f"{stock_name}: {prev_date_actual.strftime('%Y-%m-%d')} {prev_price:,.0f} → {latest_date_actual.strftime('%Y-%m-%d')} {latest_price:,.0f} ({change_pct:+.2f}%) = 기여도 {contribution:+.2f}")
                
                contributions.append({
                    'stock': stock_name,
                    'contribution': contribution
                })
            
        except Exception as e:
            logging.warning(f"Failed to get data for {stock_name} ({code}): {e}")
            continue
    
    # 정렬
    contributions_sorted = sorted(contributions, key=lambda x: x['contribution'], reverse=True)
    
    top_5 = contributions_sorted[:5]
    # 하위 5개는 오름차순 (가장 낮은 것부터)
    bottom_5 = sorted(contributions_sorted[-5:], key=lambda x: x['contribution'])
    
    return top_5, bottom_5

def format_message(date, nav_data, returns_data, top_5, bottom_5):
    """텔레그램 메시지 포맷"""
    day_kor = get_day_of_week_kor()
    date_str = date.strftime(f'%Y-%m-%d ({day_kor})')
    
    # a. 날짜
    msg = f"a. 날짜 / {date_str}\n"
    
    # b. 기준가
    msg += "b. 기준가 / \n"
    for name, value in nav_data.items():
        msg += f"{name} {value:,.2f}\n"
    
    # c. 수익률
    msg += "c. 수익률 (1D 1W 1M 3M 6M 1Y YTD)\n"
    for product in ['트루밸류', 'KOSPI', 'KOSDAQ']:
        if product in returns_data:
            returns = returns_data[product]
            # NaN과 numpy 타입을 문자열로 변환
            returns_str = " ".join([
                str(returns.get(period, 'N/A')) if not pd.isna(returns.get(period, 'N/A')) else 'N/A'
                for period in ['1D', '1W', '1M', '3M', '6M', '1Y', 'YTD']
            ])
            
            if product == '트루밸류':
                msg += f"삼성 트루밸류\n{returns_str}\n"
            else:
                msg += f"{product}\n{returns_str}\n"
    
    # d. 종목별 기여도 상위
    if top_5:
        top_str = " ".join([f"{item['stock']} {item['contribution']:+.1f}" for item in top_5])
        msg += f"d. 종목별 기여도 상위 / \n{top_str}\n"
    else:
        msg += "d. 종목별 기여도 상위 / \n데이터 없음\n"
    
    # e. 종목별 기여도 하위
    if bottom_5:
        bottom_str = " ".join([f"{item['stock']} {item['contribution']:+.1f}" for item in bottom_5])
        msg += f"e. 종목별 기여도 하위 / \n{bottom_str}"
    else:
        msg += "e. 종목별 기여도 하위 / \n데이터 없음"
    
    return msg

async def send_report():
    """리포트 생성 및 전송"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        logging.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing.")
        sys.exit(1)
    
    logging.info("1. 기준가 데이터 읽기...")
    date, nav_data = get_latest_nav()
    
    logging.info("2. 수익률 데이터 읽기...")
    returns_data = get_latest_returns()
    
    logging.info("3. 종목별 기여도 계산...")
    top_5, bottom_5 = calculate_contributions()
    
    logging.info("4. 메시지 포맷팅...")
    message = format_message(date, nav_data, returns_data, top_5, bottom_5)
    
    logging.info("5. 텔레그램 전송...")
    bot = Bot(token=token)
    await bot.send_message(chat_id=chat_id, text=message)
    
    logging.info("완료!")
    print(f"\n전송된 메시지:\n{message}")

if __name__ == "__main__":
    asyncio.run(send_report())
