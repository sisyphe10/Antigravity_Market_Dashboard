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

KST = datetime.timezone(datetime.timedelta(hours=9))

# 당일 포트폴리오 리포트 전송 추적 (중복 방지)
_portfolio_report_sent_date = None


def git_sync(cwd):
    """VM git 동기화: fetch + reset --hard (충돌 불가)"""
    subprocess.run(["git", "fetch", "origin", "main"], cwd=cwd, capture_output=True, timeout=60)
    subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=cwd, capture_output=True, timeout=30)


def git_push_safe(cwd):
    """커밋 후 push: 실패 시 fetch+merge+push 재시도"""
    result = subprocess.run(["git", "push"], cwd=cwd, capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        return True
    # push 실패 → fetch + merge 시도 (rebase는 바이너리 충돌 시 불가)
    subprocess.run(["git", "fetch", "origin", "main"], cwd=cwd, capture_output=True, timeout=60)
    merge = subprocess.run(
        ["git", "merge", "origin/main", "--strategy-option=ours", "--no-edit"],
        cwd=cwd, capture_output=True, text=True, timeout=60
    )
    if merge.returncode != 0:
        subprocess.run(["git", "merge", "--abort"], cwd=cwd, capture_output=True, timeout=10)
        logging.warning("git push failed: merge conflict, aborted")
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

        # 3. Dashboard 재생성 및 push
        logging.info("Step 3: Regenerating dashboard...")
        result_dashboard = subprocess.run(
            [sys.executable, "execution/create_dashboard.py"],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result_dashboard.returncode == 0:
            subprocess.run(["git", "add", "index.html", "market.html", "wrap.html", "charts/"], cwd=parent_dir, capture_output=True, timeout=30)
            commit_dash = subprocess.run(
                ["git", "commit", "-m", f"포트폴리오 업데이트 ({now_str})"],
                cwd=parent_dir, capture_output=True, text=True, timeout=30
            )
            if commit_dash.returncode == 0:
                git_push_safe(parent_dir)
                logging.info("Dashboard updated and pushed")
        else:
            logging.error(f"Dashboard generation failed: {result_dashboard.stderr}")

        # 4. 포트폴리오 리포트 생성 및 전송 (당일 미전송 시에만)
        global _portfolio_report_sent_date
        today_kst = datetime.datetime.now(tz=KST).strftime('%Y-%m-%d')
        if _portfolio_report_sent_date == today_kst:
            logging.info("Step 4: 리포트 이미 전송됨, 스킵")
        else:
            logging.info("Step 4: Generating portfolio report...")
            result_report = subprocess.run(
                [sys.executable, "execution/daily_portfolio_report.py"],
                capture_output=True,
                text=True,
                timeout=120
            )
            if result_report.returncode == 0:
                _portfolio_report_sent_date = today_kst
                logging.info("Portfolio report sent successfully via Telegram")
            else:
                logging.error(f"Report generation failed: {result_report.stderr}")
                for chat_id in SUBSCRIBERS:
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text="⚠️ 포트폴리오 리포트 생성에 실패했습니다."
                        )
                    except Exception as e:
                        logging.error(f"Failed to send error notification to {chat_id}: {e}")

        os.chdir(original_dir)  # 원래 디렉토리로 복귀

    except subprocess.TimeoutExpired:
        logging.error("Portfolio update process timed out")
        os.chdir(original_dir)
    except Exception as e:
        logging.error(f"Daily portfolio job failed: {e}")
        os.chdir(original_dir)

async def daily_market_alert_job(context: ContextTypes.DEFAULT_TYPE):
    """매일 16:05 투자유의종목 대시보드 독립 갱신"""
    logging.info("Daily market alert job started")
    try:
        parent_dir = DASHBOARD_DIR
        original_dir = os.getcwd()
        os.chdir(parent_dir)
        git_sync(parent_dir)

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        result = subprocess.run(
            [sys.executable, "execution/create_market_alert.py"],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            subprocess.run(["git", "add", "market_alert.html"], cwd=parent_dir, capture_output=True, timeout=30)
            commit = subprocess.run(
                ["git", "commit", "-m", f"투자유의종목 업데이트 ({now_str})"],
                cwd=parent_dir, capture_output=True, text=True, timeout=30
            )
            if commit.returncode == 0:
                git_push_safe(parent_dir)
                logging.info("Market alert page updated and pushed")
            else:
                logging.info("No changes to market_alert.html")
        else:
            logging.error(f"Market alert generation failed: {result.stderr[-500:]}")
            for chat_id in SUBSCRIBERS:
                try:
                    await context.bot.send_message(chat_id=chat_id, text="⚠️ 투자유의종목 대시보드 생성 실패")
                except:
                    pass

        os.chdir(original_dir)
    except subprocess.TimeoutExpired:
        logging.error("Market alert job timed out, scheduling retry in 20 min")
        os.chdir(original_dir)
        context.job_queue.run_once(daily_market_alert_retry_job, when=1200)
    except Exception as e:
        logging.error(f"Market alert job failed: {e}, scheduling retry in 20 min")
        try:
            os.chdir(original_dir)
        except:
            pass
        context.job_queue.run_once(daily_market_alert_retry_job, when=1200)


async def daily_market_alert_retry_job(context: ContextTypes.DEFAULT_TYPE):
    """투자유의종목 대시보드 재시도"""
    logging.info("Market alert retry job started")
    try:
        parent_dir = DASHBOARD_DIR
        original_dir = os.getcwd()
        os.chdir(parent_dir)
        git_sync(parent_dir)

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        result = subprocess.run(
            [sys.executable, "execution/create_market_alert.py"],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            subprocess.run(["git", "add", "market_alert.html"], cwd=parent_dir, capture_output=True, timeout=30)
            commit = subprocess.run(
                ["git", "commit", "-m", f"투자유의종목 업데이트 ({now_str})"],
                cwd=parent_dir, capture_output=True, text=True, timeout=30
            )
            if commit.returncode == 0:
                git_push_safe(parent_dir)
                logging.info("Market alert retry succeeded")
        else:
            logging.error(f"Market alert retry also failed: {result.stderr[-300:]}")
            for chat_id in SUBSCRIBERS:
                try:
                    await context.bot.send_message(chat_id=chat_id, text="❌ 투자유의종목 대시보드 재시도도 실패")
                except:
                    pass

        os.chdir(original_dir)
    except Exception as e:
        logging.error(f"Market alert retry failed: {e}")
        try:
            os.chdir(original_dir)
        except:
            pass


async def daily_journal_job(context: ContextTypes.DEFAULT_TYPE):
    """매일 16:10 투자일지 시장 데이터 수집"""
    logging.info("Daily journal data job started")
    try:
        result = subprocess.run(
            [sys.executable, "execution/fetch_journal_data.py"],
            capture_output=True, text=True, timeout=120,
            cwd=DASHBOARD_DIR
        )
        if result.returncode == 0:
            logging.info("Journal data collected successfully")
        else:
            logging.warning(f"Journal data failed: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        logging.error("Journal data job timed out")
    except Exception as e:
        logging.error(f"Journal data job failed: {e}")



async def featured_update_job(context):
    """16:10 / 18:30 KST - Featured 데이터 수집 (KRX 16:00 1차, 18:10 2차 배포)"""
    now_kst = datetime.datetime.now(tz=KST)
    tag = f"Featured [{now_kst.strftime('%H:%M')}]"
    logging.info(f"{tag} 수집 시작")
    errors = []

    try:
        dashboard_dir = DASHBOARD_DIR
        # git_sync 전 로컬 데이터 백업 (reset --hard로 소실 방지)
        import shutil
        for fname in ['featured_data.json', 'stock_price_history.json', 'featured_news.json']:
            src = os.path.join(dashboard_dir, fname)
            bak = src + '.bak'
            if os.path.exists(src):
                shutil.copy2(src, bak)
        git_sync(dashboard_dir)
        # git_sync 후 백업 복원
        for fname in ['featured_data.json', 'stock_price_history.json', 'featured_news.json']:
            src = os.path.join(dashboard_dir, fname)
            bak = src + '.bak'
            if os.path.exists(bak):
                shutil.copy2(bak, src)
                os.remove(bak)

        # Step 0: WICS 섹터 매핑 업데이트 (매월 1일 1차 수집 시에만)
        if now_kst.hour < 17 and now_kst.day == 1:
            wics_result = subprocess.run(
                [sys.executable, "execution/fetch_wics_mapping.py"],
                capture_output=True, text=True, timeout=120, cwd=dashboard_dir
            )
            if wics_result.returncode == 0:
                logging.info(f"{tag} WICS 매핑 주간 업데이트 완료")
            else:
                logging.warning(f"{tag} WICS 매핑 실패 (무시): {wics_result.stderr[-100:]}")

        # Step 1: stock_price_history.json 업데이트 (신고가 계산용)
        price_result = subprocess.run(
            [sys.executable, "execution/update_price_history.py"],
            capture_output=True, text=True, timeout=300, cwd=dashboard_dir
        )
        if price_result.returncode != 0:
            errors.append(f"price_history 실패: {price_result.stderr[-200:]}")
            logging.error(f"{tag} {errors[-1]}")
        else:
            price_out = price_result.stdout.strip()
            if '새로 수집할 날짜 없음' in price_out:
                errors.append("price_history: 새로 수집할 날짜 없음 (데이터 미제공 또는 이미 수집)")
                logging.warning(f"{tag} {errors[-1]}")
            elif '없음' in price_out and '전체 수집' in price_out:
                errors.append("price_history: stock_price_history.json 파일 없음")
                logging.error(f"{tag} {errors[-1]}")
            else:
                logging.info(f"{tag} price_history OK: {price_out[-150:]}")

        # Step 2: Featured 데이터 수집
        result = subprocess.run(
            [sys.executable, "execution/fetch_featured_data.py"],
            capture_output=True, text=True, timeout=300, cwd=dashboard_dir
        )
        if result.returncode != 0:
            errors.append(f"fetch_featured 비정상 종료: {result.stderr[-200:]}")
            logging.error(f"{tag} {errors[-1]}")
        elif '완료' not in result.stdout:
            # stdout 분석: 왜 완료 메시지가 없는지
            out = result.stdout.strip()
            if '모든 날짜가 이미 수집됨' in out:
                logging.info(f"{tag} Featured: 이미 최신 (추가 수집 불필요)")
            elif not out:
                errors.append("fetch_featured: stdout 비어있음 (silent failure)")
                logging.error(f"{tag} {errors[-1]}")
            else:
                # 수집 시도했지만 모두 실패한 경우
                fail_count = out.count('실패')
                errors.append(f"fetch_featured: 완료 메시지 없음 (실패 {fail_count}건)\nstdout: {out[-300:]}")
                logging.error(f"{tag} {errors[-1]}")
        else:
            logging.info(f"{tag} Featured 수집 완료: {result.stdout.strip()[-150:]}")

        # Step 3: 신고가 종목 뉴스 수집
        try:
            news_result = subprocess.run(
                [sys.executable, "execution/fetch_featured_news.py"],
                capture_output=True, text=True, timeout=120, cwd=dashboard_dir
            )
            if news_result.returncode == 0:
                logging.info(f"{tag} 뉴스 수집 완료: {news_result.stdout.strip()[-100:]}")
            else:
                logging.warning(f"{tag} 뉴스 수집 실패 (무시): {news_result.stderr[-100:]}")
        except Exception as ne:
            logging.warning(f"{tag} 뉴스 수집 예외 (무시): {ne}")

        # 에러가 있더라도 대시보드 재생성 시도 (기존 데이터로라도 갱신)
        subprocess.run([sys.executable, "execution/create_dashboard.py"],
                       capture_output=True, text=True, timeout=120, cwd=dashboard_dir)
        now_str = now_kst.strftime("%Y-%m-%d %H:%M")
        subprocess.run(["git", "add", "featured.html", "featured_data.json", "featured_news.json",
                        "etf.html", "index.html", "market.html", "wrap.html"],
                       cwd=dashboard_dir, capture_output=True, timeout=30)
        commit_result = subprocess.run(
            ["git", "commit", "-m", f"Featured 업데이트 ({now_str})"],
            cwd=dashboard_dir, capture_output=True, text=True, timeout=30
        )
        if commit_result.returncode == 0:
            git_push_safe(dashboard_dir)
            logging.info(f"{tag} push 완료")
        else:
            logging.info(f"{tag} 변경 없음 (commit skip)")

    except Exception as e:
        errors.append(f"예외 발생: {e}")
        logging.error(f"{tag} {errors[-1]}")

    # 실패 시 텔레그램 알림
    if errors:
        error_msg = f"❌ {tag} 수집 실패\n\n" + "\n\n".join(f"• {e}" for e in errors)
        for chat_id in SUBSCRIBERS:
            try:
                await context.bot.send_message(chat_id=chat_id, text=error_msg[:4000])
            except:
                pass


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
        cwd=dashboard_dir, capture_output=True, text=True, timeout=300
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


async def late_market_alert_job(context: ContextTypes.DEFAULT_TYPE):
    """23:00 투자유의종목 재생�� (장 마감 후 공시 반영)"""
    logging.info("Late market alert job started (23:00 KST)")
    try:
        dashboard_dir = DASHBOARD_DIR
        git_sync(dashboard_dir)
        result = subprocess.run(
            [sys.executable, "execution/create_market_alert.py"],
            cwd=dashboard_dir, capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            logging.error(f"Late market alert failed: {result.stderr[-300:]}")
            return
        subprocess.run(
            [sys.executable, "execution/create_dashboard.py"],
            cwd=dashboard_dir, capture_output=True, text=True, timeout=120
        )
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        subprocess.run(["git", "add", "market_alert.html", "index.html", "market.html"],
                       cwd=dashboard_dir, capture_output=True, timeout=30)
        commit_result = subprocess.run(
            ["git", "commit", "-m", f"���자유의종목 야간 업데이트 ({now_str})"],
            cwd=dashboard_dir, capture_output=True, text=True, timeout=30
        )
        if commit_result.returncode == 0:
            git_push_safe(dashboard_dir)
            logging.info("Late market alert pushed")
        else:
            logging.info("Late market alert: no changes")
    except Exception as e:
        logging.error(f"Late market alert error: {e}")


async def daily_etf_collection_job(context: ContextTypes.DEFAULT_TYPE):
    """매일 18:30 ETF 구성종목 수집 (독립 스크립트 호출)"""
    logging.info("Daily ETF collection job started")
    try:
        result = subprocess.run(
            [sys.executable, "execution/etf_collector/collect_etf_daily.py"],
            capture_output=True, text=True, timeout=1200,
            cwd=DASHBOARD_DIR
        )
        if result.returncode == 0:
            # 마지막 로그 줄 추출
            last_line = result.stdout.strip().split('\n')[-1] if result.stdout.strip() else ''
            logging.info(f"ETF collection completed: {last_line}")
        else:
            logging.error(f"ETF collection failed: {result.stderr[-500:]}")
            for chat_id in SUBSCRIBERS:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=f"⚠️ ETF 구성종목 수집 실패")
                except:
                    pass
            # 20:00 재시도
            context.job_queue.run_once(daily_etf_retry_job, when=5400)
    except subprocess.TimeoutExpired:
        logging.error("ETF collection timed out (20 min)")
    except Exception as e:
        logging.error(f"ETF collection error: {e}")


async def daily_etf_retry_job(context: ContextTypes.DEFAULT_TYPE):
    """ETF 수집 재시도 (20:00)"""
    logging.info("ETF collection retry started")
    try:
        result = subprocess.run(
            [sys.executable, "execution/etf_collector/collect_etf_daily.py"],
            capture_output=True, text=True, timeout=1200,
            cwd=DASHBOARD_DIR
        )
        if result.returncode == 0:
            logging.info("ETF collection retry completed")
        else:
            logging.error(f"ETF collection retry also failed: {result.stderr[-300:]}")
            for chat_id in SUBSCRIBERS:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=f"❌ ETF 구성종목 수집 재시도도 실패")
                except:
                    pass
    except Exception as e:
        logging.error(f"ETF collection retry error: {e}")


async def nightly_portfolio_refresh_job(context: ContextTypes.DEFAULT_TYPE):
    """매일 23:00 당일 주문 포트폴리오/섹터 반영"""
    logging.info("Nightly portfolio refresh job started (23:00 KST)")
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _nightly_refresh_sync)
        logging.info("Nightly portfolio refresh completed")
    except Exception as e:
        logging.error(f"Nightly portfolio refresh failed: {e}")


async def evening_backup_job(context: ContextTypes.DEFAULT_TYPE):
    """20:00 백업 - 16:xx 스케줄에서 데이터 못 가져온 경우 재시도"""
    logging.info("Evening backup job started (20:00 KST)")
    try:
        loop = asyncio.get_running_loop()

        # 1. Portfolio report (16:00에 실패했을 수 있음)
        logging.info("Backup: portfolio job...")
        await daily_portfolio_job(context)

        # 2. Nightly refresh (16:20에 실패했을 수 있음)
        logging.info("Backup: nightly refresh...")
        await loop.run_in_executor(None, _nightly_refresh_sync)

        # 4. ETF collection (16:30에 실패했을 수 있음)
        logging.info("Backup: ETF collection...")
        await daily_etf_collection_job(context)

        logging.info("Evening backup job completed")
    except Exception as e:
        logging.error(f"Evening backup job error: {e}")


_ALERT_SENT_FILE = os.path.join(DASHBOARD_DIR, '.market_alert_sent.json')


def _load_prev_alert():
    try:
        with open(_ALERT_SENT_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_alert(data):
    with open(_ALERT_SENT_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False)


async def daily_market_alert_summary_job(context: ContextTypes.DEFAULT_TYPE):
    """매일 05:15 투자유의종목 텔레그램 요약 알림"""
    logging.info("Market alert summary job started")
    try:
        import html as html_mod
        sys.path.insert(0, os.path.join(DASHBOARD_DIR, 'execution'))
        from create_market_alert import (
            get_session, fetch_category, parse_stocks, load_krx_data,
            fmt_marcap
        )
        esc = html_mod.escape

        now_kst = datetime.datetime.now(tz=KST)
        today = now_kst.strftime('%Y-%m-%d')
        start_90 = (now_kst - datetime.timedelta(days=90)).strftime('%Y-%m-%d')
        start_10 = (now_kst - datetime.timedelta(days=10)).strftime('%Y-%m-%d')

        krx_data = load_krx_data()
        session = get_session()

        stocks_주의 = parse_stocks(fetch_category(session, '투자주의', start_10, today), '투자주의', krx_data)
        seen = {}
        for s in stocks_주의:
            if s['name'] not in seen or s['designation_date'] > seen[s['name']]['designation_date']:
                seen[s['name']] = s
        stocks_주의 = list(seen.values())

        stocks_경고 = parse_stocks(fetch_category(session, '투자경고', start_90, today), '투자경고', krx_data)
        stocks_위험 = parse_stocks(fetch_category(session, '투자위험', start_90, today), '투자위험', krx_data)

        # 시총 1000억 이상만
        MIN_MARCAP = 1000
        stocks_주의 = [s for s in stocks_주의 if s.get('marcap') and s['marcap'] >= MIN_MARCAP]
        stocks_경고 = [s for s in stocks_경고 if s.get('marcap') and s['marcap'] >= MIN_MARCAP]
        stocks_위험 = [s for s in stocks_위험 if s.get('marcap') and s['marcap'] >= MIN_MARCAP]

        # 이전 리스트와 비교
        prev = _load_prev_alert()
        prev_위험 = set(prev.get('위험', []))
        prev_경고 = set(prev.get('경고', []))
        prev_주의 = set(prev.get('주의', []))

        def fmt_line(s, is_new):
            name = esc(s['name'])
            mcap = esc(fmt_marcap(s['marcap']))
            if is_new:
                return f"• <b>[NEW]</b> {name} / {mcap}"
            return f"• {name} / {mcap}"

        lines = [f"<b><u>투자유의종목 현황</u></b> ({today})"]

        if stocks_위험:
            lines.append("")
            lines.append("<b><u>[투자위험]</u></b>")
            for s in sorted(stocks_위험, key=lambda x: (x.get('marcap') or 0), reverse=True):
                lines.append(fmt_line(s, s['name'] not in prev_위험))

        if stocks_경고:
            lines.append("")
            lines.append("<b><u>[투자경고]</u></b>")
            for s in sorted(stocks_경고, key=lambda x: (x.get('marcap') or 0), reverse=True):
                lines.append(fmt_line(s, s['name'] not in prev_경고))

        if stocks_주의:
            lines.append("")
            lines.append("<b><u>[투자주의]</u></b>")
            for s in sorted(stocks_주의, key=lambda x: (x.get('marcap') or 0), reverse=True):
                is_new = s['name'] not in prev_주의
                is_예고 = s.get('warn_type') == '투자경고 지정예고'
                name = esc(s['name'])
                mcap = esc(fmt_marcap(s['marcap']))
                if is_new:
                    line = f"• <b>[NEW]</b> {name} / {mcap}"
                else:
                    line = f"• {name} / {mcap}"
                if is_예고:
                    line = f"<u>{line}</u>"
                lines.append(line)

        _save_alert({
            '위험': [s['name'] for s in stocks_위험],
            '경고': [s['name'] for s in stocks_경고],
            '주의': [s['name'] for s in stocks_주의],
        })

        msg = "\n".join(lines)
        for chat_id in SUBSCRIBERS:
            try:
                for i in range(0, len(msg), 4000):
                    await context.bot.send_message(chat_id=chat_id, text=msg[i:i+4000], parse_mode='HTML')
            except Exception as e:
                logging.error(f"Market alert summary send failed: {e}")

        logging.info(f"Market alert summary sent: 위험{len(stocks_위험)} 경고{len(stocks_경고)} 주의{len(stocks_주의)}")
    except Exception as e:
        logging.error(f"Market alert summary job failed: {e}")


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
            today_kst = datetime.datetime.now(tz=KST).date()
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

        budget_msg = ""
        try:
            pct, budget_total, total_spent = check_budget()
            if pct is not None:
                bar_len = 10
                filled = min(bar_len, round(pct / 100 * bar_len))
                bar = '█' * filled + '░' * (bar_len - filled)
                remaining = max(0, budget_total - total_spent)
                budget_msg = f"📊 예산 소진율 {pct}% [{bar}]\n💵 잔액 {remaining:,}원\n\n"
        except:
            pass

        await update.message.reply_text(
            f"<b><u>시지프 가계부</u></b>\n\n"
            f"{budget_msg}"
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
        today_str = datetime.datetime.now(tz=KST).strftime('%Y-%m-%d')

        _append_row(service, '거래내역', [today_str, tx_type, category, str(amount), memo])

        type_emoji = '🔴' if tx_type == '지출' else '🟠'
        msg = (
            f"<b><u>시지프 가계부</u></b>\n"
            f"{type_emoji} <b>{tx_type}</b> 입력 완료\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📅 {today_str}\n"
            f"📂 {category}\n"
            f"💰 {amount:,}원\n"
        )
        if memo:
            msg += f"📝 {memo}\n"

        # 지출 시 예산 소진율 + 잔액 표시
        if tx_type == '지출':
            try:
                pct, budget_total, total_spent = check_budget()
                if pct is not None:
                    bar_len = 10
                    filled = min(bar_len, round(pct / 100 * bar_len))
                    bar = '█' * filled + '░' * (bar_len - filled)
                    remaining = max(0, budget_total - total_spent)
                    msg += f"\n📊 예산 소진율 {pct}% [{bar}]"
                    msg += f"\n💵 잔액 {remaining:,}원"
            except:
                pass

        await update.message.reply_text(msg, parse_mode='HTML')
        logging.info(f"Sisyphe ledger: {tx_type} {amount} {category} {memo}")


    except Exception as e:
        logging.error(f"Sisyphe ledger error: {e}")
        await update.message.reply_text(f"❌ 저장 실패: {str(e)}")


# ============================================================
# Fitness 기록 - Telegram → Sisyphe data.json (GitHub Contents API)
# ============================================================
SISYPHE_REPO = 'sisyphe10/Sisyphe'
SISYPHE_DATA_PATH = 'data.json'


def _gh_get_data_json():
    import base64, requests
    pat = os.environ.get('GH_PAT')
    if not pat:
        raise RuntimeError('GH_PAT 환경변수가 설정되지 않았습니다')
    r = requests.get(
        f'https://api.github.com/repos/{SISYPHE_REPO}/contents/{SISYPHE_DATA_PATH}',
        headers={'Authorization': f'token {pat}', 'Accept': 'application/vnd.github.v3+json'},
        timeout=10,
    )
    r.raise_for_status()
    meta = r.json()
    content = base64.b64decode(meta['content']).decode('utf-8')
    return json.loads(content), meta['sha']


def _gh_put_data_json(data, sha, message):
    import base64, requests
    pat = os.environ.get('GH_PAT')
    content_str = json.dumps(data, ensure_ascii=False, indent=2)
    r = requests.put(
        f'https://api.github.com/repos/{SISYPHE_REPO}/contents/{SISYPHE_DATA_PATH}',
        headers={'Authorization': f'token {pat}', 'Accept': 'application/vnd.github.v3+json'},
        json={
            'message': message,
            'content': base64.b64encode(content_str.encode('utf-8')).decode('ascii'),
            'sha': sha,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _parse_duration(s):
    """'31:26' → 31.4333..., '31' → 31.0"""
    if ':' in s:
        mm, ss = s.split(':')
        return int(mm) + int(ss) / 60.0
    return float(s)


def _fmt_duration(min_dec):
    total = round(min_dec * 60)
    return f"{total // 60}:{total % 60:02d}"


def _parse_fitness_tags(tokens):
    """h158, c167, f4 등의 태그 추출. 반환: (hr, cadence, fatigue, memo)"""
    hr, cadence, fatigue = None, None, None
    memo_tokens = []
    for t in tokens:
        if len(t) >= 2 and t[0].lower() in ('h',) and t[1:].isdigit():
            hr = int(t[1:])
        elif len(t) >= 2 and t[0].lower() in ('c',) and t[1:].isdigit():
            cadence = int(t[1:])
        elif len(t) >= 2 and t[0].lower() in ('f',) and t[1:].isdigit():
            fatigue = int(t[1:])
        else:
            memo_tokens.append(t)
    return hr, cadence, fatigue, ' '.join(memo_tokens)


async def fitness_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/fitness 런닝 5.01 31:26 h158 c167 f4 메모"""
    args = context.args
    today_str = datetime.datetime.now(tz=KST).strftime('%Y-%m-%d')

    # 인자 없이 /fitness → 이번 주 요약 + 사용법
    if not args:
        try:
            data, _ = _gh_get_data_json()
            entries = data.get('fitness', [])
            now = datetime.datetime.now(tz=KST)
            weekday = now.weekday()
            mon = (now - datetime.timedelta(days=weekday)).strftime('%Y-%m-%d')
            sun = (now - datetime.timedelta(days=weekday) + datetime.timedelta(days=6)).strftime('%Y-%m-%d')

            week_runs, week_weight, week_tennis = 0, 0, 0
            week_km, week_min = 0.0, 0.0
            for e in entries:
                d = e.get('date', '')
                if d < mon or d > sun:
                    continue
                t = e.get('type', '')
                if t == '런닝':
                    week_runs += 1
                    week_km += float(e.get('distance') or 0)
                    week_min += float(e.get('duration') or 0)
                elif t == '웨이트':
                    week_weight += 1
                elif t == '테니스':
                    week_tennis += 1

            pace_str = ''
            if week_km > 0 and week_min > 0:
                p = week_min / week_km
                pace_str = f"  평균 {int(p)}:{int((p % 1) * 60):02d}/km"

            msg = (
                f"<b><u>Sisyphe Fitness</u></b>\n\n"
                f"📅 이번 주 ({mon} ~ {sun})\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🏃 런닝 {week_runs}회  {week_km:.1f}km  {_fmt_duration(week_min)}{pace_str}\n"
                f"🏋️ 웨이트 {week_weight}회\n"
                f"🎾 테니스 {week_tennis}회\n\n"
                "📝 <b>사용법</b>\n\n"
                "<code>/fitness 런닝 5.01 31:26 h158 c167 f4 이지런</code>\n"
                "  → km · 시간(mm:ss 또는 분) · 심박 · 케이던스 · 피로도 · 메모\n"
                "<code>/fitness 웨이트 60 f2 가슴 벤치80</code>\n"
                "<code>/fitness 테니스 180 f5</code>\n\n"
                "<i>태그: h=심박, c=케이던스, f=피로도(0-10). 순서·생략 무관</i>\n"
            )
        except Exception as e:
            logging.error(f"Sisyphe fitness summary error: {e}")
            msg = (
                f"<b><u>Sisyphe Fitness</u></b>\n\n"
                "📝 <b>사용법</b>\n\n"
                "<code>/fitness 런닝 5.01 31:26 h158 c167 f4 이지런</code>\n"
                "<code>/fitness 웨이트 60 f2 가슴 벤치80</code>\n"
                "<code>/fitness 테니스 180 f5</code>\n"
            )
        await update.message.reply_text(msg, parse_mode='HTML')
        return

    workout_type = args[0]

    try:
        entry = {'date': today_str}

        if workout_type in ['런닝', 'ㄹ', '런']:
            if len(args) < 3:
                await update.message.reply_text("❌ 형식: /fitness 런닝 [거리km] [시간 mm:ss|분] [h심박 c케이던스 f피로도] [메모]")
                return
            distance = float(args[1])
            duration = _parse_duration(args[2])
            hr, cadence, fatigue, memo = _parse_fitness_tags(args[3:])

            entry.update({'type': '런닝', 'distance': distance, 'duration': round(duration, 2)})
            if hr is not None: entry['hr'] = hr
            if cadence is not None: entry['cadence'] = cadence
            if fatigue is not None: entry['fatigue'] = fatigue
            if memo: entry['memo'] = memo

            pace = duration / distance if distance > 0 else 0
            msg_lines = [
                "<b><u>Sisyphe Fitness</u></b>",
                "🏃 <b>런닝</b> 기록 완료",
                "━━━━━━━━━━━━━━━",
                f"📅 {today_str}",
                f"📏 {distance}km · {_fmt_duration(duration)}",
                f"⏱️ 페이스 {int(pace)}:{int((pace % 1) * 60):02d}/km",
            ]
            if hr is not None: msg_lines.append(f"❤️ HR {hr}")
            if cadence is not None: msg_lines.append(f"👟 케이던스 {cadence}")
            if fatigue is not None: msg_lines.append(f"😤 피로도 {fatigue}")
            if memo: msg_lines.append(f"📝 {memo}")
            msg = '\n'.join(msg_lines)

        elif workout_type in ['웨이트', 'ㅇ', '웨']:
            if len(args) < 2:
                await update.message.reply_text("❌ 형식: /fitness 웨이트 [시간분] [f피로도] [메모]")
                return
            duration = _parse_duration(args[1])
            _, _, fatigue, memo = _parse_fitness_tags(args[2:])

            entry.update({'type': '웨이트', 'distance': 0, 'duration': round(duration, 2)})
            if fatigue is not None: entry['fatigue'] = fatigue
            if memo: entry['memo'] = memo

            msg_lines = [
                "<b><u>Sisyphe Fitness</u></b>",
                "🏋️ <b>웨이트</b> 기록 완료",
                "━━━━━━━━━━━━━━━",
                f"📅 {today_str}",
                f"⏱️ {_fmt_duration(duration)}",
            ]
            if fatigue is not None: msg_lines.append(f"😤 피로도 {fatigue}")
            if memo: msg_lines.append(f"📝 {memo}")
            msg = '\n'.join(msg_lines)

        elif workout_type in ['테니스', 'ㅌ', '테']:
            if len(args) < 2:
                await update.message.reply_text("❌ 형식: /fitness 테니스 [시간분] [f피로도] [메모]")
                return
            duration = _parse_duration(args[1])
            _, _, fatigue, memo = _parse_fitness_tags(args[2:])

            entry.update({'type': '테니스', 'distance': 0, 'duration': round(duration, 2)})
            if fatigue is not None: entry['fatigue'] = fatigue
            if memo: entry['memo'] = memo

            msg_lines = [
                "<b><u>Sisyphe Fitness</u></b>",
                "🎾 <b>테니스</b> 기록 완료",
                "━━━━━━━━━━━━━━━",
                f"📅 {today_str}",
                f"⏱️ {_fmt_duration(duration)}",
            ]
            if fatigue is not None: msg_lines.append(f"😤 피로도 {fatigue}")
            if memo: msg_lines.append(f"📝 {memo}")
            msg = '\n'.join(msg_lines)

        else:
            await update.message.reply_text(
                "❌ 유형: 런닝(ㄹ) / 웨이트(ㅇ) / 테니스(ㅌ)\n\n"
                "<code>/fitness 런닝 5.01 31:26 h158 c167 f4</code>",
                parse_mode='HTML'
            )
            return

        # GitHub API로 data.json에 append
        data, sha = _gh_get_data_json()
        if 'fitness' not in data:
            data['fitness'] = []
        data['fitness'].append(entry)
        data['fitness'].sort(key=lambda e: (e.get('date', ''), e.get('type', '')))
        _gh_put_data_json(data, sha, f"fitness: {entry['date']} {entry['type']}")

        await update.message.reply_text(msg, parse_mode='HTML')
        logging.info(f"Sisyphe fitness: {entry}")

    except ValueError as e:
        await update.message.reply_text(f"❌ 입력 형식 오류: {str(e)}")
    except Exception as e:
        logging.error(f"Sisyphe fitness error: {e}")
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

        budget_msg = ""
        try:
            import urllib.request as _ur
            _base = f'https://sheets.googleapis.com/v4/spreadsheets/{SEONYUDUO_SHEET_ID}/values'
            with _ur.urlopen(f'{_base}/%EA%B0%80%EA%B3%84%EB%B6%80?key={SISYPHE_API_KEY}', timeout=15) as _r:
                _tx = json.loads(_r.read().decode())
            _rows = (_tx.get('values') or [])[1:]
            month_prefix = datetime.datetime.now(tz=KST).strftime('%Y-%m')
            total_spent = sum(
                int(str(r[3]).replace(',', '') or '0')
                for r in _rows
                if len(r) > 3 and str(r[0]).startswith(month_prefix) and r[1] == '지출'
            )
            budget = 800000
            pct = round(total_spent / budget * 100)
            remaining = max(0, budget - total_spent)
            bar_len = 10
            filled = min(bar_len, round(pct / 100 * bar_len))
            bar = '█' * filled + '░' * (bar_len - filled)
            budget_msg = f"📊 예산 소진율 {pct}% [{bar}]\n💵 잔액 {remaining:,}원\n\n"
        except:
            pass

        msg = f"<b><u>선유듀오 가계부</u></b>\n\n"
        msg += budget_msg
        msg += "<b>카테고리</b>\n"
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
            f"<b><u>선유듀오 가계부</u></b>\n"
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

        # 지출 시 예산 소진율 + 잔액 표시 (월 80만원 기준)
        if tx_type == '지출':
            try:
                import urllib.request as _ur
                _base = f'https://sheets.googleapis.com/v4/spreadsheets/{SEONYUDUO_SHEET_ID}/values'
                with _ur.urlopen(f'{_base}/%EA%B0%80%EA%B3%84%EB%B6%80?key={SISYPHE_API_KEY}', timeout=15) as _r:
                    _tx = json.loads(_r.read().decode())
                _rows = (_tx.get('values') or [])[1:]
                month_prefix = datetime.datetime.now(tz=KST).strftime('%Y-%m')
                total_spent = sum(
                    int(str(r[3]).replace(',', '') or '0')
                    for r in _rows
                    if len(r) > 3 and str(r[0]).startswith(month_prefix) and r[1] == '지출'
                )
                budget = 800000
                pct = round(total_spent / budget * 100)
                remaining = max(0, budget - total_spent)
                bar_len = 10
                filled = min(bar_len, round(pct / 100 * bar_len))
                bar = '█' * filled + '░' * (bar_len - filled)
                msg += f"\n📊 예산 소진율 {pct}% [{bar}]"
                msg += f"\n💵 잔액 {remaining:,}원"
            except:
                pass

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
_WISEREPORT_SENT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.wisereport_sent.json')


def _load_wisereport_sent():
    """파일에서 당일 전송 기록 로드"""
    today_str = datetime.datetime.now(KST).strftime('%Y-%m-%d')
    try:
        with open(_WISEREPORT_SENT_FILE, 'r') as f:
            data = json.load(f)
        if data.get('date') == today_str:
            return set(tuple(x) for x in data.get('sent', [])), today_str
    except:
        pass
    return set(), today_str


def _save_wisereport_sent(sent_set, date_str):
    """전송 기록 파일에 저장"""
    try:
        with open(_WISEREPORT_SENT_FILE, 'w') as f:
            json.dump({'date': date_str, 'sent': list(sent_set)}, f)
    except:
        pass


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
        # 같은 종목끼리 그룹핑 (한글 오름차순)
        groups = {}
        for r in company_data:
            nm = r['name'].split('(')[0].strip()
            if nm not in groups:
                groups[nm] = []
            groups[nm].append(r)

        for nm in sorted(groups.keys()):
            items = groups[nm]
            for r in items:
                op = r['opinion'] or '-'
                tgt = r['target'] or '-'
                analyst = r['analyst'].replace('[', '').replace(']', '')
                # 증권사 앞2글자 + 애널리스트명
                parts = analyst.split()
                firm = parts[0][:2] if parts else '-'
                person = ' '.join(parts[1:]) if len(parts) > 1 else ''
                analyst_short = f"{firm} {person}" if person else firm
                close = r.get('close', '') or '-'
                # upside/downside 계산
                try:
                    c_val = int(close.replace(',', ''))
                    t_val = int(tgt.replace(',', ''))
                    pct = round((t_val - c_val) / c_val * 100)
                    pct_str = f" ({pct:+d}%)"
                except:
                    pct_str = ''
                lines.append(f"<b><u>{nm}</u></b>")
                lines.append(f"{analyst_short} | {op} | {close} → {tgt}{pct_str}")
                lines.append(f"「{r['title']}」")
                summ = r['summary'].replace('▶ ', '▶').replace('▶', '\n- ')
                if summ.startswith('\n'):
                    summ = summ[1:]
                lines.append(summ)
                lines.append('')

    if industry_data:
        lines.append('<b>━━ 산업 ━━</b>')
        groups = {}
        for r in industry_data:
            nm = r['name']
            if nm not in groups:
                groups[nm] = []
            groups[nm].append(r)

        for nm in sorted(groups.keys()):
            items = groups[nm]
            for r in items:
                prev = r.get('prev_opinion', '') or ''
                curr = r.get('opinion', '') or ''
                analyst = r['analyst'].replace('[', '').replace(']', '')
                if prev and curr and prev != curr:
                    opinion_str = f"{prev} → {curr}"
                else:
                    opinion_str = curr or prev or '-'
                parts = analyst.split()
                firm = parts[0][:2] if parts else '-'
                person = ' '.join(parts[1:]) if len(parts) > 1 else ''
                analyst_short = f"{firm} {person}" if person else firm
                lines.append(f"<b><u>{nm}</u></b>")
                lines.append(f"{analyst_short} | {opinion_str}")
                lines.append(f"「{r['title']}」")
                summ = r['summary'].replace('▶ ', '▶').replace('▶', '\n- ')
                if summ.startswith('\n'):
                    summ = summ[1:]
                lines.append(summ)
            lines.append('')

    # 종목/산업 블록 단위로 분할 (빈줄 기준)
    blocks = []
    block = ''
    for line in lines:
        if line == '' and block.strip():
            blocks.append(block + '\n')
            block = ''
        else:
            block += line + '\n'
    if block.strip():
        blocks.append(block)

    # 4096자 제한, 블록 단위로 메시지 분할
    messages = []
    current = ''
    for blk in blocks:
        if len(current) + len(blk) > 4000:
            if current.strip():
                messages.append(current)
            current = blk
        else:
            current += blk
    if current.strip():
        messages.append(current)
    return messages


async def wisereport_job(context):
    """WiseReport 리서치 리포트 스크래핑 + 텔레그램 전송"""
    now = datetime.datetime.now(KST)
    today_str = now.strftime('%Y-%m-%d')

    sent_set, sent_date = _load_wisereport_sent()
    if sent_date != today_str:
        sent_set = set()

    is_update = len(sent_set) > 0

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
        if key not in sent_set:
            sent_set.add(key)
            new_company.append(r)

    new_industry = []
    for r in industry:
        key = (r['name'], r['title'])
        if key not in sent_set:
            sent_set.add(key)
            new_industry.append(r)

    if not new_company and not new_industry:
        _save_wisereport_sent(sent_set, today_str)
        logging.info("WiseReport: no new reports")
        return

    messages = format_wisereport_msg(new_company, new_industry, is_update)
    for msg in messages:
        for chat_id in SUBSCRIBERS:
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
            except Exception as e:
                logging.error(f"WiseReport send failed: {e}")

    _save_wisereport_sent(sent_set, today_str)
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

    # 그룹별 예산 합산 (의료 제외)
    BUDGET_EXCLUDE = {'의료'}
    budget_total = 0
    budget_categories = []
    for row in budget_rows:
        cat = row[2] if len(row) > 2 else ''
        amt = int((row[3] if len(row) > 3 else '0').replace(',', '') or '0')
        if cat and cat not in BUDGET_EXCLUDE:
            budget_categories.append(cat)
            budget_total += amt

    if budget_total <= 0:
        return None, None, None

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
    return pct, budget_total, total_spent




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
    application.add_handler(CommandHandler('fitness', fitness_command))
    application.add_handler(CommandHandler('journal', journal_command))
    
    job_queue = application.job_queue
    try:
        import pytz
        kst = pytz.timezone('Asia/Seoul')
        weather_time = datetime.time(hour=5, minute=0, second=0, tzinfo=kst)
        calendar_time = datetime.time(hour=5, minute=5, second=0, tzinfo=kst)
        headlines_time = datetime.time(hour=5, minute=10, second=0, tzinfo=kst)
        alert_summary_time = datetime.time(hour=5, minute=15, second=0, tzinfo=kst)
        portfolio_time = datetime.time(hour=16, minute=0, second=0, tzinfo=kst)
        market_alert_time = datetime.time(hour=16, minute=5, second=0, tzinfo=kst)
        journal_time = datetime.time(hour=16, minute=10, second=0, tzinfo=kst)
        nightly_time = datetime.time(hour=16, minute=20, second=0, tzinfo=kst)
        etf_collection_time = datetime.time(hour=16, minute=30, second=0, tzinfo=kst)
    except:
        weather_time = datetime.time(hour=5, minute=0, second=0)
        calendar_time = datetime.time(hour=5, minute=5, second=0)
        headlines_time = datetime.time(hour=5, minute=10, second=0)
        alert_summary_time = datetime.time(hour=5, minute=15, second=0)
        portfolio_time = datetime.time(hour=16, minute=0, second=0)
        market_alert_time = datetime.time(hour=16, minute=5, second=0)
        journal_time = datetime.time(hour=16, minute=10, second=0)
        nightly_time = datetime.time(hour=16, minute=20, second=0)
        etf_collection_time = datetime.time(hour=16, minute=30, second=0)

    # Featured 수집: 16:10 1차 (정규장 종가), 18:30 2차 (시간외 포함 최종)
    try:
        featured_1st_time = datetime.time(hour=16, minute=20, second=0, tzinfo=pytz.timezone('Asia/Seoul'))
        featured_2nd_time = datetime.time(hour=18, minute=30, second=0, tzinfo=pytz.timezone('Asia/Seoul'))
    except:
        featured_1st_time = datetime.time(hour=16, minute=20, second=0)
        featured_2nd_time = datetime.time(hour=18, minute=30, second=0)
    job_queue.run_daily(featured_update_job, time=featured_1st_time)
    job_queue.run_daily(featured_update_job, time=featured_2nd_time)

    job_queue.run_daily(daily_weather_job, time=weather_time)
    job_queue.run_daily(daily_calendar_job, time=calendar_time)
    job_queue.run_daily(daily_headlines_job, time=headlines_time)
    job_queue.run_daily(daily_market_alert_summary_job, time=alert_summary_time)
    job_queue.run_daily(daily_portfolio_job, time=portfolio_time)
    job_queue.run_daily(daily_market_alert_job, time=market_alert_time)
    job_queue.run_daily(daily_journal_job, time=journal_time)
    job_queue.run_daily(daily_etf_collection_job, time=etf_collection_time)
    job_queue.run_daily(nightly_portfolio_refresh_job, time=nightly_time)

    # 20:00 백업 (16:xx에서 데이터 못 가져온 경우 재시도)
    try:
        backup_time = datetime.time(hour=20, minute=0, second=0, tzinfo=pytz.timezone('Asia/Seoul'))
    except:
        backup_time = datetime.time(hour=20, minute=0, second=0)
    job_queue.run_daily(evening_backup_job, time=backup_time)

    # 23:00 투자유의종목 야간 업데이트
    try:
        late_alert_time = datetime.time(hour=23, minute=0, second=0, tzinfo=pytz.timezone('Asia/Seoul'))
    except:
        late_alert_time = datetime.time(hour=23, minute=0, second=0)
    job_queue.run_daily(late_market_alert_job, time=late_alert_time)

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
            for h, m in [(7,0),(8,0),(9,0),(10,0),(11,0),(12,0),(13,0),(14,0),(15,0),(16,0),(17,0)]
        ]
    except:
        wisereport_times = [
            datetime.time(hour=h, minute=m, second=0)
            for h, m in [(7,0),(8,0),(9,0),(10,0),(11,0),(12,0),(13,0),(14,0),(15,0),(16,0),(17,0)]
        ]
    for t in wisereport_times:
        job_queue.run_daily(wisereport_job, time=t)

    print(f"Bot started at {datetime.datetime.now()}")
    print(f"✅ Daily jobs scheduled:")
    print(f"  - Featured data: 06:00 KST (전일 데이터, 익일 수집)")
    print(f"  - Weather: 05:00 KST")
    print(f"  - Calendar: 05:05 KST")
    print(f"  - Headlines: 05:10 KST")
    print(f"  - Portfolio report: 16:00 KST")
    print(f"  - Market alert: 16:05 KST (투자유의종목)")
    print(f"  - Journal data: 16:10 KST (투자일지)")
    print(f"  - Auto portfolio update: 09:30~15:35 KST (30분 간격, 거래일만)")
    print(f"  - Nightly portfolio refresh: 16:20 KST (당일 주문 반영)")
    print(f"  - ETF collection: 16:30 KST (구성종목 수집)")
    print(f"  - Evening backup: 20:00 KST (16:xx 실패 시 재시도)")
    print(f"  - Late market alert: 23:00 KST (투자유의종목 야간 업데이트)")
    print(f"  - WiseReport: 07~15,17 KST (리서치 리포트, 매시 정각)")
    application.run_polling()
