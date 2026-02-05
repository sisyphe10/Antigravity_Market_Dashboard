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
    """오늘의 캘린더 일정 조회 (직접 지정된 캘린더)"""
    credentials = get_credentials_from_env()
    service = build('calendar', 'v3', credentials=credentials)
    
    # 조회할 캘린더 목록 (직접 지정)
    # 캘린더를 추가하려면 여기에 캘린더 ID를 추가하세요
    calendars_to_check = {
        'kts77775@gmail.com': '메인 캘린더',
        'a49c912f9e11c6e050c873312ae00a314e45dc075540c86cf428c9921fcbc20c@group.calendar.google.com': '옥쥬와 빵빵이',
        'h7u3p3bs2tva7ki3e2up0tg30o@group.calendar.google.com': '운용 본부',
        's7m7ahc836cajffbt98vae3m1k@group.calendar.google.com': '투자 활동',
    }
    
    logging.info("조회할 캘린더:")
    for cal_id, cal_name in calendars_to_check.items():
        logging.info(f"  - {cal_name} (ID: {cal_id})")
    
    # 오늘 00:00 ~ 23:59 (KST)
    from datetime import timezone, timedelta
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    
    # KST 기준으로 오늘의 시작과 끝
    start_of_day = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=kst)
    end_of_day = datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=kst)
    
    logging.info(f"📅 오늘({now.strftime('%Y-%m-%d')}) 일정 조회 중...")
    logging.info(f"시간 범위: {start_of_day.isoformat()} ~ {end_of_day.isoformat()}")
    
    # 캘린더별로 일정 수집
    events_by_calendar = {
        'main': [],  # 메인 캘린더 (투자 활동 제외)
        'investment': []  # 투자 활동 캘린더
    }
    
    # 모든 캘린더 조회
    for cal_id, cal_name in calendars_to_check.items():
        try:
            logging.info(f"캘린더 '{cal_name}' 조회 중...")
            events_result = service.events().list(
                calendarId=cal_id,
                timeMin=start_of_day.isoformat(),
                timeMax=end_of_day.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            logging.info(f"  → {len(events)}개 일정 발견")
            
            # 투자 활동 캘린더는 별도로 분류
            if '투자 활동' in cal_name or '투자활동' in cal_name or 'investment' in cal_name.lower():
                events_by_calendar['investment'].extend(events)
            else:
                events_by_calendar['main'].extend(events)
                
        except Exception as e:
            logging.warning(f"캘린더 '{cal_name}' 조회 실패: {e}")
    
    # 시간순 정렬
    def get_event_time(event):
        start = event['start'].get('dateTime', event['start'].get('date'))
        if 'T' in start:
            return datetime.fromisoformat(start.replace('Z', '+00:00'))
        else:
            return datetime.fromisoformat(start + 'T00:00:00+00:00')
    
    events_by_calendar['main'].sort(key=get_event_time)
    events_by_calendar['investment'].sort(key=get_event_time)
    
    total_events = len(events_by_calendar['main']) + len(events_by_calendar['investment'])
    logging.info(f"총 {total_events}개 일정 발견 (메인: {len(events_by_calendar['main'])}, 투자: {len(events_by_calendar['investment'])})")
    
    return events_by_calendar

def format_calendar_message(events_by_calendar):
    """캘린더 일정을 텔레그램 메시지 형식으로 변환 (캘린더별 구분)"""
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    day_kor = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
    
    msg = f"📅 오늘의 일정 ({date_str} {day_kor}요일)\n\n"
    
    main_events = events_by_calendar.get('main', [])
    investment_events = events_by_calendar.get('investment', [])
    
    # 메인 캘린더 일정
    if main_events:
        for event in main_events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', '(제목 없음)')
            
            # 시간 파싱
            if 'T' in start:  # 시간이 있는 일정
                dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                time_str = dt.strftime('%H:%M')
                msg += f"• {time_str} - {summary}\n"
            else:  # 종일 일정
                msg += f"• 종일 - {summary}\n"
    
    # 투자 활동 캘린더 일정 (별도 섹션)
    if investment_events:
        msg += f"\n💼 투자 활동\n"
        for event in investment_events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', '(제목 없음)')
            
            # 시간 파싱
            if 'T' in start:  # 시간이 있는 일정
                dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                time_str = dt.strftime('%H:%M')
                msg += f"• {time_str} - {summary}\n"
            else:  # 종일 일정
                msg += f"• 종일 - {summary}\n"
    
    # 총 일정 개수
    total_count = len(main_events) + len(investment_events)
    
    if total_count == 0:
        msg += "오늘은 일정이 없습니다. 😊"
    else:
        msg += f"\n총 {total_count}개의 일정이 있습니다."
    
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
