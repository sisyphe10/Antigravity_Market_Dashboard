"""
Google Calendar 일정 조회 스크립트 (서비스 계정 방식)
GitHub Actions에서 실행 가능
"""
import os
import sys
import json
import logging
import asyncio
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from telegram import Bot

# 로깅 설정
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# 캘린더 읽기 권한
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def get_credentials_from_env():
    """환경 변수에서 서비스 계정 인증 정보 가져오기"""
    service_account_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_KEY')
    
    if not service_account_json:
        logging.error("❌ GOOGLE_SERVICE_ACCOUNT_KEY 환경 변수가 설정되지 않았습니다.")
        sys.exit(1)
    
    # JSON 문자열을 딕셔너리로 변환
    service_account_info = json.loads(service_account_json)
    
    # 서비스 계정 인증 정보 생성
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=SCOPES
    )
    
    return credentials

def get_today_events():
    """오늘의 캘린더 일정 조회"""
    credentials = get_credentials_from_env()
    service = build('calendar', 'v3', credentials=credentials)
    
    # 오늘 00:00 ~ 23:59 (KST)
    now = datetime.now()
    start_of_day = datetime(now.year, now.month, now.day, 0, 0, 0).isoformat() + 'Z'
    end_of_day = datetime(now.year, now.month, now.day, 23, 59, 59).isoformat() + 'Z'
    
    logging.info(f"📅 오늘({now.strftime('%Y-%m-%d')}) 일정 조회 중...")
    
    # 캘린더 일정 가져오기
    # primary 대신 서비스 계정과 공유한 캘린더 사용
    events_result = service.events().list(
        calendarId='primary',  # 공유된 기본 캘린더
        timeMin=start_of_day,
        timeMax=end_of_day,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])
    logging.info(f"일정 {len(events)}개 발견")
    
    return events

def format_calendar_message(events):
    """캘린더 일정을 텔레그램 메시지 형식으로 변환"""
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    day_kor = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
    
    msg = f"📅 오늘의 일정 ({date_str} {day_kor}요일)\n\n"
    
    if not events:
        msg += "오늘은 일정이 없습니다. 😊"
        return msg
    
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        summary = event.get('summary', '(제목 없음)')
        
        # 시간 파싱
        if 'T' in start:  # 시간이 있는 일정
            dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            time_str = dt.strftime('%H:%M')
            msg += f"• {time_str} - {summary}\n"
        else:  # 종일 일정
            msg += f"• 종일 - {summary}\n"
    
    msg += f"\n총 {len(events)}개의 일정이 있습니다."
    
    return msg

async def send_calendar_to_telegram(message):
    """텔레그램으로 캘린더 일정 전송"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        logging.error("❌ TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않았습니다.")
        sys.exit(1)
    
    bot = Bot(token=token)
    await bot.send_message(chat_id=chat_id, text=message)
    logging.info("✅ 텔레그램 전송 완료!")

async def main():
    """메인 함수"""
    try:
        logging.info("=" * 50)
        logging.info("Google Calendar 일정 조회 시작")
        logging.info("=" * 50)
        
        # 1. 오늘 일정 조회
        events = get_today_events()
        
        # 2. 메시지 포맷
        message = format_calendar_message(events)
        logging.info(f"\n전송할 메시지:\n{message}\n")
        
        # 3. 텔레그램 전송
        await send_calendar_to_telegram(message)
        
        logging.info("=" * 50)
        logging.info("완료!")
        logging.info("=" * 50)
        
    except Exception as e:
        logging.error(f"❌ 오류 발생: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())
