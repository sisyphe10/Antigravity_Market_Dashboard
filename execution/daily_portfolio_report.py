import os
import sys
import asyncio
import logging
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta, timezone
from telegram import Bot
import holidays
from dotenv import load_dotenv

load_dotenv()

# Windows console encoding fix
sys.stdout.reconfigure(encoding='utf-8')

# 로깅 설정
logging.basicConfig(level=logging.INFO)

def is_korean_trading_day():
    """한국 거래일 여부 확인 (주말 + 공휴일 제외)"""
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).date()
    kr_holidays = holidays.KR(years=today.year)
    if today.weekday() >= 5:
        logging.info(f"{today} 주말 - 리포트 스킵")
        return False
    if today in kr_holidays:
        logging.info(f"{today} 공휴일({kr_holidays.get(today)}) - 리포트 스킵")
        return False
    return True

file_name = 'Wrap_NAV.xlsx'

def get_day_of_week_kor():
    """한글 요일 반환"""
    days = ["월", "화", "수", "목", "금", "토", "일"]
    return days[datetime.now().weekday()]

def get_report_date():
    """리포트 기준 날짜 결정 (16시 기준)"""
    from datetime import timezone, timedelta as td
    
    # KST 시간대 (UTC+9)
    kst = timezone(td(hours=9))
    now_kst = datetime.now(kst)
    
    # 15시 이전이면 전일, 15시 이후면 당일
    if now_kst.hour < 15:
        report_date = now_kst.date() - td(days=1)
    else:
        report_date = now_kst.date()
    
    return report_date

def get_latest_nav():
    """최신 기준가 가져오기"""
    df = pd.read_excel(file_name, sheet_name='기준가')
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date')
    
    # 리포트 날짜 기준으로 데이터 가져오기
    report_date = get_report_date()
    
    # 리포트 날짜 이하의 가장 최근 데이터
    available_dates = df.index[df.index.date <= report_date]
    if len(available_dates) == 0:
        latest_date = df.index[-1]
    else:
        latest_date = available_dates[-1]
    
    latest_row = df.loc[latest_date]
    
    # 필요한 상품만 추출
    nav_data = {
        '삼성 트루밸류': latest_row.get('트루밸류', 0),
        'NH Value ESG': latest_row.get('Value ESG', 0),
        'DB 개방형 랩': latest_row.get('개방형 랩', 0),
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

    # 리포트 날짜 기준
    report_date = get_report_date()

    for _, row in df_latest.iterrows():
        # 코드 컬럼 사용 (종목코드와 동일한 값, 전체 행 채워져 있음)
        code = row.get('코드')
        stock_name = row['종목']
        weight = row['비중']  # 퍼센트 단위

        if pd.isna(code):
            logging.warning(f"⚠️ {stock_name}: 코드가 없습니다. 스킵합니다.")
            continue

        code = str(int(float(code))).strip().zfill(6)
        stock_name = row['종목']
        weight = row['비중']  # 퍼센트 단위
        
        try:
            # 리포트 날짜 기준으로 데이터 가져오기 (최근 10일)
            end_date = report_date
            start_date = end_date - timedelta(days=10)
            
            df_stock = fdr.DataReader(code, start=start_date, end=end_date)
            
            # 리포트 날짜 이하의 데이터만 필터링
            df_stock = df_stock[df_stock.index.date <= report_date]
            
            if len(df_stock) >= 2:
                # 리포트 날짜(D)와 전 거래일(D-1) 비교
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
    """텔레그램 메시지 포맷 (HTML)"""
    LINE = "━━━━━━━━━━━━━━━"

    # 리포트 날짜 기준
    report_date = get_report_date()
    day_of_week = ["월", "화", "수", "목", "금", "토", "일"][report_date.weekday()]
    date_str = f"{report_date.strftime('%Y-%m-%d')} ({day_of_week})"

    msg = f"<b>📊 포트폴리오 리포트</b>\n{date_str}\n"

    # 기준가
    msg += f"{LINE}\n<b>💰 기준가</b>\n{LINE}\n"
    for name, value in nav_data.items():
        msg += f"<b>{name}  {value:,.2f}</b>\n"

    # 수익률
    msg += f"{LINE}\n<b>📈 수익률</b>\n{LINE}\n"
    display_names = {
        '트루밸류': '삼성 트루밸류',
        'KOSPI': 'KOSPI',
        'KOSDAQ': 'KOSDAQ',
    }
    periods = ['1D', '1W', '1M', '3M', '6M', '1Y', 'YTD']
    for product in ['트루밸류', 'KOSPI', 'KOSDAQ']:
        if product in returns_data:
            returns = returns_data[product]
            # N/A가 아닌 항목만 표시
            valid_periods = []
            for p in periods:
                val = returns.get(p, 'N/A')
                if not pd.isna(val) and val != 'N/A':
                    if p == 'YTD':
                        valid_periods.append(f"<b><u>{p} {val}</u></b>")
                    else:
                        valid_periods.append(f"{p} {val}")
            if valid_periods:
                name = display_names.get(product, product)
                msg += f"<b>{name}</b>\n"
                # 3개씩 끊어서 줄바꿈
                for i in range(0, len(valid_periods), 3):
                    msg += " | ".join(valid_periods[i:i+3]) + "\n"
                msg += "\n"

    # 기여도 상위
    msg += f"{LINE}\n<b>🔺 기여도 상위</b>\n{LINE}\n"
    if top_5:
        for item in top_5:
            msg += f"{item['stock']}  {item['contribution']:+.1f}\n"
    else:
        msg += "데이터 없음\n"

    # 기여도 하위
    msg += f"{LINE}\n<b>🔻 기여도 하위</b>\n{LINE}\n"
    if bottom_5:
        for item in bottom_5:
            msg += f"{item['stock']}  {item['contribution']:+.1f}\n"
    else:
        msg += "데이터 없음\n"

    return msg

async def send_report(no_send=False):
    """리포트 생성 및 전송 (거래일만)"""
    if not is_korean_trading_day():
        print("거래일이 아니므로 리포트를 생략합니다.")
        return

    logging.info("1. 기준가 데이터 읽기...")
    date, nav_data = get_latest_nav()

    logging.info("2. 수익률 데이터 읽기...")
    returns_data = get_latest_returns()

    logging.info("3. 종목별 기여도 계산...")
    top_5, bottom_5 = calculate_contributions()

    logging.info("4. 메시지 포맷팅...")
    message = format_message(date, nav_data, returns_data, top_5, bottom_5)

    if not no_send:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            logging.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing.")
            sys.exit(1)
        logging.info("5. 텔레그램 전송...")
        bot = Bot(token=token)
        await bot.send_message(chat_id=chat_id, text=message, parse_mode='HTML')

    logging.info("완료!")
    print(f"\n전송된 메시지:\n{message}")

if __name__ == "__main__":
    no_send = '--no-send' in sys.argv
    asyncio.run(send_report(no_send=no_send))
