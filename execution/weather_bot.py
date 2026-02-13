import logging
import datetime
import os
import asyncio
import time
import subprocess
import sys
import json
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

# 로깅 설정
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# 환경 변수 로드
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Market Dashboard 저장소 경로
DASHBOARD_DIR = os.path.join(os.path.expanduser('~'), 'Antigravity_Market_Dashboard')

SUBSCRIBERS = set()

def get_day_of_week_kor():
    days = ["월", "화", "수", "목", "금", "토", "일"]
    return days[datetime.datetime.now().weekday()]

def get_weather_emoji(status_text):
    if not status_text: return "🌤️"
    
    status = status_text.replace(" ", "") # 공백 제거 후 비교
    if "맑음" in status: return "☀️"
    if "구름많음" in status or "흐림" in status: return "☁️"
    if "비" in status: return "🌧️"
    if "눈" in status: return "☃️"
    return "🌤️" # 기본값

def get_naver_weather(location="여의도"):
    """
    네이버 날씨 정보를 상세하게 가져옵니다. (Timeout: requests Level)
    포함: 날짜(요일), 이모티콘 날씨 등
    """
    start_time = time.time()
    try:
        url = f"https://search.naver.com/search.naver?query={location}+날씨"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        # 1. 네트워크 요청 (10초 타임아웃)
        logging.info(f"Start scraping for {location}...")
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        
        soup = BeautifulSoup(res.text, "html.parser")
        
        # --- 데이터 파싱 ---
        
        # a. 날짜 (요일 추가)
        now = datetime.datetime.now()
        day_kor = get_day_of_week_kor()
        date_str = now.strftime(f"%Y-%m-%d ({day_kor})")
        
        # b. 날씨 (이모티콘 추가)
        summary_elem = soup.select_one("span.weather.before_slash")
        weather_status = summary_elem.text if summary_elem else "확인불가"
        weather_emoji = get_weather_emoji(weather_status)
        
        # c. 최저/최고 기온
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
        
        # 일출/일몰 계산 (astral)
        
        # 일출/일몰 계산 (AccuWeather Scraping)
        try:
            accu_url = "https://www.accuweather.com/ko/kr/yeoui-dong/225999/weather-forecast/225999"
            accu_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
            }
            res = requests.get(accu_url, headers=accu_headers, timeout=5) # 5s timeout
            if res.status_code == 200:
                accu_soup = BeautifulSoup(res.text, "html.parser")
                # Structure: .sunrise-sunset container inside .sun
                # The text is like: "10시간 25분일출AM 7:34일몰PM 5:59"
                # Or parsing explicit labels
                
                # Method: Find '일출' and '일몰' followed by time (AM/PM HH:MM)
                # This is tricky with plain text. Let's look for specific elements found in check_accu.py
                # Found 1 blocks in .sunrise-sunset
                
                block = accu_soup.select_one(".sunrise-sunset")
                if block:
                    # Parse specific times. The text is usually messy.
                    # Let's try to extract time using regex for robust parsing
                    import re
                    text = block.get_text()
                    # Pattern: 일출(AM|PM)\s*(\d{1,2}:\d{2}) ... 일몰(AM|PM)\s*(\d{1,2}:\d{2})
                    # Or simple 'AM 7:34', 'PM 5:59'
                    
                    sunrise_match = re.search(r"일출\s*(AM|PM)\s*(\d{1,2}:\d{2})", text)
                    sunset_match = re.search(r"일몰\s*(AM|PM)\s*(\d{1,2}:\d{2})", text)
                    
                    def convert_to_24h(ampm, time_str):
                        hour, minute = map(int, time_str.split(':'))
                        if ampm == "PM" and hour != 12:
                            hour += 12
                        if ampm == "AM" and hour == 12:
                            hour = 0
                        return f"{hour:02d}:{minute:02d}"

                    if sunrise_match:
                        sr = convert_to_24h(sunrise_match.group(1), sunrise_match.group(2))
                    else:
                        sr = "?"
                        
                    if sunset_match:
                        ss = convert_to_24h(sunset_match.group(1), sunset_match.group(2))
                    else:
                        ss = "?"
                    
                    sun_info = f"{sr}, {ss}"
                else:
                    sun_info = "정보없음 (Parsing Fail)"
            else:
                 sun_info = "정보없음 (Connection Fail)"

        except Exception as e:
            logging.error(f"AccuWeather scraping failed: {e}")
            sun_info = "정보없음 (Error)"

        elapsed = time.time() - start_time
        logging.info(f"Scraping finished in {elapsed:.2f}s")

        # --- 출력 포맷 구성 ---
        result_msg = (
            f"a. 날짜 / {date_str}\n"
            f"b. 날씨 / {weather_status} {weather_emoji}\n"
            f"c. 최저기온, 최고기온 / {min_temp}도, {max_temp}도\n"
            f"d. 현재기온 / {current_temp}도\n"
            f"e. 미세먼지, 초미세먼지 / {dust}, {ultra_dust}\n"
            f"f. 일출, 일몰 / {sun_info}"
        )
        return result_msg
        
    except requests.Timeout:
        logging.error("Scraping timed out (requests)")
        raise TimeoutError("네이버 접속 시간이 초과되었습니다.")
    except Exception as e:
        logging.error(f"Scraping failed: {e}")
        raise e

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    SUBSCRIBERS.add(user_id)
    await context.bot.send_message(
        chat_id=user_id,
        text="반갑습니다! 매일 아침 6시에 여의도 날씨를 알려드릴게요.\n/weather 로 즉시 확인 가능합니다."
    )
    logging.info(f"New subscriber: {user_id}")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if user_id in SUBSCRIBERS:
        SUBSCRIBERS.remove(user_id)
        await context.bot.send_message(chat_id=user_id, text="구독 취소되었습니다.")
    else:
        await context.bot.send_message(chat_id=user_id, text="구독 중이 아닙니다.")

