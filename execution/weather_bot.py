import logging
import datetime
import os
import asyncio
import subprocess
import sys
import json
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from dotenv import load_dotenv

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

SUBSCRIBERS_FILE = os.path.join(DASHBOARD_DIR, 'subscribers.json')

def load_subscribers():
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE, 'r') as f:
            return set(json.load(f))
    return set()

def save_subscribers():
    with open(SUBSCRIBERS_FILE, 'w') as f:
        json.dump(list(SUBSCRIBERS), f)

SUBSCRIBERS = load_subscribers()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    SUBSCRIBERS.add(user_id)
    save_subscribers()
    await context.bot.send_message(
        chat_id=user_id,
        text="반갑습니다! 포트폴리오 리포트와 장중 업데이트를 알려드릴게요.\n/help 로 명령어를 확인하세요."
    )
    logging.info(f"New subscriber: {user_id}")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if user_id in SUBSCRIBERS:
        SUBSCRIBERS.remove(user_id)
        save_subscribers()
        await context.bot.send_message(chat_id=user_id, text="구독 취소되었습니다.")
    else:
        await context.bot.send_message(chat_id=user_id, text="구독 중이 아닙니다.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """도움말 표시"""
    help_text = """📋 **사용 가능한 명령어**

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
• 거래일 09:30~15:30 30분마다 자동 실행

🌤️ **날씨 / 일정**
• 매일 05:00 날씨 자동 전송 (GitHub Actions)
• 매일 05:10 Google Calendar 일정 자동 전송 (GitHub Actions)

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
        df = fdr.DataReader(code, start=pd.Timestamp.now() - timedelta(days=30))
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
        # pull --rebase로 원격 변경사항 통합 후 push
        subprocess.run(
            ["git", "pull", "--rebase", "origin", "main"],
            cwd=dashboard_dir,
            capture_output=True,
            text=True,
            timeout=60
        )
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


async def auto_portfolio_update_job(context: ContextTypes.DEFAULT_TYPE):
    """거래일 30분마다 자동 포트폴리오 업데이트 + 텔레그램 알림"""
    import datetime as dt_module
    now_kst = dt_module.datetime.now(pytz.timezone('Asia/Seoul'))

    # 주말 스킵
    if now_kst.weekday() >= 5:
        return

    # 실제 거래 여부 확인: 삼성전자 오늘 데이터가 있으면 장중
    try:
        import FinanceDataReader as fdr
        import pandas as pd
        today_str = now_kst.strftime('%Y-%m-%d')
        df = fdr.DataReader('005930', start=today_str)
        if df.empty:
            logging.info(f"Auto update skipped: no market data today ({today_str}, 공휴일 또는 휴장)")
            return
    except Exception as e:
        logging.warning(f"Auto update: market check 실패 ({e}), 업데이트 진행")

    logging.info(f"Auto portfolio update started at {now_kst.strftime('%H:%M')} KST")
    try:
        loop = asyncio.get_running_loop()
        portfolio_data = await asyncio.wait_for(
            loop.run_in_executor(None, run_portfolio_update),
            timeout=300.0
        )
        logging.info("Auto portfolio update completed successfully")

        # 구독자에게 텔레그램 알림 전송
        if SUBSCRIBERS and portfolio_data:
            summary = format_update_summary(portfolio_data)
            for chat_id in SUBSCRIBERS:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=summary)
                except Exception as e:
                    logging.error(f"Auto update 알림 전송 실패 (chat_id={chat_id}): {e}")
    except Exception as e:
        logging.error(f"Auto portfolio update failed: {e}")


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

        # 0. 최신 Wrap_NAV.xlsx 받기 (로컬 PC에서 push한 내용 반영)
        logging.info("Step 0: Pulling latest data from GitHub...")
        subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=parent_dir,
            capture_output=True,
            text=True,
            timeout=60
        )

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
    application.add_handler(CommandHandler('portfolio', portfolio_command))
    application.add_handler(CommandHandler('update', update_command))
    application.add_handler(CommandHandler('stop', stop))
    application.add_handler(CommandHandler('help', help_command))
    
    job_queue = application.job_queue
    try:
        import pytz
        kst = pytz.timezone('Asia/Seoul')
        # 매일 오후 4시 - 포트폴리오 업데이트 및 리포트
        portfolio_time = datetime.time(hour=16, minute=0, second=0, tzinfo=kst)
    except:
        portfolio_time = datetime.time(hour=16, minute=0, second=0)

    # 날씨 알림은 GitHub Actions에서 전송 (daily_weather.yml, KST 05:00)
    job_queue.run_daily(daily_portfolio_job, time=portfolio_time)

    # 거래시간 30분마다 자동 포트폴리오 업데이트
    # 09:30, 10:00, 10:30, ..., 15:00, 15:30 KST
    try:
        kst = pytz.timezone('Asia/Seoul')
        trading_times = [
            datetime.time(hour=h, minute=m, second=0, tzinfo=kst)
            for h, m in [
                (9,30),(10,0),(10,30),(11,0),(11,30),
                (12,0),(12,30),(13,0),(13,30),(14,0),
                (14,30),(15,0),(15,30)
            ]
        ]
    except:
        trading_times = [
            datetime.time(hour=h, minute=m, second=0)
            for h, m in [
                (9,30),(10,0),(10,30),(11,0),(11,30),
                (12,0),(12,30),(13,0),(13,30),(14,0),
                (14,30),(15,0),(15,30)
            ]
        ]

    for t in trading_times:
        job_queue.run_daily(auto_portfolio_update_job, time=t)

    print(f"Bot started at {datetime.datetime.now()}")
    print(f"✅ Daily jobs scheduled:")
    print(f"  - Weather report: 06:00 KST")
    print(f"  - Portfolio update & report: 16:00 KST")
    print(f"  - Auto portfolio update: 09:30~15:30 KST (30분 간격, 거래일만)")
    application.run_polling()
