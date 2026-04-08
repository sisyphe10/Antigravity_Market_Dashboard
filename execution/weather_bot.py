import logging
import datetime
import os
import asyncio
import subprocess
import sys
import json
import fcntl

# 중복 실행 방지 (파일 락)
_lock_file = open('/tmp/weather_bot.lock', 'w')
try:
    fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    _lock_file.write(str(os.getpid()))
    _lock_file.flush()
except IOError:
    print("ERROR: weather_bot is already running. Exiting.")
    sys.exit(1)

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


def git_sync(cwd):
    """VM git 동기화: fetch + reset --hard (충돌 불가)"""
    subprocess.run(["git", "fetch", "origin", "main"], cwd=cwd, capture_output=True, timeout=60)
    subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=cwd, capture_output=True, timeout=30)


def git_push_safe(cwd):
    """커밋 후 push: 실패 시 fetch+rebase+push 재시도, 그래도 실패 시 abort"""
    result = subprocess.run(["git", "push"], cwd=cwd, capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        return True
    # push 실패 → fetch + rebase 시도
    subprocess.run(["git", "fetch", "origin", "main"], cwd=cwd, capture_output=True, timeout=60)
    rebase = subprocess.run(["git", "rebase", "origin/main"], cwd=cwd, capture_output=True, text=True, timeout=60)
    if rebase.returncode != 0:
        subprocess.run(["git", "rebase", "--abort"], cwd=cwd, capture_output=True, timeout=10)
        logging.warning("git push failed: rebase conflict, aborted")
        return False
    result2 = subprocess.run(["git", "push"], cwd=cwd, capture_output=True, text=True, timeout=60)
    return result2.returncode == 0


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
• 거래일 09:30~15:35 30분마다 자동 실행

🌤️ **날씨 / 일정**
/weather - 현재 날씨 즉시 조회 (여의도 기준)
/calendar - 오늘 Google Calendar 일정 즉시 조회
• 매일 05:00 날씨 자동 전송
• 매일 05:10 Google Calendar 일정 자동 전송

💰 **가계부 (Sisyphe → Google Sheets)**
/ledger - 카테고리 목록 조회
/ledger 지출 식비 점심 15000
/ledger 수입 급여 3000000

⚙️ **기타**
/start - 봇 시작 및 자동 알림 구독
/stop - 자동 알림 구독 해제
/help - 이 도움말 표시
"""
    await update.message.reply_text(help_text)

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """현재 날씨 조회"""
    chat_id = update.effective_chat.id
    status_msg = await update.message.reply_text("🌤️ 날씨 정보를 가져오는 중...")

    try:
        import sys
        sys.path.insert(0, os.path.join(DASHBOARD_DIR, 'execution'))
        from daily_alert import get_naver_weather

        loop = asyncio.get_running_loop()
        message = await loop.run_in_executor(None, lambda: get_naver_weather("여의도"))
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=message
        )
    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=f"❌ 날씨 조회 실패: {str(e)}"
        )


async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """오늘 캘린더 일정 조회"""
    chat_id = update.effective_chat.id
    status_msg = await update.message.reply_text("📅 일정을 가져오는 중...")

    try:
        import sys
        sys.path.insert(0, os.path.join(DASHBOARD_DIR, 'execution'))
        from daily_calendar import get_today_events, format_calendar_message

        loop = asyncio.get_running_loop()
        events = await loop.run_in_executor(None, get_today_events)
        message = format_calendar_message(events)
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=message,
            parse_mode='HTML'
        )
    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=f"❌ 일정 조회 실패: {str(e)}"
        )


async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """포트폴리오 리포트 조회"""
    chat_id = update.effective_chat.id
    
    # 처리 중 메시지
    status_msg = await update.message.reply_text("📊 포트폴리오 리포트를 생성하는 중...")
    
    try:
        import subprocess
        import sys
        
        # 기준가 + 수익률 먼저 갱신
        subprocess.run(
            [sys.executable, "calculate_wrap_nav.py"],
            capture_output=True, text=True, timeout=120
        )
        subprocess.run(
            [sys.executable, "calculate_returns.py"],
            capture_output=True, text=True, timeout=120
        )

        # daily_portfolio_report.py 실행
        result = subprocess.run(
            [sys.executable, "execution/daily_portfolio_report.py", "--no-send"],
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
                    text=report_message,
                    parse_mode='HTML'
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

        # 리포트 성공 시 dashboard 재생성 및 push
        if result.returncode == 0:
            import os
            script_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(script_dir)
            git_sync(parent_dir)
            result_dash = subprocess.run(
                [sys.executable, "execution/create_dashboard.py"],
                cwd=parent_dir, capture_output=True, text=True, timeout=120
            )
            if result_dash.returncode == 0:
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                subprocess.run(["git", "add", "index.html", "market.html", "wrap.html"], cwd=parent_dir, capture_output=True, timeout=30)
                subprocess.run(["git", "commit", "-m", f"포트폴리오 업데이트 ({now_str})"], cwd=parent_dir, capture_output=True, timeout=30)
                git_push_safe(parent_dir)
                logging.info("Dashboard updated via /portfolio command")

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

_NAVER_INDEX_CODES = {
    '^KS11': 'KOSPI',
    '^KQ11': 'KOSDAQ',
}

def _fetch_naver_index_return(naver_code):
    """네이버 금융에서 지수 등락률 크롤링 (fdr fallback용)"""
    import re, requests
    url = f'https://finance.naver.com/sise/sise_index.naver?code={naver_code}'
    r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
    r.encoding = 'euc-kr'
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, 'html.parser')
    elem = soup.find(id='change_value_and_rate')
    if not elem:
        return None
    text = elem.get_text()
    m = re.search(r'([+-]?\d[\d.]+)%', text)
    if not m:
        return None
    return float(m.group(1))


def fetch_price(code):
    """종목 실시간 가격 조회 (스레드에서 호출)"""
    import FinanceDataReader as fdr
    from datetime import timedelta, timezone
    import pandas as pd
    try:
        # 지수는 항상 네이버에서 직접 등락률 조회 (FDR 데이터 누락 이슈 방지)
        if code in _NAVER_INDEX_CODES:
            ret = _fetch_naver_index_return(_NAVER_INDEX_CODES[code])
            return code, ret

        df = fdr.DataReader(code, start=pd.Timestamp.now() - timedelta(days=30))
        # NaN Close 행 제거
        df = df.dropna(subset=['Close'])
        if len(df) < 2:
            return code, None
        # 최신 데이터가 오늘(KST) 것이 아니면 데이터 없음
        kst = timezone(timedelta(hours=9))
        today_kst = pd.Timestamp.now(tz=kst).normalize().tz_localize(None).date()
        latest_date = df.index[-1]
        if hasattr(latest_date, 'date'):
            latest_date = latest_date.date()
        if latest_date < today_kst:
            return code, None
        latest = df.iloc[-1]['Close']
        prev = df.iloc[-2]['Close']
        if prev == 0:
            return code, None
        return code, ((latest - prev) / prev) * 100
    except Exception:
        return code, None


def run_portfolio_update():
    """포트폴리오 테이블 업데이트 실행 (동기 - run_in_executor에서 호출)"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    dashboard_dir = DASHBOARD_DIR

    # 0. Wrap_NAV.xlsx에서 최신 포트폴리오 구성 반영 → portfolio_data.json 재생성
    logging.info("Update Step 0: Regenerating portfolio_data.json from Wrap_NAV.xlsx...")
    step0_result = subprocess.run(
        [sys.executable, "execution/create_portfolio_tables.py"],
        capture_output=True, text=True, timeout=180,
        cwd=dashboard_dir
    )
    if step0_result.returncode != 0:
        logging.error(f"Step 0 failed (rc={step0_result.returncode}): {step0_result.stderr[-500:]}")

    # 1. 기존 portfolio_data.json 읽기 (종목 코드/비중 이미 확정됨)
    logging.info("Update Step 1: Reading portfolio_data.json...")
    portfolio_file = os.path.join(dashboard_dir, 'portfolio_data.json')
    with open(portfolio_file, 'r', encoding='utf-8') as f:
        portfolio_data = json.load(f)

    # 전체 종목 코드 수집 (중복 제거) + 지수 추가
    all_codes = set()
    for key, stocks in portfolio_data.items():
        if key.startswith('_'):
            continue
        for s in stocks:
            all_codes.add(s['code'])
    all_codes.update(['^KS11', '^KQ11'])

    # 2. 실시간 주가 병렬 조회
    logging.info(f"Update Step 2: Fetching {len(all_codes)} stock prices...")
    price_map = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_price, code): code for code in all_codes}
        for future in as_completed(futures):
            code, today_return = future.result()
            price_map[code] = today_return

    # 지수 수익률 저장
    portfolio_data['_index'] = {
        'KOSPI': price_map.get('^KS11'),
        'KOSDAQ': price_map.get('^KQ11'),
    }

    # 3. today_return, contribution, cumulative_return 업데이트
    logging.info("Update Step 3: Updating returns...")
    for portfolio_name, stocks in portfolio_data.items():
        if portfolio_name.startswith('_'):
            continue
        for s in stocks:
            today_return = price_map.get(s['code'])
            prev_cumulative = s.get('cumulative_return')
            s['today_return'] = today_return
            if today_return is not None:
                s['contribution'] = (s['weight'] / 100) * (today_return / 100) * 1000
                if prev_cumulative is not None:
                    s['cumulative_return'] = ((1 + prev_cumulative / 100) * (1 + today_return / 100) - 1) * 100
            else:
                s['contribution'] = None

    # 4. portfolio_data.json 저장 (_로 시작하는 임시 키 제외)
    save_data = {k: v for k, v in portfolio_data.items() if not k.startswith('_')}
    with open(portfolio_file, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

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
        ["git", "add", "portfolio_data.json", "index.html", "market.html", "wrap.html"],
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
        if not git_push_safe(dashboard_dir):
            logging.warning("Git push failed after commit")
    else:
        logging.info(f"No changes to commit: {commit_result.stdout}")

    return portfolio_data


def format_update_summary(portfolio_data):
    """포트폴리오 업데이트 요약 메시지 생성"""
    from datetime import timezone, timedelta
    KST = timezone(timedelta(hours=9))
    now_str = datetime.datetime.now(tz=KST).strftime("%Y-%m-%d %H:%M")
    lines = [f"📊 포트폴리오 업데이트", f"⏰ {now_str} (KST)"]

    index = portfolio_data.get('_index', {})
    kospi = index.get('KOSPI')
    kosdaq = index.get('KOSDAQ')
    import math
    kospi_str = f"{kospi:+.2f}%" if (kospi is not None and not math.isnan(kospi)) else "N/A"
    kosdaq_str = f"{kosdaq:+.2f}%" if (kosdaq is not None and not math.isnan(kosdaq)) else "N/A"
    lines.append(f"<b><u>KOSPI {kospi_str}  |  KOSDAQ {kosdaq_str}</u></b>")
    lines.append("")

    for portfolio_name, stocks in portfolio_data.items():
        if portfolio_name.startswith('_'):
            continue
        # 포트폴리오 가중 평균 수익률
        # 비중 합계가 100% 미만이면 나머지는 현금(수익률 0%)으로 처리
        weighted_return = sum(
            s['weight'] * (s['today_return'] or 0)
            for s in stocks
        ) / 100

        lines.append(f"<b><u>[{portfolio_name}]</u></b>")
        lines.append(f"<b><u>오늘: {weighted_return:+.1f}%</u></b>")

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
            text=summary,
            parse_mode='HTML'
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
                    await context.bot.send_message(chat_id=chat_id, text=summary, parse_mode='HTML')
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
        git_sync(parent_dir)

        # 1. 기준가 업데이트 (검증 실패 시 1회 재시도)
        logging.info("Step 1: Updating NAV prices...")
        for nav_attempt in range(1, 3):
            result_nav = subprocess.run(
                [sys.executable, "calculate_wrap_nav.py"],
                capture_output=True,
                text=True,
                timeout=120
            )
            if result_nav.returncode == 0:
                break
            logging.warning(f"NAV update attempt {nav_attempt} failed: {result_nav.stdout}")
            if nav_attempt == 2:
                logging.error(f"NAV update failed after retry: {result_nav.stderr}")
                os.chdir(original_dir)
                return

        logging.info("NAV prices updated successfully")

        # 1-5. portfolio_data.json 재생성 (Wrap_NAV.xlsx 최신 구성 반영)
        logging.info("Step 1-5: Regenerating portfolio_data.json from Wrap_NAV.xlsx...")
        subprocess.run(
            [sys.executable, "execution/create_portfolio_tables.py"],
            capture_output=True, text=True, timeout=180
        )

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

        # 2-5. Wrap_NAV.xlsx 변경사항 GitHub에 push
        logging.info("Step 2-5: Pushing updated Wrap_NAV.xlsx to GitHub...")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        subprocess.run(["git", "add", "Wrap_NAV.xlsx"], cwd=parent_dir, capture_output=True, timeout=30)
        commit_result = subprocess.run(
            ["git", "commit", "-m", f"Update Wrap_NAV ({now_str})"],
            cwd=parent_dir, capture_output=True, text=True, timeout=30
        )
        if commit_result.returncode == 0:
            git_push_safe(parent_dir)
            logging.info("Wrap_NAV.xlsx pushed to GitHub")
        else:
            logging.info("No changes to Wrap_NAV.xlsx to commit")

        # 2-7. WRAP 차트 이미지 재생성
        logging.info("Step 2-7: Drawing wrap charts...")
        result_wcharts = subprocess.run(
            [sys.executable, "execution/draw_wrap_charts.py"],
            capture_output=True, text=True, timeout=120
        )
        if result_wcharts.returncode == 0:
            logging.info("Wrap charts generated successfully")
        else:
            logging.warning(f"Wrap charts generation failed: {result_wcharts.stderr}")

        # 3. 투자유의종목 페이지 재생성
        logging.info("Step 3-0: Regenerating market alert page...")
        subprocess.run(
            [sys.executable, "execution/create_market_alert.py"],
            capture_output=True, text=True, timeout=180
        )

        # 3. Dashboard 재생성 및 push
        logging.info("Step 3: Regenerating dashboard...")
        result_dashboard = subprocess.run(
            [sys.executable, "execution/create_dashboard.py"],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result_dashboard.returncode == 0:
            subprocess.run(["git", "add", "index.html", "market.html", "wrap.html", "market_alert.html", "charts/"], cwd=parent_dir, capture_output=True, timeout=30)
            commit_dash = subprocess.run(
                ["git", "commit", "-m", f"포트폴리오 업데이트 ({now_str})"],
                cwd=parent_dir, capture_output=True, text=True, timeout=30
            )
            if commit_dash.returncode == 0:
                git_push_safe(parent_dir)
                logging.info("Dashboard updated and pushed")
        else:
            logging.error(f"Dashboard generation failed: {result_dashboard.stderr}")

        # 3-5. 투자일지 시장 데이터 수집
        logging.info("Step 3-5: Fetching journal market data...")
        result_journal = subprocess.run(
            [sys.executable, "execution/fetch_journal_data.py"],
            capture_output=True, text=True, timeout=120
        )
        if result_journal.returncode == 0:
            logging.info("Journal data collected successfully")
        else:
            logging.warning(f"Journal data failed: {result_journal.stderr[:100]}")

        # 4. 포트폴리오 리포트 생성 및 전송
        logging.info("Step 4: Generating portfolio report...")
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

async def daily_featured_job(context: ContextTypes.DEFAULT_TYPE):
    """매일 18:00 Featured 종목 수집 + 대시보드 갱신. 실패 시 19:00에 재시도."""
    logging.info("Daily featured job started")
    try:
        import subprocess, sys, os
        parent_dir = DASHBOARD_DIR
        os.chdir(parent_dir)
        git_sync(parent_dir)

        result = subprocess.run(
            [sys.executable, "execution/fetch_featured_data.py"],
            capture_output=True, text=True, timeout=180, cwd=parent_dir
        )
        # 당일 데이터 수집 여부 확인 (stdout에서 오늘 날짜 확인)
        today_str = datetime.datetime.now(tz=KST).strftime('%Y-%m-%d')
        if result.returncode != 0 or today_str not in result.stdout:
            logging.warning(f"Featured data: 당일 데이터 미수집, 19:00 재시도 예약")
            for chat_id in SUBSCRIBERS:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=f"⏳ Featured 데이터 미수집 ({today_str}), 19:00에 재시도합니다.")
                except: pass
            # 1시간 후 재시도
            context.job_queue.run_once(daily_featured_retry_job, when=3600)
            return

        logging.info("Featured data collected successfully")
        # Dashboard 재생성 + push
        subprocess.run([sys.executable, "execution/create_dashboard.py"],
                       capture_output=True, text=True, timeout=120, cwd=parent_dir)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        subprocess.run(["git", "add", "featured.html", "featured_data.json"], cwd=parent_dir, capture_output=True, timeout=30)
        commit_result = subprocess.run(["git", "commit", "-m", f"Featured 업데이트 ({now_str})"],
                                       cwd=parent_dir, capture_output=True, text=True, timeout=30)
        if commit_result.returncode == 0:
            git_push_safe(parent_dir)
            logging.info("Featured dashboard pushed")
    except Exception as e:
        logging.error(f"Daily featured job error: {e}")


async def daily_featured_retry_job(context: ContextTypes.DEFAULT_TYPE):
    """19:00 Featured 재시도"""
    logging.info("Featured retry job started")
    try:
        import subprocess, sys, os
        parent_dir = DASHBOARD_DIR
        os.chdir(parent_dir)

        result = subprocess.run(
            [sys.executable, "execution/fetch_featured_data.py"],
            capture_output=True, text=True, timeout=180, cwd=parent_dir
        )
        if result.returncode == 0:
            logging.info("Featured retry: data collected")
            subprocess.run([sys.executable, "execution/create_dashboard.py"],
                           capture_output=True, text=True, timeout=120, cwd=parent_dir)
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            subprocess.run(["git", "add", "featured.html", "featured_data.json"], cwd=parent_dir, capture_output=True, timeout=30)
            commit_result = subprocess.run(["git", "commit", "-m", f"Featured 업데이트 ({now_str})"],
                                           cwd=parent_dir, capture_output=True, text=True, timeout=30)
            if commit_result.returncode == 0:
                git_push_safe(parent_dir)
        else:
            logging.warning(f"Featured retry also failed, will be collected at 23:00 GHA")
            for chat_id in SUBSCRIBERS:
                try:
                    await context.bot.send_message(chat_id=chat_id, text="❌ Featured 데이터 19:00 재시도도 실패했습니다. 23:00 GHA에서 수집됩니다.")
                except: pass
    except Exception as e:
        logging.error(f"Featured retry error: {e}")


def _nightly_refresh_sync():
    """23:00 당일 포트폴리오 데이터 반영 (동기 함수)"""
    dashboard_dir = DASHBOARD_DIR
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # 최신 Wrap_NAV.xlsx 받기
    git_sync(dashboard_dir)

    # portfolio_data.json 재생성 (23:00 이후이므로 당일 데이터 포함)
    subprocess.run(
        [sys.executable, "execution/create_portfolio_tables.py"],
        cwd=dashboard_dir, capture_output=True, text=True, timeout=180
    )

    # SEIBro TOP 50 수집은 GHA에서 실행 (VM 메모리 부족으로 Selenium 불가)

    # 투자유의종목 페이지 재생성
    subprocess.run(
        [sys.executable, "execution/create_market_alert.py"],
        cwd=dashboard_dir, capture_output=True, text=True, timeout=180
    )

    # 대시보드 재생성
    subprocess.run(
        [sys.executable, "execution/create_dashboard.py"],
        cwd=dashboard_dir, capture_output=True, text=True, timeout=120
    )

    # Git push
    subprocess.run(
        ["git", "add", "portfolio_data.json", "index.html", "market.html", "wrap.html", "market_alert.html", "seibro.html", "dataset.csv"],
        cwd=dashboard_dir, capture_output=True, timeout=30
    )
    commit_result = subprocess.run(
        ["git", "commit", "-m", f"당일 포트폴리오 반영 ({now_str})"],
        cwd=dashboard_dir, capture_output=True, text=True, timeout=30
    )
    if commit_result.returncode == 0:
        git_push_safe(dashboard_dir)
        logging.info("Nightly portfolio data pushed to GitHub")
    else:
        logging.info("Nightly refresh: no changes to commit")


async def nightly_portfolio_refresh_job(context: ContextTypes.DEFAULT_TYPE):
    """매일 23:00 당일 주문 포트폴리오/섹터 반영"""
    logging.info("Nightly portfolio refresh job started (23:00 KST)")
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _nightly_refresh_sync)
        logging.info("Nightly portfolio refresh completed")
    except Exception as e:
        logging.error(f"Nightly portfolio refresh failed: {e}")


