
import os
import sys
import logging
import asyncio
import datetime
import requests
from bs4 import BeautifulSoup
from telegram import Bot

# 로깅 설정
logging.basicConfig(level=logging.INFO)

def get_day_of_week_kor():
    days = ["월", "화", "수", "목", "금", "토", "일"]
    # GitHub Actions 환경(UTC) 고려: KST 기준 요일 계산
    # get_naver_weather 내부에서 보정하므로 여기선 now() 사용 시 주의
    # 일단 호출 시점의 datetime 객체를 받아 처리하는 것이 안전하지만,
    # 여기서는 datetime.datetime.now() 대신 외부에서 계산된 시간을 쓰거나
    # 함수 내부에서 +9시간 보정을 일관되게 적용해야 함.
    # 간단히: 이 함수는 호출 시점 시스템 시간 기준 요일을 반환.
    return days[datetime.datetime.now().weekday()]

def get_weather_emoji(status_text):
    if not status_text: return "🌤️"
    
    status = status_text.replace(" ", "")
    if "맑음" in status: return "☀️"
    if "구름많음" in status or "흐림" in status: return "☁️"
    if "비" in status: return "🌧️"
    if "눈" in status: return "☃️"
    return "🌤️"

def get_naver_weather(location="여의도"):
    """
    네이버 날씨 정보를 상세하게 가져옵니다.
    """
    try:
        url = f"https://search.naver.com/search.naver?query={location}+날씨"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        # 네트워크 요청 (10초 타임아웃)
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        
        soup = BeautifulSoup(res.text, "html.parser")
        
        # a. 날짜
        # GitHub Actions는 UTC일 수 있으므로 KST(+9) 보정
        now = datetime.datetime.now() + datetime.timedelta(hours=9)
        days = ["월", "화", "수", "목", "금", "토", "일"]
        day_kor = days[now.weekday()]
        date_str = now.strftime(f"%Y-%m-%d ({day_kor})")
        
        # b. 날씨
        summary_elem = soup.select_one("span.weather.before_slash")
        weather_status = summary_elem.text if summary_elem else "확인불가"
        weather_emoji = get_weather_emoji(weather_status)
        
        # c. 최저/최고
        min_elem = soup.select_one("span.lowest")
        max_elem = soup.select_one("span.highest")
        min_temp = min_elem.text.replace("최저기온", "").replace("°", "").strip() if min_elem else "?"
        max_temp = max_elem.text.replace("최고기온", "").replace("°", "").strip() if max_elem else "?"
        
        # d. 현재 기온
        temp_elem = soup.select_one("div.temperature_text > strong")
        current_temp = temp_elem.text.replace("현재 온도", "").replace("°", "").strip() if temp_elem else "?"
        
        # e, f. 차트 아이템
        chart_data = {}
        chart_list = soup.select("ul.today_chart_list > li")
        if chart_list:
            for item in chart_list:
                title_elem = item.select_one("strong")
                val_elem = item.select_one("span.txt")
                if title_elem and val_elem:
                    chart_data[title_elem.text.strip()] = val_elem.text.strip()
        
        dust = chart_data.get("미세먼지", "정보없음")
        ultra_dust = chart_data.get("초미세먼지", "정보없음")
        
        # 일출/일몰 계산 (astral 라이브러리 - 천문학 공식)
        try:
            from astral import LocationInfo
            from astral.sun import sun
            import datetime as dt

            city = LocationInfo("Seoul", "Korea", "Asia/Seoul", 37.5219, 126.9245)  # 여의도
            KST = dt.timezone(dt.timedelta(hours=9))
            today = dt.datetime.now(tz=KST).date()
            s = sun(city.observer, date=today, tzinfo=KST)
            sr = s['sunrise'].strftime('%H:%M')
            ss = s['sunset'].strftime('%H:%M')
            sun_info = f"{sr}, {ss}"
        except Exception as e:
            logging.error(f"Sunrise/sunset calculation failed: {e}")
            sun_info = "정보없음 (Error)"

        result_msg = (
            f"a. 날짜 / {date_str}\n"
            f"b. 날씨 / {weather_status} {weather_emoji}\n"
            f"c. 최저기온, 최고기온 / {min_temp}도, {max_temp}도\n"
            f"d. 현재기온 / {current_temp}도\n"
            f"e. 미세먼지, 초미세먼지 / {dust}, {ultra_dust}\n"
            f"f. 일출, 일몰 / {sun_info}"
        )
        return result_msg
        
    except Exception as e:
        logging.error(f"Scraping failed: {e}")
        return f"날씨 정보를 가져오는데 실패했습니다: {e}"

async def send_daily_alert():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        logging.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing.")
        sys.exit(1)
        
    logging.info("Fetching weather data...")
    message = get_naver_weather("여의도")
    
    logging.info(f"Sending message to {chat_id}...")
    bot = Bot(token=token)
    await bot.send_message(chat_id=chat_id, text=message)
    logging.info("Done.")

if __name__ == "__main__":
    asyncio.run(send_daily_alert())