async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    status_msg = await context.bot.send_message(chat_id=chat_id, text="🔍 날씨 정보를 가져오는 중입니다...")
    
    try:
        loop = asyncio.get_running_loop()
        weather_info = await asyncio.wait_for(
            loop.run_in_executor(None, get_naver_weather, "여의도"),
            timeout=15.0
        )
        await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=weather_info)
        
    except asyncio.TimeoutError:
        await context.bot.edit_message_text(
            chat_id=chat_id, 
            message_id=status_msg.message_id, 
            text="⚠️ **오류 알림**\n날씨 조회 시간이 15초를 초과하여 중단되었습니다."
        )
    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=f"❌ 오류가 발생했습니다: {str(e)}"
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """도움말 표시"""
    help_text = """📋 **사용 가능한 명령어**

🌤️ **날씨 정보**
/weather - 여의도 날씨 조회
• 매일 오전 6시 자동 전송
• 날짜, 날씨, 기온, 미세먼지, 일출/일몰 정보 제공

📊 **포트폴리오 리포트**
/portfolio - 포트폴리오 리포트 조회
• 매일 오후 4시 자동 전송
• 기준가 (삼성 트루밸류, NH Value ESG, DB 개방형 랩)
• 수익률 (1D, 1W, 1M, 3M, 6M, 1Y, YTD)
• 종목별 기여도 상위/하위 5개

🔄 **포트폴리오 테이블 업데이트**
/update - 실시간 주가 기반 포트폴리오 테이블 즉시 업데이트
• 오늘 수익률 + 누적 수익률 재계산
• Dashboard(GitHub Pages) 자동 반영

⚙️ **기타**
/start - 봇 시작 및 자동 알림 구독
/stop - 자동 알림 구독 해제
/help - 이 도움말 표시
"""
    await update.message.reply_text(help_text)

async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """포트폴리오 리포트 조회"""
    chat_id = update.effective_chat.id
    
    # 처리 중 메시지
    status_msg = await update.message.reply_text("📊 포트폴리오 리포트를 생성하는 중...")
    
    try:
        import subprocess
        import sys
        
        # daily_portfolio_report.py 실행
        result = subprocess.run(
            [sys.executable, "execution/daily_portfolio_report.py"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            # 성공 - 출력에서 메시지 추출
            output_lines = result.stdout.strip().split('\n')
            
            # "전송된 메시지:" 이후의 내용 찾기
            message_start = -1
            for i, line in enumerate(output_lines):
                if "전송된 메시지:" in line:
                    message_start = i + 1
                    break
            
            if message_start > 0:
                report_message = '\n'.join(output_lines[message_start:])
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg.message_id,
                    text=report_message
                )
            else:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg.message_id,
                    text="✅ 리포트가 생성되었습니다."
                )
        else:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text=f"❌ 리포트 생성 실패:\n{result.stderr}"
            )
            
    except subprocess.TimeoutExpired:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text="⚠️ 리포트 생성 시간이 초과되었습니다."
        )
    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=f"❌ 오류가 발생했습니다: {str(e)}"
        )

def fetch_price(code):
    """종목 실시간 가격 조회 (스레드에서 호출)"""
    import FinanceDataReader as fdr
    from datetime import timedelta
    import pandas as pd
    try:
        df = fdr.DataReader(code, start=pd.Timestamp.now() - timedelta(days=5))
        if len(df) < 2:
            return code, None
        latest = df.iloc[-1]['Close']
        prev = df.iloc[-2]['Close']
        return code, ((latest - prev) / prev) * 100
    except Exception:
        return code, None