async def daily_weather_job(context: ContextTypes.DEFAULT_TYPE):
    """매일 05:00 날씨 알림 (daily_alert.py 실행)"""
    logging.info("Daily weather job started")
    try:
        result = subprocess.run(
            [sys.executable, "execution/daily_alert.py"],
            capture_output=True, text=True, encoding='utf-8',
            timeout=60, cwd=DASHBOARD_DIR
        )
        if result.returncode == 0:
            logging.info("Daily weather job completed successfully")
        else:
            logging.error(f"Daily weather job failed: {result.stderr}")
    except Exception as e:
        logging.error(f"Daily weather job error: {e}")


async def daily_headlines_job(context: ContextTypes.DEFAULT_TYPE):
    """매일 05:10 리서치 헤드라인 알림 (당일/전일 데이터만 전송)"""
    logging.info("Daily headlines job started")
    try:
        import json as _json
        headlines_file = os.path.join(DASHBOARD_DIR, 'research_headlines.json')
        if os.path.exists(headlines_file):
            with open(headlines_file, 'r', encoding='utf-8') as f:
                data = _json.load(f)
            headlines = data.get('headlines', [])
            date = data.get('date', '')
            # 날짜 신선도 체크: 어제 또는 오늘 데이터만 전송
            _KST = datetime.timezone(datetime.timedelta(hours=9))
            today_kst = datetime.datetime.now(tz=_KST).date()
            yesterday_kst = today_kst - datetime.timedelta(days=1)
            try:
                headline_date = datetime.datetime.strptime(date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                headline_date = None
            if headline_date and headline_date < yesterday_kst:
                logging.info(f"Research headlines 스킵: 오래된 데이터 ({date})")
                headlines = []
            if headlines:
                # 엄중(important) 먼저, 일반 나중에 정렬
                important = [h for h in headlines if isinstance(h, dict) and h.get('important')]
                normal = [h for h in headlines if not (isinstance(h, dict) and h.get('important'))]
                sorted_headlines = important + normal

                msg = f"📋 <b>Research Notes ({date})</b>\n\n"
                for i, h in enumerate(sorted_headlines):
                    title = h.get('title', '') if isinstance(h, dict) else h
                    summary = h.get('summary', '') if isinstance(h, dict) else ''
                    # 엄중 → 일반 전환 시 구분선
                    if i == len(important) and important:
                        msg += "————————————————\n\n"
                    msg += f"- <b><u>{title}</u></b>\n"
                    if summary:
                        msg += f"  {summary}\n"
                    msg += "\n"
                for chat_id in SUBSCRIBERS:
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
                    except Exception as e:
                        logging.error(f"Research headline 전송 실패: {e}")
                logging.info(f"Research headlines sent: {len(headlines)}건")
    except Exception as e:
        logging.error(f"Research headlines error: {e}")

async def daily_calendar_job(context: ContextTypes.DEFAULT_TYPE):
    """매일 05:10 Google Calendar 일정 알림 (daily_calendar.py 실행)"""
    logging.info("Daily calendar job started")
    try:
        result = subprocess.run(
            [sys.executable, "execution/daily_calendar.py"],
            capture_output=True, text=True, encoding='utf-8',
            timeout=60, cwd=DASHBOARD_DIR
        )
        if result.returncode == 0:
            logging.info("Daily calendar job completed successfully")
        else:
            logging.error(f"Daily calendar job failed: {result.stderr}")
    except Exception as e:
        logging.error(f"Daily calendar job error: {e}")

    # 하이라이트 일정 D-Day 알림
    await check_dday_alerts(context)


async def check_dday_alerts(context):
    """하이라이트 일정 한 달 전/일주일 전/하루 전 알림"""
    if not SUBSCRIBERS:
        return

    try:
        from korean_lunar_calendar import KoreanLunarCalendar
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        KST = datetime.timezone(datetime.timedelta(hours=9))
        today = datetime.datetime.now(tz=KST).date()

        # 1) 음력 기념일 (생일 + 설/추석)
        LUNAR_EVENTS = [
            {'name': '🎂 혜자 생일', 'month': 3, 'day': 4},
            {'name': '🎂 동석 생일', 'month': 3, 'day': 12},
            {'name': '🎂 연순 생일', 'month': 5, 'day': 3},
            {'name': '🎂 맹호 생일', 'month': 8, 'day': 16},
            {'name': '🧧 설날', 'month': 1, 'day': 1},
            {'name': '🌕 추석', 'month': 8, 'day': 15},
        ]

        highlight_events = []
        cal = KoreanLunarCalendar()
        for year in [today.year, today.year + 1]:
            for ev in LUNAR_EVENTS:
                try:
                    if cal.setLunarDate(year, ev['month'], ev['day'], False):
                        d = datetime.date(cal.solarYear, cal.solarMonth, cal.solarDay)
                        highlight_events.append({'name': ev['name'], 'date': d})
                except:
                    pass

        # 2) Google Calendar "D-day |" 이벤트 (옥쥬와 빵빵이)
        try:
            service_account_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_KEY')
            if service_account_json:
                sa_info = json.loads(service_account_json)
                creds = service_account.Credentials.from_service_account_info(
                    sa_info, scopes=['https://www.googleapis.com/auth/calendar.readonly']
                )
                service = build('calendar', 'v3', credentials=creds)
                cal_id = 'a49c912f9e11c6e050c873312ae00a314e45dc075540c86cf428c9921fcbc20c@group.calendar.google.com'
                time_min = datetime.datetime.combine(today, datetime.time.min).isoformat() + '+09:00'
                time_max = datetime.datetime.combine(today + datetime.timedelta(days=400), datetime.time.min).isoformat() + '+09:00'
                events_result = service.events().list(
                    calendarId=cal_id, timeMin=time_min, timeMax=time_max,
                    singleEvents=True, orderBy='startTime', maxResults=200
                ).execute()
                for item in events_result.get('items', []):
                    summary = item.get('summary', '')
                    if summary.startswith('D-day |') or summary.startswith('D-day|'):
                        clean = summary.split('|', 1)[1].strip()
                        start = item['start'].get('date') or item['start'].get('dateTime', '')[:10]
                        d = datetime.date.fromisoformat(start)
                        highlight_events.append({'name': f'📌 {clean}', 'date': d})
        except Exception as e:
            logging.warning(f"D-Day Google Calendar fetch failed: {e}")

        # 3) 알림 대상 확인 (30일 전, 7일 전, 1일 전)
        alerts = []
        for ev in highlight_events:
            diff = (ev['date'] - today).days
            if diff == 30:
                alerts.append(f"📅 <b>[한 달 전]</b> {ev['name']}\n    {ev['date'].strftime('%Y-%m-%d')} (D-30)")
            elif diff == 7:
                alerts.append(f"📅 <b>[일주일 전]</b> {ev['name']}\n    {ev['date'].strftime('%Y-%m-%d')} (D-7)")
            elif diff == 1:
                alerts.append(f"📅 <b>[내일]</b> {ev['name']}\n    {ev['date'].strftime('%Y-%m-%d')} (D-1)")

        if alerts:
            msg = "━━━━━━━━━━━━━━━\n<b>🔔 D-Day 알림</b>\n━━━━━━━━━━━━━━━\n\n"
            msg += "\n\n".join(alerts)
            for chat_id in SUBSCRIBERS:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
                except Exception as e:
                    logging.error(f"D-Day alert send failed to {chat_id}: {e}")
            logging.info(f"D-Day alerts sent: {len(alerts)} items")
        else:
            logging.info("No D-Day alerts for today")

    except Exception as e:
        logging.error(f"D-Day alert check failed: {e}")

# ============================================================
# 가계부 (Sisyphe) - Telegram → Google Sheets
# ============================================================
SISYPHE_SHEET_ID = '1V41yiwO4VrVUhjhqHyu8JGsuGcqw6pZen0NHdxzXHGs'

def _get_sheets_service():
    """Google Sheets API 서비스 (서비스 계정)"""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    sa_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_KEY')
    if not sa_json:
        return None
    sa_info = json.loads(sa_json)
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return build('sheets', 'v4', credentials=creds)

def _read_sheet(service, sheet_name):
    """시트에서 전체 데이터 읽기"""
    result = service.spreadsheets().values().get(
        spreadsheetId=SISYPHE_SHEET_ID, range=sheet_name
    ).execute()
    return result.get('values', [])

def _append_row(service, sheet_name, row):
    """시트에 행 추가"""
    service.spreadsheets().values().append(
        spreadsheetId=SISYPHE_SHEET_ID,
        range=sheet_name,
        valueInputOption='USER_ENTERED',
        insertDataOption='INSERT_ROWS',
        body={'values': [row]}
    ).execute()

async def ledger_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ledger 지출 15000 식비 점심"""
    args = context.args

    service = _get_sheets_service()
    if not service:
        await update.message.reply_text("❌ Google 서비스 계정이 설정되지 않았습니다.")
        return

    # 인자 없이 /ledger만 입력 → 카테고리 목록 + 사용법 표시
    if not args:
        try:
            rows = _read_sheet(service, '카테고리')
            expense_cats, income_cats = [], []
            for r in rows[1:]:  # skip header
                if len(r) >= 2:
                    if r[0] == '지출': expense_cats.append(r[1])
                    elif r[0] == '수입': income_cats.append(r[1])
            cat_msg = "<b>카테고리</b>\n"
            if expense_cats:
                cat_msg += f"지출: {' · '.join(expense_cats)}\n"
            if income_cats:
                cat_msg += f"수입: {' · '.join(income_cats)}\n"
            cat_msg += "\n"
        except:
            cat_msg = ""

        await update.message.reply_text(
            f"{cat_msg}"
            "📝 <b>사용법</b>\n\n"
            "<code>/ledger 지출 식비 점심 15000</code>\n"
            "<code>/ledger 수입 급여 3000000</code>\n\n"
            "형식: /ledger [지출|수입] [카테고리] [메모] [금액]",
            parse_mode='HTML'
        )
        return

    if len(args) < 3:
        await update.message.reply_text("❌ 형식: /ledger [지출|수입] [카테고리] [메모] [금액]", parse_mode='HTML')
        return

    tx_type_str = args[0]
    if tx_type_str in ['지출', 'ㅈ']:
        tx_type = '지출'
    elif tx_type_str in ['수입', 'ㅅ']:
        tx_type = '수입'
    else:
        await update.message.reply_text("❌ 유형은 '지출' 또는 '수입'으로 입력하세요.")
        return

    # 마지막 인자가 금액
    try:
        amount = int(args[-1].replace(',', ''))
        if amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ 마지막에 금액(숫자)을 입력하세요.")
        return

    category = args[1]
    memo = ' '.join(args[2:-1]) if len(args) > 3 else ''

    # 카테고리 유효성 검사
    try:
        rows = _read_sheet(service, '카테고리')
        valid_cats = [r[1] for r in rows[1:] if len(r) >= 2 and r[0] == tx_type]
        if category not in valid_cats:
            cat_list = ' · '.join(valid_cats) if valid_cats else '없음'
            await update.message.reply_text(f"❌ '{category}'는 유효하지 않은 카테고리입니다.\n\n{tx_type}: {cat_list}", parse_mode='HTML')
            return
    except:
        pass

    try:
        KST = datetime.timezone(datetime.timedelta(hours=9))
        today_str = datetime.datetime.now(tz=KST).strftime('%Y-%m-%d')

        _append_row(service, '거래내역', [today_str, tx_type, category, str(amount), memo])

        type_emoji = '🔴' if tx_type == '지출' else '🟠'
        msg = (
            f"{type_emoji} <b>{tx_type}</b> 입력 완료\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📅 {today_str}\n"
            f"📂 {category}\n"
            f"💰 {amount:,}원\n"
        )
        if memo:
            msg += f"📝 {memo}\n"

        # 지출 시 예산 소진율 표시
        if tx_type == '지출':
            try:
                pct, budget_total = check_budget()
                if pct is not None:
                    bar_len = 10
                    filled = min(bar_len, round(pct / 100 * bar_len))
                    bar = '█' * filled + '░' * (bar_len - filled)
                    msg += f"\n📊 예산 소진율 {pct}% [{bar}]"
            except:
                pass

        await update.message.reply_text(msg, parse_mode='HTML')
        logging.info(f"Sisyphe ledger: {tx_type} {amount} {category} {memo}")


    except Exception as e:
        logging.error(f"Sisyphe ledger error: {e}")
        await update.message.reply_text(f"❌ 저장 실패: {str(e)}")


# ============================================================
# 가계부 (선유듀오) - Telegram → Google Sheets
# ============================================================
SEONYUDUO_SHEET_ID = '1w6q3UwUER7oINuk50LyMzgF2K0Fbt2wgSVJ34vImo0g'

def _get_seonyuduo_service():
    """선유듀오용 Google Sheets API 서비스"""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    sa_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_KEY')
    if not sa_json:
        return None
    sa_info = json.loads(sa_json)
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return build('sheets', 'v4', credentials=creds)

async def ledger2_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ledger2 지출 식비 점심 15000 생활비"""
    args = context.args

    service = _get_seonyuduo_service()
    if not service:
        await update.message.reply_text("❌ Google 서비스 계정이 설정되지 않았습니다.")
        return

    # 인자 없이 /ledger2만 입력 → 카테고리 + 통장 목록 표시
    if not args:
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=SEONYUDUO_SHEET_ID, range='카테고리!A:C'
            ).execute()
            rows = result.get('values', [])
            expense_cats, income_cats, accounts = [], [], []
            for r in rows:
                if len(r) >= 2:
                    if r[0] == '지출' and r[1] not in expense_cats: expense_cats.append(r[1])
                    elif r[0] == '수입' and r[1] not in income_cats: income_cats.append(r[1])
                if len(r) >= 3 and r[2] and r[2] not in accounts: accounts.append(r[2])
        except:
            expense_cats, income_cats, accounts = [], [], []

        msg = "<b>카테고리</b>\n"
        if expense_cats:
            msg += f"지출: {' · '.join(expense_cats)}\n"
        if income_cats:
            msg += f"수입: {' · '.join(income_cats)}\n"
        if accounts:
            msg += f"통장: {' · '.join(accounts)}\n"
        msg += "\n"
        msg += (
            "📝 <b>사용법</b>\n\n"
            "<code>/ledger2 지출 식비 점심 15000 생활비</code>\n"
            "<code>/ledger2 수입 급여 생활비충원 800000 생활비</code>\n\n"
            "형식: /ledger2 [유형] [카테고리] [메모] [금액] [통장]"
        )
        await update.message.reply_text(msg, parse_mode='HTML')
        return

    if len(args) < 4:
        await update.message.reply_text("❌ 형식: /ledger2 [유형] [카테고리] [메모] [금액] [통장]", parse_mode='HTML')
        return

    tx_type_str = args[0]
    if tx_type_str in ['지출', 'ㅈ']:
        tx_type = '지출'
    elif tx_type_str in ['수입', 'ㅅ']:
        tx_type = '수입'
    else:
        await update.message.reply_text("❌ 유형은 '지출/ㅈ' 또는 '수입/ㅅ'으로 입력하세요.")
        return

    category = args[1]

    # 카테고리 유효성 검사
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SEONYUDUO_SHEET_ID, range='카테고리!A:B'
        ).execute()
        ref_rows = result.get('values', [])
        valid_cats = [r[1] for r in ref_rows if len(r) >= 2 and r[0] == tx_type]
        if category not in valid_cats:
            cat_list = ' · '.join(valid_cats) if valid_cats else '없음'
            await update.message.reply_text(f"❌ '{category}'는 유효하지 않은 카테고리입니다.\n\n{tx_type}: {cat_list}", parse_mode='HTML')
            return
    except:
        pass

    # 마지막 인자 = 통장, 그 앞 = 금액
    account = args[-1]
    try:
        amount = int(args[-2].replace(',', ''))
        if amount <= 0:
            raise ValueError
        memo = ' '.join(args[2:-2]) if len(args) > 4 else ''
    except:
        # 통장 생략된 경우: 마지막이 금액
        try:
            amount = int(args[-1].replace(',', ''))
            if amount <= 0:
                raise ValueError
            memo = ' '.join(args[2:-1]) if len(args) > 3 else ''
            account = ''
        except:
            await update.message.reply_text("❌ 금액(숫자)을 확인하세요.")
            return

    try:
        KST = datetime.timezone(datetime.timedelta(hours=9))
        today_str = datetime.datetime.now(tz=KST).strftime('%Y-%m-%d')

        service.spreadsheets().values().append(
            spreadsheetId=SEONYUDUO_SHEET_ID,
            range='가계부!A1:F1',
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body={'values': [[today_str, tx_type, category, amount, memo, account]]}
        ).execute()

        type_emoji = '🔴' if tx_type == '지출' else '🟢'
        msg = (
            f"{type_emoji} <b>{tx_type}</b> 입력 완료\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📅 {today_str}\n"
            f"📂 {category}\n"
            f"💰 {amount:,}원\n"
        )
        if memo:
            msg += f"📝 {memo}\n"
        if account:
            msg += f"🏦 {account}\n"

        await update.message.reply_text(msg, parse_mode='HTML')
        logging.info(f"SeonyuDuo ledger: {tx_type} {amount} {category} {memo} {account}")

    except Exception as e:
        logging.error(f"SeonyuDuo ledger error: {e}")
        await update.message.reply_text(f"❌ 저장 실패: {str(e)}")


