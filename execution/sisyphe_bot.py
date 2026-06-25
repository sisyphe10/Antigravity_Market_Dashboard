import logging
import datetime
import os
import asyncio
import subprocess
import sys
import json
import fcntl

# 중복 실행 방지 (파일 락)
_lock_file = open('/tmp/sisyphe_bot.lock', 'w')
try:
    fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    _lock_file.write(str(os.getpid()))
    _lock_file.flush()
except IOError:
    print("ERROR: sisyphe_bot is already running. Exiting.")
    sys.exit(1)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from dotenv import load_dotenv

# 로깅 설정
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# 텔레그램 polling getUpdates 로그 제거 (10초마다 INFO → 디스크/journal 점거)
logging.getLogger("httpx").setLevel(logging.WARNING)

# 환경 변수 로드
load_dotenv()
TOKEN = os.getenv("TELEGRAM_SISYPHE_BOT_TOKEN")

# Market Dashboard 저장소 경로
DASHBOARD_DIR = os.path.join(os.path.expanduser('~'), 'Antigravity_Market_Dashboard')

SUBSCRIBERS_FILE = os.path.join(DASHBOARD_DIR, 'subscribers.json')

KST = datetime.timezone(datetime.timedelta(hours=9))

# 데일리 스케줄 job misfire 방지 (2026-06-24 journal 16:10 누락 사고).
# 직전 무거운 job(16:00 리포트 등)이 동기 subprocess로 이벤트 루프를 잠깐 점유하면
# 후속 job이 몇 초 늦어져 apscheduler 기본 grace(1초)를 넘겨 스킵된다.
# 10분 유예 + coalesce 로 데일리 수집이 약간 늦어도 반드시 실행되게 한다.
DAILY_JOB_KWARGS = {'misfire_grace_time': 600, 'coalesce': True}

# 당일 포트폴리오 리포트 전송 추적 (중복 방지) — 봇 재시작에도 살아남도록 파일 영속화
PORTFOLIO_REPORT_STATE_FILE = os.path.join(DASHBOARD_DIR, '.portfolio_report_sent.json')


def _load_portfolio_report_sent_date():
    try:
        with open(PORTFOLIO_REPORT_STATE_FILE, 'r', encoding='utf-8') as f:
            return (json.load(f) or {}).get('last_sent_date')
    except FileNotFoundError:
        return None
    except Exception as e:
        logging.warning(f"Failed to read portfolio report state: {e}")
        return None


def _save_portfolio_report_sent_date(date_str):
    try:
        with open(PORTFOLIO_REPORT_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'last_sent_date': date_str}, f)
    except Exception as e:
        logging.error(f"Failed to write portfolio report state: {e}")


def git_sync(cwd):
    """VM git 동기화: fetch + reset --hard (충돌 불가)"""
    subprocess.run(["git", "fetch", "origin", "main"], cwd=cwd, capture_output=True, timeout=60)
    subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=cwd, capture_output=True, timeout=30)


def git_push_safe(cwd, xlsx_conflict="bail"):
    """이미 add+commit 된 HEAD 커밋을 race-safe 하게 push (GHA와 push 정책 통일).

    GHA 3종(recalc/finalize/daily_crawl)이 쓰는 scripts/safe_commit_push.sh 를
    --push-head 모드로 호출한다. 충돌 시 **whole-file 3-way merge**(우리가 바꾼
    파일=ours, 안 바꾼 파일=theirs, Wrap_NAV.xlsx는 시트 3-way merge)로 해소 →
    구 `merge -X ours` 의 blind overwrite(GHA 산출물 통째 덮어쓰기) 제거. 그래도
    못 풀면 스크립트가 origin/main 으로 reset 후 종료(bail)하므로 VM 이 stuck
    상태로 미push 커밋을 누적하지 않는다(해당 회차만 누락, 다음 주기 재생성).
    """
    result = subprocess.run(
        ["bash", "scripts/safe_commit_push.sh", "--push-head", "--xlsx-conflict", xlsx_conflict],
        cwd=cwd, capture_output=True, text=True, timeout=180
    )
    if result.returncode != 0:
        logging.warning(f"safe_commit_push 실패 (rc={result.returncode}): "
                        f"{(result.stdout or '')[-200:]} {(result.stderr or '')[-200:]}")
        return False
    return True


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

📓 **투자일지 (Journal)**
/journal 장전 오늘은 매수 중지 예정
/journal 장후 예상대로 하락, 관망 유지

💡 **투자 아이디어 (Ideas)**
/idea 삼성전자 BUY 반도체 사이클 하단
/idea SK하이닉스 WATCH HBM 가격 정상화
• 액션: BUY/SELL/WATCH/ADD/CUT/HOLD
• 종목별 아이디어가 Journal 페이지 Ideas 탭에 누적

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
            capture_output=True, text=True, timeout=240
        )
        subprocess.run(
            [sys.executable, "calculate_returns.py"],
            capture_output=True, text=True, timeout=180
        )

        # daily_portfolio_report.py 실행
        result = subprocess.run(
            [sys.executable, "execution/daily_portfolio_report.py", "--no-send"],
            capture_output=True,
            text=True,
            timeout=180
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
                cwd=parent_dir, capture_output=True, text=True, timeout=240
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
        capture_output=True, text=True, timeout=300,
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

    # 2. 실시간 주가 조회 — KIS multprice 배치(장중 실시간) 우선, 누락분만 FDR/네이버 폴백
    logging.info(f"Update Step 2: Fetching {len(all_codes)} stock prices...")
    price_map = {}
    stock_codes = [c for c in all_codes if c not in _NAVER_INDEX_CODES]

    # 2a. KIS 배치 (종목). prdy_ctrt = 당일 등락률(장중 실시간) → FDR 일봉 지연 문제 회피.
    try:
        from kis_token import fetch_changes
        kis_chg = fetch_changes(stock_codes)
        price_map.update(kis_chg)
        logging.info(f"Update Step 2: KIS multprice {len(kis_chg)}/{len(stock_codes)}종목")
    except Exception as e:
        logging.warning(f"Update Step 2: KIS multprice 실패 → FDR 폴백: {e}")

    # 2b. KIS 누락 종목 + 지수 → FDR/네이버 폴백 (스레드)
    fallback_codes = [c for c in all_codes if c not in price_map]
    if fallback_codes:
        logging.info(f"Update Step 2: FDR/네이버 폴백 {len(fallback_codes)}건")
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_price, code): code for code in fallback_codes}
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
                # 기여도는 표·메시지(D-1 뷰) 기준 → weight_prev 사용 (평소엔 weight와 동일)
                _wp = s.get('weight_prev')
                _wp = s['weight'] if _wp is None else _wp
                s['contribution'] = (_wp / 100) * (today_return / 100) * 1000
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
        timeout=240,
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
        ["git", "commit", "-m", f"Update portfolio tables ({now_str}) [skip ci]"],
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

    def _disp_w(s):
        # 표시 비중 = weight_prev(D-1). 당일 finalize된 주문은 다음 거래일부터 반영.
        wp = s.get('weight_prev')
        return (s.get('weight', 0) or 0) if wp is None else wp

    for portfolio_name, stocks in portfolio_data.items():
        if portfolio_name.startswith('_'):
            continue
        # D-1 보유분만 표시 (당일 신규 편입은 다음 거래일부터)
        held = [s for s in stocks if (_disp_w(s) or 0) > 0]
        # 포트폴리오 가중 평균 수익률
        # 비중 합계가 100% 미만이면 나머지는 현금(수익률 0%)으로 처리
        weighted_return = sum(
            _disp_w(s) * (s['today_return'] or 0)
            for s in held
        ) / 100

        lines.append(f"<b><u>[{portfolio_name}]</u></b>")
        lines.append(f"<b><u>오늘: {weighted_return:+.1f}%</u></b>")

        # 보유 종목 전체 — 기여도(contribution) 내림차순. +기여/−기여 그룹별 구분선·소계.
        ranked = sorted(
            held,
            key=lambda x: (x.get('contribution') if x.get('contribution') is not None else float('-inf')),
            reverse=True
        )

        def _stock_line(s):
            contrib = s.get('contribution')
            contrib_str = f" {contrib:+.2f}" if contrib is not None else ""
            tr = s.get('today_return')
            tr_str = f" {tr:+.1f}%" if tr is not None else " N/A"
            return f"  {s['name']}{tr_str}{contrib_str}"

        pos = [s for s in ranked if (s.get('contribution') or 0) > 0]
        nonpos = [s for s in ranked if (s.get('contribution') or 0) <= 0]
        if pos:
            lines.extend(_stock_line(s) for s in pos)
            lines.append(f"  <b>──── 기여 {sum(s['contribution'] for s in pos):+.2f} ────</b>")
        if nonpos:
            lines.extend(_stock_line(s) for s in nonpos)
            lines.append(f"  <b>──── 기여 {sum((s.get('contribution') or 0) for s in nonpos):+.2f} ────</b>")

        lines.append("")

    # ── 주문 변경 내역 (당일 최종 저장분, 다음 거래일 반영 예정) ──
    order_changes = portfolio_data.get('_order_changes') or {}
    if order_changes:
        lines.append("———————————————")
        lines.append("<b>주문 변경 내역</b>")
        for pname, ch in order_changes.items():
            if not ch:
                continue
            lines.append("")
            lines.append(f"<b>[{pname}]</b>")
            added = ch.get('added', [])
            changed = ch.get('changed', [])
            removed = ch.get('removed', [])
            if added:
                lines.append("<b>신규</b>  " + ", ".join(f"{a['name']} {a['weight']:g}%" for a in added))
            if changed:
                lines.append("<b>변경</b>  " + ", ".join(f"{cg['name']} {cg['from']:g}% → {cg['to']:g}%" for cg in changed))
            if removed:
                lines.append("<b>편출</b>  " + ", ".join(f"{r['name']} {r['weight']:g}%" for r in removed))

    return "\n".join(lines)