def run_portfolio_update():
    """포트폴리오 테이블 업데이트 실행 (동기 - run_in_executor에서 호출)"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    dashboard_dir = DASHBOARD_DIR

    # 1. 기존 portfolio_data.json 읽기 (종목 코드/비중 이미 확정됨)
    logging.info("Update Step 1: Reading portfolio_data.json...")
    portfolio_file = os.path.join(dashboard_dir, 'portfolio_data.json')
    with open(portfolio_file, 'r', encoding='utf-8') as f:
        portfolio_data = json.load(f)

    # 전체 종목 코드 수집 (중복 제거)
    all_codes = set()
    for stocks in portfolio_data.values():
        for s in stocks:
            all_codes.add(s['code'])

    # 2. 실시간 주가 병렬 조회
    logging.info(f"Update Step 2: Fetching {len(all_codes)} stock prices...")
    price_map = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_price, code): code for code in all_codes}
        for future in as_completed(futures):
            code, today_return = future.result()
            price_map[code] = today_return

    # 3. today_return, contribution 업데이트
    logging.info("Update Step 3: Updating returns...")
    for portfolio_name, stocks in portfolio_data.items():
        for s in stocks:
            today_return = price_map.get(s['code'])
            s['today_return'] = today_return
            if today_return is not None:
                s['contribution'] = (s['weight'] / 100) * (today_return / 100) * 1000
            else:
                s['contribution'] = None

    # 4. portfolio_data.json 저장
    with open(portfolio_file, 'w', encoding='utf-8') as f:
        json.dump(portfolio_data, f, ensure_ascii=False, indent=2)

    # 5. create_dashboard.py 실행
    logging.info("Update Step 4: Running create_dashboard.py...")
    result = subprocess.run(
        [sys.executable, "execution/create_dashboard.py"],
        capture_output=True,
        text=True,
        encoding='utf-8',
        timeout=60,
        cwd=dashboard_dir
    )
    if result.returncode != 0:
        raise RuntimeError(f"create_dashboard.py 실패:\n{result.stderr}")

    # 6. Git commit & push
    logging.info("Update Step 5: Git commit & push...")
    subprocess.run(
        ["git", "add", "portfolio_data.json", "index.html"],
        cwd=dashboard_dir,
        capture_output=True,
        timeout=30
    )

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    commit_result = subprocess.run(
        ["git", "commit", "-m", f"Update portfolio tables ({now_str})"],
        cwd=dashboard_dir,
        capture_output=True,
        text=True,
        timeout=30
    )

    if commit_result.returncode == 0:
        push_result = subprocess.run(
            ["git", "push"],
            cwd=dashboard_dir,
            capture_output=True,
            text=True,
            timeout=60
        )
        if push_result.returncode != 0:
            logging.warning(f"Git push failed: {push_result.stderr}")
    else:
        logging.info(f"No changes to commit: {commit_result.stdout}")

    return portfolio_data


def format_update_summary(portfolio_data):
    """포트폴리오 업데이트 요약 메시지 생성"""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"📊 포트폴리오 업데이트 완료", f"⏰ {now_str} 기준", ""]

    for portfolio_name, stocks in portfolio_data.items():
        # 포트폴리오 가중 평균 수익률
        total_weight = sum(s['weight'] for s in stocks)
        weighted_return = sum(
            s['weight'] * (s['today_return'] or 0)
            for s in stocks
        ) / total_weight if total_weight > 0 else 0

        lines.append(f"[{portfolio_name}]")
        lines.append(f"오늘: {weighted_return:+.1f}%")

        # 상승 종목 (today_return > 0, 상위 5개)
        gainers = sorted(
            [s for s in stocks if s['today_return'] and s['today_return'] > 0],
            key=lambda x: x['today_return'],
            reverse=True
        )[:5]

        # 하락 종목 (today_return < 0, 하위 5개)
        losers = sorted(
            [s for s in stocks if s['today_return'] and s['today_return'] < 0],
            key=lambda x: x['today_return']
        )[:5]

        if gainers:
            lines.append("▲")
            for s in gainers:
                contrib = s.get('contribution')
                contrib_str = f" {contrib:+.2f}" if contrib is not None else ""
                lines.append(f"  {s['name']} {s['today_return']:+.1f}%{contrib_str}")

        if losers:
            lines.append("▼")
            for s in losers:
                contrib = s.get('contribution')
                contrib_str = f" {contrib:+.2f}" if contrib is not None else ""
                lines.append(f"  {s['name']} {s['today_return']:+.1f}%{contrib_str}")

        lines.append("")

    return "\n".join(lines)


async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """포트폴리오 테이블 실시간 업데이트"""
    chat_id = update.effective_chat.id
    status_msg = await update.message.reply_text("📊 포트폴리오 테이블 업데이트 중...")

    try:
        loop = asyncio.get_running_loop()
        portfolio_data = await asyncio.wait_for(
            loop.run_in_executor(None, run_portfolio_update),
            timeout=300.0
        )

        summary = format_update_summary(portfolio_data)
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=summary
        )

    except asyncio.TimeoutError:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text="⚠️ 포트폴리오 업데이트 시간이 초과되었습니다 (5분)."
        )
    except Exception as e:
        logging.error(f"Portfolio update failed: {e}")
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=f"❌ 업데이트 실패: {str(e)}"
        )


async def daily_weather_job(context: ContextTypes.DEFAULT_TYPE):
    if not SUBSCRIBERS:
        return

    try:
        loop = asyncio.get_running_loop()
        weather_info = await asyncio.wait_for(
            loop.run_in_executor(None, get_naver_weather, "여의도"),
            timeout=15.0
        )

        for chat_id in SUBSCRIBERS:
            try:
                await context.bot.send_message(chat_id=chat_id, text=weather_info)
            except Exception as e:
                logging.error(f"Failed to send to {chat_id}: {e}")

    except Exception as e:
        logging.error(f"Daily job failed: {e}")

async def daily_portfolio_job(context: ContextTypes.DEFAULT_TYPE):
    """매일 오후 4시 포트폴리오 업데이트 및 리포트 전송"""
    if not SUBSCRIBERS:
        logging.info("No subscribers for portfolio report")
        return

    try:
        import subprocess
        import sys
        import os

        # 작업 디렉토리를 Antigravity 루트로 변경
        original_dir = os.getcwd()
        script_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(script_dir)  # Antigravity 루트
        os.chdir(parent_dir)

        logging.info("Starting portfolio update process...")

        # 1. 기준가 업데이트
        logging.info("Step 1: Updating NAV prices...")
        result_nav = subprocess.run(
            [sys.executable, "calculate_wrap_nav.py"],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result_nav.returncode != 0:
            logging.error(f"NAV update failed: {result_nav.stderr}")
            os.chdir(original_dir)
            return

        logging.info("NAV prices updated successfully")

        # 2. 수익률 계산
        logging.info("Step 2: Calculating returns...")
        result_returns = subprocess.run(
            [sys.executable, "calculate_returns.py"],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result_returns.returncode != 0:
            logging.error(f"Returns calculation failed: {result_returns.stderr}")
            os.chdir(original_dir)
            return

        logging.info("Returns calculated successfully")

        # 3. 포트폴리오 리포트 생성 및 전송
        logging.info("Step 3: Generating portfolio report...")
        result_report = subprocess.run(
            [sys.executable, "execution/daily_portfolio_report.py"],
            capture_output=True,
            text=True,
            timeout=120
        )

        os.chdir(original_dir)  # 원래 디렉토리로 복귀

        if result_report.returncode == 0:
            logging.info("Portfolio report sent successfully via Telegram")
        else:
            logging.error(f"Report generation failed: {result_report.stderr}")
            # 실패해도 구독자들에게 알림
            for chat_id in SUBSCRIBERS:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="⚠️ 포트폴리오 리포트 생성에 실패했습니다."
                    )
                except Exception as e:
                    logging.error(f"Failed to send error notification to {chat_id}: {e}")

    except subprocess.TimeoutExpired:
        logging.error("Portfolio update process timed out")
        os.chdir(original_dir)
    except Exception as e:
        logging.error(f"Daily portfolio job failed: {e}")
        os.chdir(original_dir)

if __name__ == '__main__':
    if not TOKEN:
        print("Error: TOKEN environment variable is missing.")
        import sys
        sys.exit(1)

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('weather', weather))
    application.add_handler(CommandHandler('portfolio', portfolio_command))
    application.add_handler(CommandHandler('update', update_command))
    application.add_handler(CommandHandler('stop', stop))
    application.add_handler(CommandHandler('help', help_command))
    
    job_queue = application.job_queue
    try:
        import pytz
        kst = pytz.timezone('Asia/Seoul')
        # 매일 아침 6시 - 날씨 알림
        weather_time = datetime.time(hour=6, minute=0, second=0, tzinfo=kst)
        # 매일 오후 4시 - 포트폴리오 업데이트 및 리포트
        portfolio_time = datetime.time(hour=16, minute=0, second=0, tzinfo=kst)
    except:
        weather_time = datetime.time(hour=6, minute=0, second=0)
        portfolio_time = datetime.time(hour=16, minute=0, second=0)

    job_queue.run_daily(daily_weather_job, time=weather_time)
    job_queue.run_daily(daily_portfolio_job, time=portfolio_time)

    print(f"Bot started at {datetime.datetime.now()}")
    print(f"✅ Daily jobs scheduled:")
    print(f"  - Weather report: 06:00 KST")
    print(f"  - Portfolio update & report: 16:00 KST")
    application.run_polling()