# ============================================================
# 투자일지 - 장전계획/장후복기 입력
# ============================================================
JOURNAL_SHEET_ID = '13HXDxF62ILXyRz7meRZ5CxJT5HfWAwIKc8IsCavuVXk'

def _get_journal_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    sa_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_KEY')
    if not sa_json:
        return None
    sa_info = json.loads(sa_json)
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return build('sheets', 'v4', credentials=creds)

async def journal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/journal 장전 or /journal 장후 내용"""
    service = _get_journal_service()
    if not service:
        await update.message.reply_text("❌ Google 서비스 계정이 설정되지 않았습니다.")
        return

    # 원본 텍스트에서 줄바꿈 보존하여 파싱
    raw_text = update.message.text or ''
    parts = raw_text.split(None, 2)  # ['/journal', '장전', '나머지 전체']
    if len(parts) < 3:
        await update.message.reply_text(
            "<b>투자일지 입력</b>\n\n"
            "<code>/journal 장전 오늘은 매수 중지 예정</code>\n"
            "<code>/journal 장후 예상대로 하락, 관망 유지</code>\n\n"
            "형식: /journal [장전|장후] [내용]",
            parse_mode='HTML'
        )
        return

    entry_type = parts[1]
    content = parts[2]

    if entry_type not in ['장전', '장후']:
        await update.message.reply_text("❌ '장전' 또는 '장후'를 입력하세요.")
        return

    col = 'C' if entry_type == '장전' else 'D'  # C=장전계획, D=장후복기
    KST_tz = datetime.timezone(datetime.timedelta(hours=9))
    today = datetime.datetime.now(tz=KST_tz)
    today_str = today.strftime('%Y-%m-%d')
    dow_names = ['월', '화', '수', '목', '금', '토', '일']
    dow = dow_names[today.weekday()]

    try:
        # Journal 시트에서 오늘 날짜 행 찾기
        result = service.spreadsheets().values().get(
            spreadsheetId=JOURNAL_SHEET_ID, range='Journal!A:D'
        ).execute()
        rows = result.get('values', [])

        row_num = None
        for i, row in enumerate(rows):
            if row and today_str in str(row[0]):
                row_num = i + 1
                break

        if row_num:
            # 기존 행 업데이트
            service.spreadsheets().values().update(
                spreadsheetId=JOURNAL_SHEET_ID,
                range=f'Journal!{col}{row_num}',
                valueInputOption='USER_ENTERED',
                body={'values': [[content]]}
            ).execute()
        else:
            # 새 행 추가
            new_row = [today_str, dow, '', '']
            idx = 2 if entry_type == '장전' else 3
            new_row[idx] = content
            service.spreadsheets().values().append(
                spreadsheetId=JOURNAL_SHEET_ID,
                range='Journal!A1:D1',
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': [new_row]}
            ).execute()

        label = '장전 계획' if entry_type == '장전' else '장후 복기'
        await update.message.reply_text(
            f"✅ <b>{label}</b> 저장 완료\n"
            f"📅 {today_str} ({dow})\n"
            f"📝 {content}",
            parse_mode='HTML'
        )
        logging.info(f"Journal {entry_type}: {content}")

    except Exception as e:
        logging.error(f"Journal error: {e}")
        await update.message.reply_text(f"❌ 저장 실패: {str(e)}")


# ============================================================
# WiseReport 리서치 리포트 알림
# ============================================================
_wisereport_sent = set()  # (기업명/산업명, 제목) 튜플로 중복 방지
_wisereport_sent_date = None


def fetch_wisereport(fmt, date_str):
    """WiseReport 리포트 서머리 스크래핑. fmt=1(기업), fmt=2(산업)"""
    import urllib.request
    from bs4 import BeautifulSoup

    url = f'https://comp.wisereport.co.kr/wiseReport/summary/ReportSummary.aspx?ee={date_str}&fmt={fmt}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req, timeout=20).read().decode('utf-8', errors='replace')
    soup = BeautifulSoup(html, 'html.parser')

    tbl = soup.find('table', class_='Summary_list')
    if not tbl:
        return []

    results = []
    for row in tbl.find_all('tr', class_=['itm_t1', 'alt_t1']):
        cells = row.find_all(['th', 'td'])
        if fmt == 1 and len(cells) >= 7:
            summary = cells[6].get_text(strip=True)
            if not summary:
                continue
            name_div = cells[0].find('div')
            title_full = cells[5].get('title', '') or cells[5].get_text(strip=True)
            results.append({
                'name': name_div.get('title', '') if name_div else cells[0].get_text(strip=True),
                'analyst': cells[1].get_text(' ', strip=True),
                'opinion': cells[2].get_text(strip=True),
                'target': cells[3].get_text(strip=True).replace('\n', ''),
                'close': cells[4].get_text(strip=True),
                'title': title_full,
                'summary': summary,
            })
        elif fmt == 2 and len(cells) >= 6:
            summary = cells[5].get_text(strip=True)
            if not summary:
                continue
            results.append({
                'name': cells[0].get_text(strip=True),
                'analyst': cells[1].get_text(' ', strip=True),
                'opinion': cells[2].get_text(strip=True),
                'prev_opinion': cells[3].get_text(strip=True),
                'title': cells[4].get('title', '') or cells[4].get_text(strip=True),
                'summary': summary,
            })
    return results


def format_wisereport_msg(company_data, industry_data, is_update=False):
    """텔레그램 HTML 메시지 생성. 같은 종목/산업 그룹핑, 4096자 분할."""
    from collections import OrderedDict
    now_str = datetime.datetime.now(KST).strftime('%Y-%m-%d %H:%M')
    header = f"📋 <b>리서치 리포트</b> ({now_str})"
    if is_update:
        header = f"📋 <b>리서치 리포트 추가</b> ({now_str})"

    lines = [header, '']

    if company_data:
        lines.append('<b>━━ 기업 ━━</b>')
        # 같은 종목끼리 그룹핑 (출현 순서 유지)
        groups = OrderedDict()
        for r in company_data:
            nm = r['name'].split('(')[0].strip()
            if nm not in groups:
                groups[nm] = []
            groups[nm].append(r)

        for nm, items in groups.items():
            code = items[0]['name'].split('(')[-1].replace(')', '') if '(' in items[0]['name'] else ''
            lines.append(f"<b>{nm}</b> ({code})" if code else f"<b>{nm}</b>")
            for r in items:
                op = r['opinion'] or '-'
                tgt = r['target'] or '-'
                analyst = r['analyst'].replace('[', '').replace(']', '')
                lines.append(f"  {analyst} | {op} | {tgt}")
                lines.append(f"  {r['title']}")
                summ = r['summary'].replace('▶ ', '▶').replace('▶', '\n  ▶')
                if summ.startswith('\n'):
                    summ = summ[1:]
                lines.append(f"  {summ}")
            lines.append('')

    if industry_data:
        lines.append('<b>━━ 산업 ━━</b>')
        groups = OrderedDict()
        for r in industry_data:
            nm = r['name']
            if nm not in groups:
                groups[nm] = []
            groups[nm].append(r)

        for nm, items in groups.items():
            lines.append(f"<b>{nm}</b>")
            for r in items:
                prev = r.get('prev_opinion', '') or '-'
                curr = r.get('opinion', '') or '-'
                analyst = r['analyst'].replace('[', '').replace(']', '')
                lines.append(f"  {analyst} | {prev} → {curr}")
                lines.append(f"  {r['title']}")
                summ = r['summary'].replace('▶ ', '▶').replace('▶', '\n  ▶')
                if summ.startswith('\n'):
                    summ = summ[1:]
                lines.append(f"  {summ}")
            lines.append('')

    # 4096자 제한 분할
    messages = []
    current = ''
    for line in lines:
        if len(current) + len(line) + 1 > 4000:
            messages.append(current)
            current = line + '\n'
        else:
            current += line + '\n'
    if current.strip():
        messages.append(current)
    return messages


async def wisereport_job(context):
    """WiseReport 리서치 리포트 스크래핑 + 텔레그램 전송"""
    global _wisereport_sent, _wisereport_sent_date

    now = datetime.datetime.now(KST)
    today_str = now.strftime('%Y-%m-%d')

    # 날짜 바뀌면 초기화
    if _wisereport_sent_date != today_str:
        _wisereport_sent = set()
        _wisereport_sent_date = today_str

    is_update = len(_wisereport_sent) > 0  # 첫 전송이 아니면 업데이트

    try:
        company = fetch_wisereport(1, today_str)
        industry = fetch_wisereport(2, today_str)
    except Exception as e:
        logging.warning(f"WiseReport fetch failed: {e}")
        for chat_id in SUBSCRIBERS:
            try:
                await context.bot.send_message(chat_id=chat_id, text=f"⚠️ WiseReport 수집 실패: {e}")
            except:
                pass
        return

    # 새 항목만 필터링
    new_company = []
    for r in company:
        key = (r['name'], r['title'])
        if key not in _wisereport_sent:
            _wisereport_sent.add(key)
            new_company.append(r)

    new_industry = []
    for r in industry:
        key = (r['name'], r['title'])
        if key not in _wisereport_sent:
            _wisereport_sent.add(key)
            new_industry.append(r)

    if not new_company and not new_industry:
        logging.info("WiseReport: no new reports")
        return

    messages = format_wisereport_msg(new_company, new_industry, is_update)
    for msg in messages:
        for chat_id in SUBSCRIBERS:
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
            except Exception as e:
                logging.error(f"WiseReport send failed: {e}")

    logging.info(f"WiseReport sent: {len(new_company)} company, {len(new_industry)} industry")


# ============================================================
# 예산 소진율 체크
# ============================================================
SISYPHE_SHEET_ID = '1V41yiwO4VrVUhjhqHyu8JGsuGcqw6pZen0NHdxzXHGs'
SISYPHE_API_KEY = 'AIzaSyCHPiRby5FVAIKDwneZHy1KGl3SfycjZEw'
def check_budget():
    """Google Sheets에서 예산/거래 데이터 읽고 소진율 계산"""
    import urllib.request
    base = f'https://sheets.googleapis.com/v4/spreadsheets/{SISYPHE_SHEET_ID}/values'

    # 예산 시트 읽기
    with urllib.request.urlopen(f'{base}/%EC%98%88%EC%82%B0?key={SISYPHE_API_KEY}', timeout=15) as r:
        budget_data = json.loads(r.read().decode())
    budget_rows = (budget_data.get('values') or [])[1:]  # skip header

    # 그룹별 예산 합산
    budget_total = 0
    budget_categories = []
    for row in budget_rows:
        cat = row[2] if len(row) > 2 else ''
        amt = int((row[3] if len(row) > 3 else '0').replace(',', '') or '0')
        if cat:
            budget_categories.append(cat)
            budget_total += amt

    if budget_total <= 0:
        return None, None

    # 거래내역 시트 읽기
    with urllib.request.urlopen(f'{base}/%EA%B1%B0%EB%9E%98%EB%82%B4%EC%97%AD?key={SISYPHE_API_KEY}', timeout=15) as r:
        tx_data = json.loads(r.read().decode())
    tx_rows = (tx_data.get('values') or [])[1:]

    # 이번 달 지출 합산
    now = datetime.datetime.now(KST)
    month_prefix = now.strftime('%Y-%m')
    total_spent = 0
    for row in tx_rows:
        date = row[0] if len(row) > 0 else ''
        tx_type = row[1] if len(row) > 1 else ''
        cat = row[2] if len(row) > 2 else ''
        amt = int((row[3] if len(row) > 3 else '0').replace(',', '') or '0')
        if date.startswith(month_prefix) and tx_type == '지출' and cat in budget_categories:
            total_spent += amt

    pct = round(total_spent / budget_total * 100)
    return pct, budget_total




if __name__ == '__main__':
    if not TOKEN:
        print("Error: TOKEN environment variable is missing.")
        import sys
        sys.exit(1)

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('weather', weather_command))
    application.add_handler(CommandHandler('calendar', calendar_command))
    application.add_handler(CommandHandler('portfolio', portfolio_command))
    application.add_handler(CommandHandler('update', update_command))
    application.add_handler(CommandHandler('stop', stop))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('ledger', ledger_command))
    application.add_handler(CommandHandler('ledger2', ledger2_command))
    application.add_handler(CommandHandler('journal', journal_command))
    
    job_queue = application.job_queue
    try:
        import pytz
        kst = pytz.timezone('Asia/Seoul')
        weather_time = datetime.time(hour=5, minute=0, second=0, tzinfo=kst)
        calendar_time = datetime.time(hour=5, minute=5, second=0, tzinfo=kst)
        headlines_time = datetime.time(hour=5, minute=10, second=0, tzinfo=kst)
        portfolio_time = datetime.time(hour=16, minute=0, second=0, tzinfo=kst)
        featured_time = datetime.time(hour=18, minute=0, second=0, tzinfo=kst)
        nightly_time = datetime.time(hour=23, minute=0, second=0, tzinfo=kst)
    except:
        weather_time = datetime.time(hour=5, minute=0, second=0)
        calendar_time = datetime.time(hour=5, minute=5, second=0)
        headlines_time = datetime.time(hour=5, minute=10, second=0)
        portfolio_time = datetime.time(hour=16, minute=0, second=0)
        featured_time = datetime.time(hour=18, minute=0, second=0)
        nightly_time = datetime.time(hour=23, minute=0, second=0)

    job_queue.run_daily(daily_weather_job, time=weather_time)
    job_queue.run_daily(daily_calendar_job, time=calendar_time)
    job_queue.run_daily(daily_headlines_job, time=headlines_time)
    job_queue.run_daily(daily_portfolio_job, time=portfolio_time)
    job_queue.run_daily(daily_featured_job, time=featured_time)
    job_queue.run_daily(nightly_portfolio_refresh_job, time=nightly_time)

    # 거래시간 30분마다 자동 포트폴리오 업데이트
    # 09:30, 10:00, 10:30, ..., 15:00, 15:35 KST
    try:
        kst = pytz.timezone('Asia/Seoul')
        trading_times = [
            datetime.time(hour=h, minute=m, second=0, tzinfo=kst)
            for h, m in [
                (9,30),(10,0),(10,30),(11,0),(11,30),
                (12,0),(12,30),(13,0),(13,30),(14,0),
                (14,30),(15,0),(15,35)
            ]
        ]
    except:
        trading_times = [
            datetime.time(hour=h, minute=m, second=0)
            for h, m in [
                (9,30),(10,0),(10,30),(11,0),(11,30),
                (12,0),(12,30),(13,0),(13,30),(14,0),
                (14,30),(15,0),(15,35)
            ]
        ]

    for t in trading_times:
        job_queue.run_daily(auto_portfolio_update_job, time=t)

    # WiseReport 리서치 리포트 알림 (08:00, 08:30, 09:00, 10:00, 11:00, 12:00 KST)
    try:
        kst = pytz.timezone('Asia/Seoul')
        wisereport_times = [
            datetime.time(hour=h, minute=m, second=0, tzinfo=kst)
            for h, m in [(8,0),(8,30),(9,0),(10,0),(11,0),(12,0)]
        ]
    except:
        wisereport_times = [
            datetime.time(hour=h, minute=m, second=0)
            for h, m in [(8,0),(8,30),(9,0),(10,0),(11,0),(12,0)]
        ]
    for t in wisereport_times:
        job_queue.run_daily(wisereport_job, time=t)

    print(f"Bot started at {datetime.datetime.now()}")
    print(f"✅ Daily jobs scheduled:")
    print(f"  - Weather: 05:00 KST")
    print(f"  - Calendar: 05:05 KST")
    print(f"  - Headlines: 05:10 KST")
    print(f"  - Portfolio report: 16:00 KST")
    print(f"  - Featured data: 18:00 KST (실패 시 19:00 재시도)")
    print(f"  - Auto portfolio update: 09:30~15:35 KST (30분 간격, 거래일만)")
    print(f"  - Nightly portfolio refresh: 23:00 KST (당일 주문 반영)")
    print(f"  - WiseReport: 08:00~12:00 KST (리서치 리포트)")
    application.run_polling()