async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """포트폴리오 테이블 실시간 업데이트"""
    chat_id = update.effective_chat.id
    status_msg = await update.message.reply_text("📊 포트폴리오 테이블 업데이트 중...")

    try:
        loop = asyncio.get_running_loop()
        portfolio_data = await asyncio.wait_for(
            loop.run_in_executor(None, run_portfolio_update),
            timeout=600.0
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
            timeout=600.0
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
                timeout=240
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
            capture_output=True, text=True, timeout=300
        )

        # 2. 수익률 계산
        logging.info("Step 2: Calculating returns...")
        result_returns = subprocess.run(
            [sys.executable, "calculate_returns.py"],
            capture_output=True,
            text=True,
            timeout=180
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
            capture_output=True, text=True, timeout=180
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
            timeout=240
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

        # 4. 포트폴리오 리포트 생성 및 전송 (당일 미전송 시에만, 봇 재시작에도 dedup 유지)
        today_kst = datetime.datetime.now(tz=KST).strftime('%Y-%m-%d')
        if _load_portfolio_report_sent_date() == today_kst:
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
                _save_portfolio_report_sent_date(today_kst)
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

        # Step 2: Featured 데이터 수집 (KIS 전종목 배치 — 2026-06 KRX에서 컷오버)
        # featured_data.json에 랭킹 6종 + 신고가 3종(20d/120d/52w) 누적. 장 마감 직후 같은날 값.
        result = subprocess.run(
            [sys.executable, "execution/fetch_featured_data_kis.py"],
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

        # 외국인/기관 수급 갱신 (네이버 frgn 스크래핑) — 대시보드 재생성 전에 실행해서 wrap PORTFOLIO 표에 즉시 반영
        invtr_result = subprocess.run(
            [sys.executable, "execution/fetch_investor_trading.py"],
            capture_output=True, text=True, timeout=120, cwd=dashboard_dir
        )
        if invtr_result.returncode == 0:
            logging.info(f"{tag} investor_trading: {invtr_result.stdout.strip()[-200:]}")
        else:
            errors.append(f"investor_trading 실패: {invtr_result.stderr[-200:]}")
            logging.warning(f"{tag} {errors[-1]}")

        # 에러가 있더라도 대시보드 재생성 시도 (기존 데이터로라도 갱신)
        subprocess.run([sys.executable, "execution/create_dashboard.py"],
                       capture_output=True, text=True, timeout=120, cwd=dashboard_dir)

        now_str = now_kst.strftime("%Y-%m-%d %H:%M")
        subprocess.run(["git", "add", "featured.html", "featured_data.json", "featured_news.json",
                        "etf.html", "index.html", "market.html", "wrap.html",
                        "investor_trading.json"],
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


async def morning_featured_recovery_job(context: ContextTypes.DEFAULT_TYPE):
    """08:30 KST - 전일 Featured 데이터 누락 시 재수집 (KRX 지연 대응)"""
    import holidays
    now_kst = datetime.datetime.now(tz=KST)
    today = now_kst.date()

    # 직전 거래일 계산 (주말/공휴일 제외)
    kr_holidays = holidays.KR(years=[today.year, today.year - 1])
    prev_day = today - datetime.timedelta(days=1)
    while prev_day.weekday() >= 5 or prev_day in kr_holidays:
        prev_day -= datetime.timedelta(days=1)
    prev_day_str = prev_day.strftime('%Y-%m-%d')

    # featured_data.json에 직전 거래일 데이터 있는지 확인
    dashboard_dir = DASHBOARD_DIR
    featured_path = os.path.join(dashboard_dir, 'featured_data.json')
    try:
        with open(featured_path, 'r', encoding='utf-8') as f:
            featured = json.load(f)
        has_prev = any(r.get('d') == prev_day_str for r in featured)
    except Exception as e:
        logging.error(f"Featured [08:30] 파일 읽기 실패: {e}")
        return

    if has_prev:
        logging.info(f"Featured [08:30] 직전 거래일({prev_day_str}) 데이터 정상 - 스킵")
        return

    # 누락됨 → featured_update_job 실행 (KIS 수집은 당일만 가능 — 과거일 백필 불가, 같은날 재수집 시도)
    logging.warning(f"Featured [08:30] 직전 거래일({prev_day_str}) 누락 감지 → 재수집 시작")
    await featured_update_job(context)

    # 재수집 후 확인
    try:
        with open(featured_path, 'r', encoding='utf-8') as f:
            featured_after = json.load(f)
        recovered_count = sum(1 for r in featured_after if r.get('d') == prev_day_str)
    except Exception:
        recovered_count = 0

    # 텔레그램 알림
    if recovered_count > 0:
        msg = f"✅ Featured 익일 복구 완료\n직전 거래일 {prev_day_str}: {recovered_count}건 수집"
    else:
        msg = f"⚠️ Featured 익일 복구 실패\n직전 거래일 {prev_day_str} 데이터 여전히 없음 (KRX 지속 지연)"
    for chat_id in SUBSCRIBERS:
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg)
        except Exception:
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


# ETF 구성종목 수집은 systemd 타이머로 이관됨 (2026-06-25):
#   etf-collect.timer (16:30 KST) + etf-collect-retry.timer (18:00 KST, >=1000 가드로 idempotent)
#   → run_etf_collect.sh → execution/etf_collector/collect_etf_daily.py
# 봇 apscheduler 인메모리 잡일 때는 배포(봇 재시작)가 진행 중인 수집을 SIGTERM으로 죽이고
# 인메모리 재시도까지 소실시켰음 (2026-05-13, 2026-06-25 사고). 타이머는 별도 cgroup이라 무관.
# etf.html 재생성·push는 기존대로 18:30 Featured 2차 잡(featured_update_job)이 담당.


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

        # 3. Journal data (16:10에 misfire/실패했을 수 있음 — 16:10은 자동복구가 없던 유일 job)
        logging.info("Backup: journal data...")
        await daily_journal_job(context)

        # ETF 수집 백업은 etf-collect-retry.timer(18:00)가 담당 (봇 분리, 위 주석 참고)

        logging.info("Evening backup job completed")
    except Exception as e:
        logging.error(f"Evening backup job error: {e}")


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

    # 하이라이트 일정 D-Day 알림 → 선유듀오봇(@SeonyuDuo_bot)으로 이관(MOVE).
    # 가족 생일/명절·'D-day |' 사전 알림은 이제 seonyuduo_exercise_bot.py 06:00 다이제스트가
    # 부부 그룹챗으로 발송한다. Sisyphe 개인봇에서는 중복 발송을 막기 위해 호출하지 않음.
    # (아래 check_dday_alerts는 이력 보존용으로 남겨두되 호출하지 않으며, 호출돼도 즉시 반환)


async def check_dday_alerts(context):
    """[DEPRECATED] 하이라이트 일정 D-Day 알림 — 선유듀오봇으로 이관됨.
    seonyuduo_exercise_bot.py 의 _collect_dday_highlights_sync / _send_dday_alerts 가 대체.
    중복 발송 방지를 위해 즉시 반환한다. (로직은 이력 참조용으로 보존)"""
    return
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

def _append_row(service, sheet_name, row, value_input_option='USER_ENTERED'):
    """시트에 행 추가. RAW 모드로 호출하면 '31:26' 같은 문자열 자동 변환 방지"""
    service.spreadsheets().values().append(
        spreadsheetId=SISYPHE_SHEET_ID,
        range=sheet_name,
        valueInputOption=value_input_option,
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


def _parse_weight_memo(memo):
    """웨이트 메모를 운동별로 분해.
    '데드리프트 20kg x 20회 x 3세트, 벤치 60kg x 8회 x 4세트' →
    [{'name':'데드리프트','weight':20.0,'reps':20,'sets':3}, ...]
    쉼표 = 새 운동 행.
    """
    import re
    if not memo:
        return []
    segments = [s.strip() for s in memo.split(',') if s.strip()]
    result = []
    for seg in segments:
        tokens = seg.split()
        name_tokens = []
        for t in tokens:
            if re.search(r'\d', t):
                break
            name_tokens.append(t)
        name = ' '.join(name_tokens)
        if not name:
            continue
        weight_m = re.search(r'(\d+(?:\.\d+)?)\s*kg', seg, re.IGNORECASE)
        reps_m = re.search(r'(\d+)\s*회', seg)
        sets_m = re.search(r'(\d+)\s*세트', seg)
        result.append({
            'name': name,
            'weight': float(weight_m.group(1)) if weight_m else None,
            'reps': int(reps_m.group(1)) if reps_m else None,
            'sets': int(sets_m.group(1)) if sets_m else None,
        })
    return result


def _detect_body_part(memo):
    """웨이트 메모에서 운동 부위 감지: 등/가슴/어깨/팔/하체, 하체+기타=전신"""
    if not memo:
        return ''
    body_map = {
        '등': ['데드리프트', '랫풀', '풀업', '친업', '롱풀', '시티드로우', '케이블로우', '바벨로우', '로우'],
        '가슴': ['벤치프레스', '벤치 프레스', '체스트', '플라이', '딥스', '푸시업', '체스트프레스'],
        '어깨': ['숄더', '레터럴', '리어 델트', '업라이트', '오버헤드'],
        '팔': ['바이셉', '트라이셉', '해머컬', '킥백', '푸시다운'],
        '하체': ['스쿼트', '런지', '레그', '카프', 'RDL', '힙쓰러스트', '불가리안', '글루트', '어덕션', '핵스쿼트'],
    }
    found = []
    for part, keywords in body_map.items():
        for kw in keywords:
            if kw in memo:
                if part not in found:
                    found.append(part)
                break
    if not found:
        return ''
    if '하체' in found and len(found) > 1:
        return '전신'
    return '/'.join(found)


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

        # Google Sheets 라우팅:
        #   런닝/테니스 → '운동기록' (날짜, 유형, 거리, 시간, HR, 케이던스, 피로도, 메모)
        #   웨이트 → '웨이트' (날짜, 운동부위, 종목, 무게, 반복, 세트, 피로도) - 운동별 다행
        try:
            service = _get_sheets_service()
            if service:
                if entry['type'] == '웨이트':
                    exercises = _parse_weight_memo(entry.get('memo', ''))
                    fatigue_str = str(entry.get('fatigue', '')) if entry.get('fatigue') is not None else ''
                    if not exercises:
                        # 파싱 실패 시 원본 메모를 종목 칸에만 넣어 1행 생성
                        row = [entry.get('date', ''), _detect_body_part(entry.get('memo', '')),
                               entry.get('memo', ''), '', '', '', fatigue_str]
                        _append_row(service, '웨이트', row, value_input_option='RAW')
                    else:
                        for i, ex in enumerate(exercises):
                            row = [
                                entry.get('date', ''),
                                _detect_body_part(ex['name']),
                                ex['name'],
                                str(ex['weight']) if ex['weight'] is not None else '',
                                str(ex['reps']) if ex['reps'] is not None else '',
                                str(ex['sets']) if ex['sets'] is not None else '',
                                fatigue_str if i == 0 else '',  # 첫 행에만 피로도
                            ]
                            _append_row(service, '웨이트', row, value_input_option='RAW')
                else:
                    row = [
                        entry.get('date', ''),
                        entry.get('type', ''),
                        str(entry.get('distance', '')) if entry.get('distance') not in (None, 0, '') else '',
                        str(entry.get('duration', '')) if entry.get('duration') not in (None, 0, '') else '',
                        str(entry.get('hr', '')) if entry.get('hr') is not None else '',
                        str(entry.get('cadence', '')) if entry.get('cadence') is not None else '',
                        str(entry.get('fatigue', '')) if entry.get('fatigue') is not None else '',
                        entry.get('memo', ''),
                    ]
                    _append_row(service, '운동기록', row, value_input_option='RAW')
        except Exception as sheet_e:
            logging.warning(f"Sheets append 실패 (무시, data.json은 성공): {sheet_e}")

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


async def idea_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/idea 종목명 액션 아이디어 - 투자 아이디어를 Ideas 시트에 추가"""
    service = _get_journal_service()
    if not service:
        await update.message.reply_text("❌ Google 서비스 계정이 설정되지 않았습니다.")
        return

    raw_text = update.message.text or ''
    parts = raw_text.split(None, 3)  # ['/idea', '종목명', '액션', '아이디어 전체']
    if len(parts) < 4:
        await update.message.reply_text(
            "<b>투자 아이디어 입력</b>\n\n"
            "<code>/idea 삼성전자 BUY 반도체 사이클 하단</code>\n"
            "<code>/idea SK하이닉스 WATCH HBM 가격 정상화</code>\n"
            "<code>/idea 한섬 SELL 의류 비중 줄이기</code>\n\n"
            "형식: /idea [종목명] [액션] [아이디어]\n"
            "액션: BUY / SELL / WATCH / ADD / CUT / HOLD",
            parse_mode='HTML'
        )
        return

    stock_input = parts[1]
    action = parts[2].upper()
    idea_text = parts[3]

    # 종목 lookup (Wrap_NAV.xlsx Code 시트)
    try:
        import pandas as pd
        df_code = pd.read_excel('Wrap_NAV.xlsx', sheet_name='Code')
        match = df_code[df_code['종목명'] == stock_input]
        if match.empty:
            match = df_code[df_code['종목명'].str.contains(stock_input, na=False, regex=False)]
        if match.empty:
            await update.message.reply_text(
                f"❌ '{stock_input}' 종목을 찾을 수 없습니다.\n"
                f"Wrap_NAV.xlsx Code 시트에 등록된 종목명을 정확히 입력해주세요."
            )
            return
        if len(match) > 1:
            names = ', '.join(match['종목명'].head(5).tolist())
            await update.message.reply_text(
                f"⚠️ 여러 종목 매칭됨: {names}\n정확한 종목명으로 다시 입력해주세요."
            )
            return
        code = str(match.iloc[0]['종목코드']).zfill(6)
        actual_name = match.iloc[0]['종목명']
    except Exception as e:
        await update.message.reply_text(f"❌ 종목 조회 실패: {e}")
        return

    # 날짜/요일
    KST_tz = datetime.timezone(datetime.timedelta(hours=9))
    today = datetime.datetime.now(tz=KST_tz)
    today_str = today.strftime('%Y-%m-%d')
    dow_names = ['월', '화', '수', '목', '금', '토', '일']
    dow = dow_names[today.weekday()]

    # 네이버 금융에서 시가총액 fetch (X-시가총액 = 입력 시점 시총, 억원 단위 정수)
    market_cap_x = ''
    try:
        import requests
        r = requests.get(
            f'https://finance.naver.com/item/main.naver?code={code}',
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=10
        )
        r.encoding = 'euc-kr'
        # <em id="_market_sum"> 안에 "1,234,567" 형태. 내부에 \n / 공백 / 콤마 섞임
        m = re.search(r'<em id="_market_sum">([\s\S]*?)</em>', r.text)
        if m:
            raw = re.sub(r'[^\d]', '', m.group(1))
            if raw:
                market_cap_x = int(raw)  # 억원 단위 정수 (시트가 천 단위 콤마 자동 포맷)
    except Exception as e:
        logging.warning(f'네이버 시총 fetch 실패: {e}')

    # 새 행 번호 (수식에 행 번호 박기 위해 미리 계산)
    try:
        rows_result = service.spreadsheets().values().get(
            spreadsheetId=JOURNAL_SHEET_ID,
            range='Ideas!A:A'
        ).execute()
        new_row_num = len(rows_result.get('values', [])) + 1
    except Exception:
        new_row_num = 2  # fallback

    # 시트 row 패턴 (A 날짜, B =A{N}, C 코드, D 종목, E 시총X, F GOOGLEFINANCE 시총, G 수익률, H 액션, I 아이디어)
    b_formula = f'=A{new_row_num}'
    f_formula = f'=GOOGLEFINANCE(C{new_row_num},"marketcap")/100000000'
    g_formula = f'=F{new_row_num}/E{new_row_num}-1'

    try:
        new_row = [today_str, b_formula, "'" + code, actual_name, market_cap_x, f_formula, g_formula, action, idea_text]
        service.spreadsheets().values().append(
            spreadsheetId=JOURNAL_SHEET_ID,
            range='Ideas!A1:I1',
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body={'values': [new_row]}
        ).execute()

        await update.message.reply_text(
            f"✅ <b>Ideas 추가됨</b>\n"
            f"📅 {today_str} ({dow})\n"
            f"📌 <b>{actual_name}</b> ({code})\n"
            f"🎯 액션: <b>{action}</b>\n"
            f"💡 {idea_text}",
            parse_mode='HTML'
        )
        logging.info(f"Idea added: {actual_name} ({code}) {action} - {idea_text[:50]}")

    except Exception as e:
        logging.error(f"Idea error: {e}")
        await update.message.reply_text(f"❌ Ideas 시트 쓰기 실패: {str(e)}")


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
        amt_raw = (row[3] if len(row) > 3 else '').replace(',', '').strip()
        try:
            amt = int(amt_raw) if amt_raw else 0
        except ValueError:
            amt = 0
        # 금액 빈칸/0 카테고리는 소진율 계산서 중립 (지출도 미포함, 한도도 0)
        if cat and cat not in BUDGET_EXCLUDE and amt > 0:
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




# ============================================================
# 가계부 거래 알림 + 답장 분류/수정/제외
# ============================================================
LEDGER_TX_SHEET = '거래내역'
LEDGER_RULES_SHEET = 'ledger_category'
UNCAT_LABEL = '미분류'
UNCAT_NOTIFY_MARKER = '🏷️ 미분류 거래'      # 미분류 거래 알림 (답장→분류)
LEDGER_NOTIFY_MARKER = '🧾 가계부 등록'      # 분류된 거래 알림 (답장→수정/제외)
LEDGER_NOTIFIED_FILE = os.path.join(DASHBOARD_DIR, '.ledger_notified.json')

# 선유듀오 공유 시트 (답장 '선유듀오' → 시지프에서 제외 + 선유듀오 가계부로 이동). 같은 서비스계정.
SEONYUDUO_SHEET_ID = '1w6q3UwUER7oINuk50LyMzgF2K0Fbt2wgSVJ34vImo0g'
SEONYUDUO_LEDGER_TAB = '가계부'   # 컬럼: 날짜·유형·카테고리·금액·메모 (+통장)
SEONYUDUO_MOVE_KEYWORDS = {'선유', '선유듀오', '듀오'}

# 이관 시 @SeonyuDuo_bot(별도 토큰)으로 부부 그룹챗에 지출 알림. chat_id는 운동봇이 캡처해 둔 파일에서 읽음.
SEONYUDUO_BOT_TOKEN = os.getenv('TELEGRAM_SEONYUDUO_BOT_TOKEN')
SEONYUDUO_CHATS_FILE = os.path.join(DASHBOARD_DIR, 'seonyuduo_chats.json')
SEONYUDUO_MONTHLY_BUDGET = 800000  # 월 예산(원), /ledger2와 동일


def _load_seonyuduo_chats():
    """운동봇이 캡처한 그룹챗 id 리스트."""
    try:
        with open(SEONYUDUO_CHATS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f) or {}
        return list(data.keys()) if isinstance(data, dict) else [str(x) for x in data]
    except FileNotFoundError:
        return []
    except Exception as e:
        logging.warning(f"선유듀오 chats 읽기 실패: {e}")
        return []


def _seonyuduo_tg_send(chat_id, text):
    """@SeonyuDuo_bot 토큰으로 동기 전송 (asyncio.to_thread에서 호출). PTB Bot 수명주기 회피."""
    import urllib.request
    import urllib.parse
    data = urllib.parse.urlencode({
        'chat_id': chat_id, 'text': text,
        'parse_mode': 'HTML', 'disable_web_page_preview': 'true',
    }).encode()
    req = urllib.request.Request(
        f'https://api.telegram.org/bot{SEONYUDUO_BOT_TOKEN}/sendMessage', data=data)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


async def _notify_seonyuduo_spend(service, merchant, category, amount):
    """선유듀오 이관 성공 시 @SeonyuDuo_bot 그룹챗에 지출 알림. 실패해도 이관 결과는 유지."""
    import html
    if not SEONYUDUO_BOT_TOKEN:
        logging.info("선유듀오 봇 토큰 없음 → 그룹 알림 skip")
        return
    chats = _load_seonyuduo_chats()
    if not chats:
        logging.info("선유듀오 캡처된 그룹챗 없음 → 그룹 알림 skip")
        return
    # 선유듀오 가계부 이번달 누적 지출 (/ledger2 total_spent 로직과 동일)
    total_spent = 0
    try:
        rows = await asyncio.to_thread(
            _read_range, service, SEONYUDUO_SHEET_ID, f'{SEONYUDUO_LEDGER_TAB}!A:F')
        month_prefix = datetime.datetime.now(tz=KST).strftime('%Y-%m')
        for r in (rows[1:] if rows else []):
            if len(r) > 3 and str(r[0]).startswith(month_prefix) and r[1] == '지출':
                try:
                    total_spent += int(str(r[3]).replace(',', '') or '0')
                except ValueError:
                    pass
    except Exception as e:
        logging.warning(f"선유듀오 월 집계 실패(알림은 진행): {e}")
    budget = SEONYUDUO_MONTHLY_BUDGET
    pct = max(0, round(total_spent / budget * 100)) if budget else 0  # 환불로 음수면 0% 표시
    remaining = max(0, budget - total_spent)
    filled = min(10, max(0, round(pct / 100 * 10)))
    bar = '█' * filled + '░' * (10 - filled)
    try:
        amt_int = int(amount)
        amt_disp = f"{amt_int:,}원"
        is_cancel = amt_int < 0
    except (ValueError, TypeError):
        amt_disp = f"{amount}원"
        is_cancel = False
    head = '↩️ <b>취소/환불</b>' if is_cancel else '💸 <b>지출</b>'
    text = (
        f"<b><u>선유듀오 가계부</u></b>\n"
        f"{head}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🏪 {html.escape(str(merchant))}\n"
        f"📂 {html.escape(str(category) or '미분류')}\n"
        f"💰 {amt_disp}\n\n"
        f"📊 이번달 누적 {total_spent:,}원 · 예산 소진율 {pct}% [{bar}]\n"
        f"💵 잔액 {remaining:,}원"
    )
    sent = 0
    for cid in chats:
        try:
            await asyncio.to_thread(_seonyuduo_tg_send, int(cid), text)
            sent += 1
        except Exception as e:
            logging.warning(f"선유듀오 그룹 알림 전송 실패 ({cid}): {e}")
    logging.info(f"선유듀오 그룹 지출 알림 {sent}/{len(chats)}건 전송: {merchant} {amt_disp}")


def _load_ledger_notified():
    """알림 보낸 거래 키 집합. 파일 없으면 None(최초 실행 → baseline)."""
    try:
        with open(LEDGER_NOTIFIED_FILE, 'r', encoding='utf-8') as f:
            return set(json.load(f) or [])
    except FileNotFoundError:
        return None
    except Exception as e:
        logging.warning(f"ledger notified 읽기 실패: {e}")
        return set()


def _save_ledger_notified(keys):
    try:
        with open(LEDGER_NOTIFIED_FILE, 'w', encoding='utf-8') as f:
            json.dump(sorted(keys), f, ensure_ascii=False)
    except Exception as e:
        logging.error(f"ledger notified 저장 실패: {e}")


def _uncat_key(date, mer, amt):
    return f"{date}|{mer}|{str(amt).replace(',', '').replace(' ', '')}"


def _norm_amt(a):
    """금액 정규화: 콤마/공백/원 제거 (행 매칭용)."""
    return str(a).replace(',', '').replace(' ', '').replace('원', '').strip()


def _get_sheet_id(service, sheet_name):
    """탭 이름 → sheetId(gid). 행 삭제(batchUpdate)에 필요."""
    meta = service.spreadsheets().get(spreadsheetId=SISYPHE_SHEET_ID).execute()
    for sh in meta.get('sheets', []):
        if sh.get('properties', {}).get('title') == sheet_name:
            return sh['properties']['sheetId']
    return None


def _update_cell(service, sheet_name, a1, value):
    """단일 셀 RAW 업데이트 (예: ledger_category!B5)."""
    service.spreadsheets().values().update(
        spreadsheetId=SISYPHE_SHEET_ID,
        range=f'{sheet_name}!{a1}',
        valueInputOption='RAW',
        body={'values': [[value]]}
    ).execute()


def _delete_sheet_row(service, sheet_id, row_index):
    """0-based 행 인덱스(헤더=0) 1개 삭제."""
    service.spreadsheets().batchUpdate(
        spreadsheetId=SISYPHE_SHEET_ID,
        body={'requests': [{
            'deleteDimension': {
                'range': {
                    'sheetId': sheet_id,
                    'dimension': 'ROWS',
                    'startIndex': row_index,
                    'endIndex': row_index + 1,
                }
            }
        }]}
    ).execute()


def _read_range(service, spreadsheet_id, rng):
    """임의 스프레드시트/범위 읽기."""
    return service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=rng).execute().get('values', [])


def _update_range(service, spreadsheet_id, rng, values, value_input_option='USER_ENTERED'):
    """임의 스프레드시트/범위에 2D 값 기록."""
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=rng,
        valueInputOption=value_input_option, body={'values': values}
    ).execute()


async def check_uncategorized_job(context: ContextTypes.DEFAULT_TYPE):
    """거래내역에 신규 행이 추가되면 텔레그램 알림 (분류/미분류 모두)."""
    import html
    try:
        service = _get_sheets_service()
        if not service:
            return
        rows = await asyncio.to_thread(_read_sheet, service, LEDGER_TX_SHEET)
        notified = _load_ledger_notified()
        seed = notified is None  # 최초 실행: 기존 거래는 조용히 baseline (스팸 방지)
        if seed:
            notified = set()
        new_items = []
        for row in rows[1:]:  # skip header
            date = row[0] if len(row) > 0 else ''
            cat  = row[2] if len(row) > 2 else ''
            amt  = row[3] if len(row) > 3 else ''
            mer  = row[4] if len(row) > 4 else ''
            if not mer:
                continue
            key = _uncat_key(date, mer, amt)
            if key not in notified:
                notified.add(key)
                new_items.append((cat, mer, amt, date))
        if seed:
            _save_ledger_notified(notified)
            logging.info(f"ledger baseline: 기존 {len(notified)}건 무음 처리")
            return
        for cat, mer, amt, date in new_items:
            try:
                amt_disp = f"{int(str(amt).replace(',', '')):,}원"
            except Exception:
                amt_disp = f"{amt}원"
            if (not cat) or cat == UNCAT_LABEL:
                text = (
                    f"{UNCAT_NOTIFY_MARKER}\n"
                    f"가맹점: {html.escape(str(mer))}\n"
                    f"금액: {amt_disp}\n"
                    f"날짜: {html.escape(str(date))}\n\n"
                    f"이 메시지에 <b>답장</b>으로 카테고리를 보내주세요.\n"
                    f"예) <code>식비</code>\n"
                    f"키워드를 바꾸려면 <code>키워드=카테고리</code> (예: <code>아식스=운동</code>)\n"
                    f"가계부에서 빼려면 <code>제외</code>"
                )
            else:
                text = (
                    f"{LEDGER_NOTIFY_MARKER}\n"
                    f"가맹점: {html.escape(str(mer))}\n"
                    f"금액: {amt_disp}\n"
                    f"카테고리: {html.escape(str(cat))}\n"
                    f"날짜: {html.escape(str(date))}\n\n"
                    f"카테고리가 잘못됐으면 이 메시지에 <b>답장</b>으로 수정 (예: <code>생활용품</code>)\n"
                    f"가계부에서 빼려면 <code>제외</code>"
                )
            for uid in SUBSCRIBERS:
                try:
                    await context.bot.send_message(chat_id=uid, text=text, parse_mode='HTML')
                except Exception as e:
                    logging.warning(f"ledger 알림 전송 실패 ({uid}): {e}")
        if new_items:
            _save_ledger_notified(notified)
            logging.info(f"ledger 알림 {len(new_items)}건 전송")
    except Exception as e:
        logging.error(f"check_uncategorized_job 오류: {e}")


def _resolve_rule_op(rules, merchant, kw, cat):
    """답장을 ledger_category 연산으로 해석. update/append/noop/error 딕셔너리 반환.
    kw 지정 시 정확일치 행, 미지정 시 가맹점 매칭 행(수식 첫 매칭 모사) 기준."""
    if kw:
        for i, r in enumerate(rules):
            if r and r[0].strip() == kw:
                old = (r[1] if len(r) > 1 else '').strip()
                if old == cat:
                    return {'action': 'noop', 'text': f"ℹ️ '{kw}' → '{cat}' 규칙이 이미 있습니다."}
                return {'action': 'update', 'row': i + 1, 'kw': kw, 'old': old, 'cat': cat}
        return {'action': 'append', 'kw': kw, 'cat': cat}
    for i, r in enumerate(rules):
        if i == 0:  # 헤더(키워드|카테고리)
            continue
        k = (r[0].strip() if r and len(r) > 0 else '')
        if k and k.lower() in merchant.lower():
            old = (r[1] if len(r) > 1 else '').strip()
            if old == cat:
                return {'action': 'noop', 'text': f"ℹ️ '{k}' → '{cat}' 규칙이 이미 있습니다."}
            return {'action': 'update', 'row': i + 1, 'kw': k, 'old': old, 'cat': cat}
    if not merchant:
        return {'action': 'error', 'text': "가맹점을 알 수 없어 키워드를 지정해야 합니다. 형식: 키워드=카테고리"}
    return {'action': 'append', 'kw': merchant, 'cat': cat}


async def _ledger_apply_op(service, op):
    """해석된 op를 실제 시트에 반영하고 결과 텍스트를 반환."""
    act = op['action']
    if act in ('noop', 'error'):
        return op['text']
    if act == 'update':
        await asyncio.to_thread(_update_cell, service, LEDGER_RULES_SHEET, f"B{op['row']}", op['cat'])
        old = op.get('old') or '(없음)'
        logging.info(f"ledger_category 수정: {op['kw']} {op.get('old')} -> {op['cat']}")
        return f"✏️ '{op['kw']}' 규칙 수정: {old} → {op['cat']}\n거래내역이 자동 재분류됩니다."
    await asyncio.to_thread(_append_row, service, LEDGER_RULES_SHEET, [op['kw'], op['cat']], 'RAW')
    logging.info(f"ledger_category 추가: {op['kw']} -> {op['cat']}")
    return f"✅ '{op['kw']}' → '{op['cat']}' 분류 규칙 추가됨.\n거래내역이 자동 재분류됩니다."


async def _ledger_upsert_rule(service, context, msg, merchant, kw, cat):
    """ledger_category 규칙 추가/수정. 결과 카테고리가 기존에 없던 신규면 버튼으로 확인."""
    rules = await asyncio.to_thread(_read_sheet, service, LEDGER_RULES_SHEET)
    op = _resolve_rule_op(rules, merchant, kw, cat)
    if op['action'] in ('noop', 'error'):
        await msg.reply_text(op['text'])
        return
    known = {r[1].strip() for r in rules[1:] if len(r) > 1 and r[1].strip()}
    if cat in known:
        await msg.reply_text(await _ledger_apply_op(service, op))
        return
    # 기존에 없던 카테고리 → 오타일 수 있으니 확인
    context.user_data['pending_ledger_op'] = op
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("➕ 새 카테고리로 추가", callback_data='ledgercat:add'),
        InlineKeyboardButton("✖️ 취소", callback_data='ledgercat:cancel'),
    ]])
    sample = ' · '.join(sorted(known)) if known else '(없음)'
    await msg.reply_text(
        f"❓ '{cat}' 은(는) 기존에 없던 카테고리예요.\n"
        f"오타가 아니라면 새 카테고리로 추가할까요?\n\n"
        f"기존 카테고리: {sample}\n\n"
        f"수정하려면 [취소] 후 올바른 카테고리로 다시 답장해주세요.",
        reply_markup=kb,
    )


async def handle_ledger_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """신규 카테고리 확인 버튼 처리."""
    q = update.callback_query
    if not q:
        return
    await q.answer()
    op = context.user_data.pop('pending_ledger_op', None)
    if (q.data or '') == 'ledgercat:cancel':
        await q.edit_message_text("↩️ 취소했어요. 올바른 카테고리로 다시 답장해주세요.")
        return
    if op is None:
        await q.edit_message_text("⌛ 만료된 요청이에요. 알림에 다시 답장해주세요.")
        return
    service = _get_sheets_service()
    if not service:
        await q.edit_message_text("❌ Google 서비스 계정이 설정되지 않았습니다.")
        return
    try:
        result_text = await _ledger_apply_op(service, op)
    except Exception as e:
        logging.error(f"ledger_category 신규 적용 실패: {e}")
        await q.edit_message_text(f"❌ 처리 실패: {e}")
        return
    # 이 콜백은 '신규 카테고리(기존에 없던)' 경로에서만 도달 → 예산 탭에 없으면 추가 확인.
    # op['cat']은 새 카테고리 (append=새 규칙, update=키워드를 새 카테고리로 변경 둘 다 해당).
    new_cat = (op.get('cat') or '').strip()
    try:
        in_budget = await _is_cat_in_budget(service, new_cat)
    except Exception as e:
        logging.warning(f"예산 탭 확인 실패, 프롬프트 생략: {e}")
        in_budget = True
    if new_cat and not in_budget:
        context.user_data['pending_budget_cat'] = new_cat
        context.user_data['pending_budget_text'] = result_text
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("📊 예산에 추가", callback_data='ledgerbudget:add'),
            InlineKeyboardButton("건너뛰기", callback_data='ledgerbudget:skip'),
        ]])
        await q.edit_message_text(
            f"{result_text}\n\n"
            f"💰 '{new_cat}'은(는) 예산 탭에 없어요. 예산 항목으로 추가할까요?\n"
            f"(금액은 나중에 예산 탭에서 직접 입력)",
            reply_markup=kb,
        )
        return
    await q.edit_message_text(result_text)


async def _is_cat_in_budget(service, cat):
    """예산 탭 C열(카테고리)에 해당 카테고리가 있는지 확인."""
    rows = await asyncio.to_thread(_read_sheet, service, '예산')
    target = (cat or '').strip()
    for row in rows[1:]:
        if len(row) > 2 and (row[2] or '').strip() == target:
            return True
    return False


async def handle_ledger_budget_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """신규 카테고리를 예산 탭에 추가할지 확인하는 버튼 처리."""
    q = update.callback_query
    if not q:
        return
    await q.answer()
    text = context.user_data.pop('pending_budget_text', '')
    cat = context.user_data.pop('pending_budget_cat', None)
    if (q.data or '') == 'ledgerbudget:skip':
        await q.edit_message_text(f"{text}\n\n⏭️ 예산 추가는 건너뛰었어요.")
        return
    if not cat:
        await q.edit_message_text("⌛ 만료된 요청이에요. 예산 탭에 직접 추가해주세요.")
        return
    service = _get_sheets_service()
    if not service:
        await q.edit_message_text("❌ Google 서비스 계정이 설정되지 않았습니다.")
        return
    try:
        rows = await asyncio.to_thread(_read_sheet, service, '예산')
        # 기존 예산 행의 날짜 재사용(예산 기준월 통일). 비었으면 오늘.
        date_val = (rows[1][0] if len(rows) > 1 and rows[1] and rows[1][0]
                    else datetime.datetime.now(KST).strftime('%Y-%m-%d'))
        await asyncio.to_thread(
            _append_row, service, '예산',
            [date_val, '지출', cat, '', '생활비'], 'RAW')
        logging.info(f"예산 신규 카테고리 추가: {cat}")
        await q.edit_message_text(
            f"{text}\n\n✅ '{cat}'을(를) 예산에 추가했어요. (월 금액은 예산 탭에서 직접 입력)")
    except Exception as e:
        logging.error(f"예산 추가 실패: {e}")
        await q.edit_message_text(f"❌ 예산 추가 실패: {e}")


async def _ledger_exclude(service, msg, date, merchant, amount):
    """거래내역에서 해당 행 삭제 (원본 ledger_data는 보존)."""
    rows = await asyncio.to_thread(_read_sheet, service, LEDGER_TX_SHEET)
    target = None
    for i, row in enumerate(rows):
        if i == 0:
            continue
        r_date = row[0] if len(row) > 0 else ''
        r_amt = _norm_amt(row[3]) if len(row) > 3 else ''
        r_mer = row[4] if len(row) > 4 else ''
        if r_date == date and r_mer == merchant and r_amt == amount:
            target = i
            break
    if target is None:
        await msg.reply_text("❌ 해당 내역을 거래내역에서 못 찾았습니다.\n(이미 제외됐거나 날짜/금액이 바뀐 것 같아요.)")
        return
    sheet_id = await asyncio.to_thread(_get_sheet_id, service, LEDGER_TX_SHEET)
    if sheet_id is None:
        await msg.reply_text("❌ 거래내역 시트를 찾을 수 없습니다.")
        return
    await asyncio.to_thread(_delete_sheet_row, service, sheet_id, target)
    try:
        amt_disp = f"{int(amount):,}원"
    except Exception:
        amt_disp = f"{amount}원"
    await msg.reply_text(
        f"🗑️ 가계부에서 제외됨\n"
        f"가맹점: {merchant}\n금액: {amt_disp}\n날짜: {date}\n"
        f"(원본은 ledger_data에 보존)"
    )
    logging.info(f"거래 제외: {date}|{merchant}|{amount}")


async def _ledger_move_to_seonyuduo(service, msg, date, merchant, amount):
    """시지프 거래내역에서 행을 찾아 선유듀오 가계부로 이동 (선유듀오에 추가 후 시지프에서 삭제)."""
    rows = await asyncio.to_thread(_read_sheet, service, LEDGER_TX_SHEET)
    target = None
    rowvals = None
    for i, row in enumerate(rows):
        if i == 0:
            continue
        r_date = row[0] if len(row) > 0 else ''
        r_amt = _norm_amt(row[3]) if len(row) > 3 else ''
        r_mer = row[4] if len(row) > 4 else ''
        if r_date == date and r_mer == merchant and r_amt == amount:
            target = i
            rowvals = row
            break
    if target is None:
        await msg.reply_text("❌ 해당 내역을 거래내역에서 못 찾았습니다.\n(이미 옮겼거나 날짜/금액이 바뀐 것 같아요.)")
        return
    # 옮길 행: [날짜, 유형, 카테고리, 금액(숫자), 메모] — 시지프 카테고리 그대로 이관, 통장(F)은 빈칸
    amt_raw = _norm_amt(rowvals[3]) if len(rowvals) > 3 else _norm_amt(amount)
    try:
        amt_val = int(amt_raw)
    except Exception:
        amt_val = amt_raw
    moved = [
        rowvals[0] if len(rowvals) > 0 else date,
        rowvals[1] if len(rowvals) > 1 else '지출',
        rowvals[2] if len(rowvals) > 2 else '',
        amt_val,
        rowvals[4] if len(rowvals) > 4 else merchant,
    ]
    # 1) 선유듀오 가계부 A~E의 다음 빈 행에 직접 기록 (append 컬럼 오배치 방지). 실패 시 시지프 행 보존
    sy_rows = await asyncio.to_thread(_read_range, service, SEONYUDUO_SHEET_ID, f"{SEONYUDUO_LEDGER_TAB}!A:E")
    sy_next = len(sy_rows) + 1
    await asyncio.to_thread(_update_range, service, SEONYUDUO_SHEET_ID, f"{SEONYUDUO_LEDGER_TAB}!A{sy_next}:E{sy_next}", [moved])
    # 2) 시지프 거래내역에서 삭제
    sheet_id = await asyncio.to_thread(_get_sheet_id, service, LEDGER_TX_SHEET)
    if sheet_id is None:
        await msg.reply_text("⚠️ 선유듀오 가계부엔 추가됐지만 시지프 삭제 실패(시트ID 못 찾음). 수동 확인 필요.")
        return
    await asyncio.to_thread(_delete_sheet_row, service, sheet_id, target)
    try:
        amt_disp = f"{int(amt_raw):,}원"
    except Exception:
        amt_disp = f"{amt_raw}원"
    await msg.reply_text(
        f"➡️ 선유듀오 가계부로 이동\n"
        f"가맹점: {moved[4]}\n금액: {amt_disp}\n카테고리: {moved[2] or '미분류'}\n날짜: {moved[0]}\n"
        f"(시지프 가계부에서는 제외됨)"
    )
    logging.info(f"선유듀오 이동: {date}|{merchant}|{amount}")
    # 부부 그룹챗(@SeonyuDuo_bot)에 지출 알림 (실패해도 이관 결과는 유지)
    try:
        await _notify_seonyuduo_spend(service, moved[4], moved[2], amt_val)
    except Exception as e:
        logging.warning(f"선유듀오 그룹 알림 실패(이관은 완료): {e}")


async def handle_uncat_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """가계부 알림에 답장 → 분류/수정(ledger_category) 또는 제외(거래내역 행 삭제)."""
    import re, html
    msg = update.message
    if not msg or not msg.reply_to_message:
        return
    orig = msg.reply_to_message.text or ''
    # 마커 텍스트 부분으로 인식 (이모지 변형/복사 깨짐에 안전, doPost가 보낸 알림도 매칭)
    if ('미분류 거래' not in orig) and ('가계부 등록' not in orig):
        return  # 우리 가계부 알림에 대한 답장이 아님
    reply = (msg.text or '').strip()
    m_mer = re.search(r'가맹점:\s*(.+)', orig)
    m_amt = re.search(r'금액:\s*(.+)', orig)
    m_date = re.search(r'날짜:\s*(.+)', orig)
    merchant = html.unescape(m_mer.group(1).strip()) if m_mer else ''
    amount = _norm_amt(m_amt.group(1)) if m_amt else ''
    date = html.unescape(m_date.group(1).strip()) if m_date else ''

    service = _get_sheets_service()
    if not service:
        await msg.reply_text("❌ Google 서비스 계정이 설정되지 않았습니다.")
        return

    if reply == '제외':
        try:
            await _ledger_exclude(service, msg, date, merchant, amount)
        except Exception as e:
            logging.error(f"거래 제외 실패: {e}")
            await msg.reply_text(f"❌ 제외 실패: {e}")
        return

    if reply in SEONYUDUO_MOVE_KEYWORDS:
        try:
            await _ledger_move_to_seonyuduo(service, msg, date, merchant, amount)
        except Exception as e:
            logging.error(f"선유듀오 이동 실패: {e}")
            await msg.reply_text(f"❌ 선유듀오 이동 실패: {e}")
        return

    if '=' in reply:
        kw, cat = [s.strip() for s in reply.split('=', 1)]
    else:
        kw, cat = '', reply
    if not cat:
        await msg.reply_text("형식: 카테고리만 보내거나 '키워드=카테고리' (예: 아식스=운동), 또는 '제외'")
        return
    try:
        await _ledger_upsert_rule(service, context, msg, merchant, kw, cat)
    except Exception as e:
        logging.error(f"ledger_category 처리 실패: {e}")
        await msg.reply_text(f"❌ 규칙 처리 실패: {e}")


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
    application.add_handler(CommandHandler('idea', idea_command))
    application.add_handler(MessageHandler(filters.REPLY & filters.TEXT & ~filters.COMMAND, handle_uncat_reply))
    application.add_handler(CallbackQueryHandler(handle_ledger_callback, pattern=r'^ledgercat:'))
    application.add_handler(CallbackQueryHandler(handle_ledger_budget_callback, pattern=r'^ledgerbudget:'))

    job_queue = application.job_queue
    try:
        import pytz
        kst = pytz.timezone('Asia/Seoul')
        weather_time = datetime.time(hour=5, minute=0, second=0, tzinfo=kst)
        calendar_time = datetime.time(hour=5, minute=5, second=0, tzinfo=kst)
        portfolio_time = datetime.time(hour=17, minute=0, second=0, tzinfo=kst)  # 16→17: KIS 확정 종가 확보 후 publish
        market_alert_time = datetime.time(hour=16, minute=5, second=0, tzinfo=kst)
        journal_time = datetime.time(hour=16, minute=10, second=0, tzinfo=kst)
        nightly_time = datetime.time(hour=16, minute=20, second=0, tzinfo=kst)
    except:
        weather_time = datetime.time(hour=5, minute=0, second=0)
        calendar_time = datetime.time(hour=5, minute=5, second=0)
        portfolio_time = datetime.time(hour=17, minute=0, second=0)  # 16→17: KIS 확정 종가 확보 후 publish
        market_alert_time = datetime.time(hour=16, minute=5, second=0)
        journal_time = datetime.time(hour=16, minute=10, second=0)
        nightly_time = datetime.time(hour=16, minute=20, second=0)

    # Featured 수집: 16:20 1차 (정규장 종가), 18:30 2차 (시간외 포함 최종), 08:30 3차 (익일 KRX 지연 복구)
    try:
        featured_1st_time = datetime.time(hour=16, minute=20, second=0, tzinfo=pytz.timezone('Asia/Seoul'))
        featured_2nd_time = datetime.time(hour=18, minute=30, second=0, tzinfo=pytz.timezone('Asia/Seoul'))
        featured_3rd_time = datetime.time(hour=8, minute=30, second=0, tzinfo=pytz.timezone('Asia/Seoul'))
    except:
        featured_1st_time = datetime.time(hour=16, minute=20, second=0)
        featured_2nd_time = datetime.time(hour=18, minute=30, second=0)
        featured_3rd_time = datetime.time(hour=8, minute=30, second=0)
    job_queue.run_daily(featured_update_job, time=featured_1st_time, job_kwargs=DAILY_JOB_KWARGS)
    job_queue.run_daily(featured_update_job, time=featured_2nd_time, job_kwargs=DAILY_JOB_KWARGS)
    job_queue.run_daily(morning_featured_recovery_job, time=featured_3rd_time, job_kwargs=DAILY_JOB_KWARGS)

    job_queue.run_daily(daily_weather_job, time=weather_time, job_kwargs=DAILY_JOB_KWARGS)
    job_queue.run_daily(daily_calendar_job, time=calendar_time, job_kwargs=DAILY_JOB_KWARGS)
    job_queue.run_daily(daily_portfolio_job, time=portfolio_time, job_kwargs=DAILY_JOB_KWARGS)
    job_queue.run_daily(daily_market_alert_job, time=market_alert_time, job_kwargs=DAILY_JOB_KWARGS)
    job_queue.run_daily(daily_journal_job, time=journal_time, job_kwargs=DAILY_JOB_KWARGS)
    # ETF 수집(16:30)은 systemd 타이머 etf-collect.timer로 이관 (봇 재시작에 무관)
    job_queue.run_daily(nightly_portfolio_refresh_job, time=nightly_time, job_kwargs=DAILY_JOB_KWARGS)

    # 20:00 백업 (16:xx에서 데이터 못 가져온 경우 재시도)
    try:
        backup_time = datetime.time(hour=20, minute=0, second=0, tzinfo=pytz.timezone('Asia/Seoul'))
    except:
        backup_time = datetime.time(hour=20, minute=0, second=0)
    job_queue.run_daily(evening_backup_job, time=backup_time, job_kwargs=DAILY_JOB_KWARGS)

    # 23:00 투자유의종목 야간 업데이트
    try:
        late_alert_time = datetime.time(hour=23, minute=0, second=0, tzinfo=pytz.timezone('Asia/Seoul'))
    except:
        late_alert_time = datetime.time(hour=23, minute=0, second=0)
    job_queue.run_daily(late_market_alert_job, time=late_alert_time, job_kwargs=DAILY_JOB_KWARGS)

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

    # 가계부 거래 알림은 이제 Apps Script doPost가 행 적재 직후 직접 텔레그램으로 전송 (이벤트 드리븐).
    # 봇은 답장(분류/수정/제외)·버튼만 처리. 폴러는 fallback용으로 코드만 유지(비활성).
    # job_queue.run_repeating(check_uncategorized_job, interval=90, first=20)

    print(f"Bot started at {datetime.datetime.now()}")
    print(f"✅ Daily jobs scheduled:")
    print(f"  - Featured data: 06:00 KST (전일 데이터, 익일 수집)")
    print(f"  - Weather: 05:00 KST")
    print(f"  - Calendar: 05:05 KST")
    print(f"  - Portfolio report: 16:00 KST")
    print(f"  - Market alert: 16:05 KST (투자유의종목)")
    print(f"  - Journal data: 16:10 KST (투자일지)")
    print(f"  - Auto portfolio update: 09:30~15:35 KST (30분 간격, 거래일만)")
    print(f"  - Nightly portfolio refresh: 16:20 KST (당일 주문 반영)")
    print(f"  - ETF collection: systemd 타이머 etf-collect.timer (16:30 KST, 봇 분리)")
    print(f"  - Evening backup: 20:00 KST (16:xx 실패 시 재시도)")
    print(f"  - Late market alert: 23:00 KST (투자유의종목 야간 업데이트)")
    application.run_polling()
