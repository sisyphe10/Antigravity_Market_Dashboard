"""
RA_Sisyphe — 리서치/뉴스 알림 텔레그램 봇.

Jobs:
  - 05:10 KST: Research Notes 헤드라인
  - 05:15 KST: 투자유의종목 일일 요약
  - 07:00~17:00 KST (매시): WiseReport 신규 리서치 리포트
  - 18:00 KST: KNA 세계원전시장동향 신규 게시글

별도 SUBSCRIBERS (subscribers_ra_sisyphe.json), 별도 락 파일.
환경변수: TELEGRAM_RA_SISYPHE_BOT_TOKEN
"""
import logging
import datetime
import os
import sys
import json
import fcntl
import html as _html

# 중복 실행 방지 (파일 락)
_lock_file = open('/tmp/ra_sisyphe_bot.lock', 'w')
try:
    fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    _lock_file.write(str(os.getpid()))
    _lock_file.flush()
except IOError:
    print("ERROR: ra_sisyphe_bot is already running. Exiting.")
    sys.exit(1)

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from dotenv import load_dotenv

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)
# 텔레그램 polling getUpdates 로그 제거 (10초마다 INFO → 디스크/journal 점거)
logging.getLogger("httpx").setLevel(logging.WARNING)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_RA_SISYPHE_BOT_TOKEN")

DASHBOARD_DIR = os.path.join(os.path.expanduser('~'), 'Antigravity_Market_Dashboard')
SUBSCRIBERS_FILE = os.path.join(DASHBOARD_DIR, 'subscribers_ra_sisyphe.json')
KST = datetime.timezone(datetime.timedelta(hours=9))


def load_subscribers():
    try:
        with open(SUBSCRIBERS_FILE, 'r') as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_subscribers():
    with open(SUBSCRIBERS_FILE, 'w') as f:
        json.dump(list(SUBSCRIBERS), f)


SUBSCRIBERS = load_subscribers()


# ============================================================
# 핸들러
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    SUBSCRIBERS.add(user_id)
    save_subscribers()
    await context.bot.send_message(
        chat_id=user_id,
        text=(
            "🔬 RA_Sisyphe (리서치 알림) 구독되었습니다.\n\n"
            "매일 일정:\n"
            "- 05:10 Research Notes 헤드라인\n"
            "- 05:15 투자유의종목 현황\n"
            "- 07:00~17:00 (시간당) WiseReport 리포트\n"
            "- 18:00 KNA 세계원전시장동향"
        ),
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if user_id in SUBSCRIBERS:
        SUBSCRIBERS.remove(user_id)
        save_subscribers()
        await context.bot.send_message(chat_id=user_id, text="구독 취소되었습니다.")
    else:
        await context.bot.send_message(chat_id=user_id, text="구독 중이 아닙니다.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "🔬 RA_Sisyphe (리서치 알림 봇)\n\n"
            "/start - 구독\n"
            "/stop - 구독 취소\n"
            "/help - 도움말"
        ),
    )


# ============================================================
# Research Notes 헤드라인 (매일 05:10)
# ============================================================
async def daily_headlines_job(context: ContextTypes.DEFAULT_TYPE):
    """매일 05:10 리서치 헤드라인 알림 (당일/전일 데이터만 전송)"""
    logging.info("Daily headlines job started")
    try:
        headlines_file = os.path.join(DASHBOARD_DIR, 'research_headlines.json')
        if not os.path.exists(headlines_file):
            return
        with open(headlines_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        headlines = data.get('headlines', [])
        date = data.get('date', '')

        today_kst = datetime.datetime.now(tz=KST).date()
        yesterday_kst = today_kst - datetime.timedelta(days=1)
        try:
            headline_date = datetime.datetime.strptime(date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            headline_date = None
        if headline_date and headline_date < yesterday_kst:
            logging.info(f"Research headlines 스킵: 오래된 데이터 ({date})")
            return

        if not headlines:
            return

        important = [h for h in headlines if isinstance(h, dict) and h.get('important')]
        normal = [h for h in headlines if not (isinstance(h, dict) and h.get('important'))]
        sorted_headlines = important + normal

        msg = f"📋 <b>Research Notes ({date})</b>\n\n"
        for i, h in enumerate(sorted_headlines):
            title = h.get('title', '') if isinstance(h, dict) else h
            summary = h.get('summary', '') if isinstance(h, dict) else ''
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


# ============================================================
# WiseReport 리서치 리포트 알림 (07:00~17:00 매시)
# ============================================================
_WISEREPORT_SENT_FILE = os.path.join(DASHBOARD_DIR, '.wisereport_sent.json')


def _load_wisereport_sent():
    today_str = datetime.datetime.now(KST).strftime('%Y-%m-%d')
    try:
        with open(_WISEREPORT_SENT_FILE, 'r') as f:
            data = json.load(f)
        if data.get('date') == today_str:
            return set(tuple(x) for x in data.get('sent', [])), today_str
    except Exception:
        pass
    return set(), today_str


def _save_wisereport_sent(sent_set, date_str):
    try:
        with open(_WISEREPORT_SENT_FILE, 'w') as f:
            json.dump({'date': date_str, 'sent': list(sent_set)}, f)
    except Exception:
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
    now_str = datetime.datetime.now(KST).strftime('%Y-%m-%d %H:%M')
    header = f"📋 <b>리서치 리포트</b> ({now_str})"
    if is_update:
        header = f"📋 <b>리서치 리포트 추가</b> ({now_str})"

    lines = [header, '']

    if company_data:
        lines.append('<b>━━ 기업 ━━</b>')
        groups = {}
        for r in company_data:
            nm = r['name'].split('(')[0].strip()
            groups.setdefault(nm, []).append(r)

        for nm in sorted(groups.keys()):
            for r in groups[nm]:
                op = r['opinion'] or '-'
                tgt = r['target'] or '-'
                analyst = r['analyst'].replace('[', '').replace(']', '')
                parts = analyst.split()
                firm = parts[0][:2] if parts else '-'
                person = ' '.join(parts[1:]) if len(parts) > 1 else ''
                analyst_short = f"{firm} {person}" if person else firm
                close = r.get('close', '') or '-'
                try:
                    c_val = int(close.replace(',', ''))
                    t_val = int(tgt.replace(',', ''))
                    pct = round((t_val - c_val) / c_val * 100)
                    pct_str = f" ({pct:+d}%)"
                except Exception:
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
            groups.setdefault(r['name'], []).append(r)

        for nm in sorted(groups.keys()):
            for r in groups[nm]:
                prev = r.get('prev_opinion', '') or ''
                curr = r.get('opinion', '') or ''
                analyst = r['analyst'].replace('[', '').replace(']', '')
                opinion_str = f"{prev} → {curr}" if prev and curr and prev != curr else (curr or prev or '-')
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


async def wisereport_job(context: ContextTypes.DEFAULT_TYPE):
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
            except Exception:
                pass
        return

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
# KNA 세계원전시장동향 (매일 18:00)
# ============================================================
async def daily_kna_news_job(context: ContextTypes.DEFAULT_TYPE):
    """매일 18:00 KNA 세계원전시장동향 신규 게시글 알림"""
    logging.info("Daily KNA news job started")
    try:
        sys.path.insert(0, os.path.join(DASHBOARD_DIR, 'execution'))
        from fetch_kna_news import fetch_new_posts
        posts = fetch_new_posts(update_state=True)
        if not posts:
            logging.info("KNA: 신규 글 없음")
            return
        for p in posts:
            header = (
                f"📰 <b>[KNA] {_html.escape(p['title'])}</b>\n"
                f"{p['date']} · #{p['display_no']}\n"
                f"{p['url']}\n\n"
            )
            # 본문 escape + '□' 로 시작하는 소제목은 볼드+밑줄
            body_lines = []
            for ln in p.get('body', '').split('\n'):
                escaped = _html.escape(ln)
                if ln.lstrip().startswith('□'):
                    body_lines.append(f'<b><u>{escaped}</u></b>')
                else:
                    body_lines.append(escaped)
            body = '\n'.join(body_lines)
            full = header + body
            for chat_id in SUBSCRIBERS:
                try:
                    for i in range(0, len(full), 4000):
                        await context.bot.send_message(
                            chat_id=chat_id, text=full[i:i + 4000], parse_mode='HTML',
                            disable_web_page_preview=True,
                        )
                except Exception as e:
                    logging.error(f"KNA news 전송 실패 (num={p.get('num')}): {e}")
        logging.info(f"KNA news sent: {len(posts)}건")
    except Exception as e:
        logging.error(f"KNA news job failed: {e}")


# ============================================================
# 투자유의종목 일일 요약 (매일 05:15)
# ============================================================
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
        sys.path.insert(0, os.path.join(DASHBOARD_DIR, 'execution'))
        from create_market_alert import (
            get_session, fetch_category, parse_stocks, load_krx_data,
            fmt_marcap
        )
        esc = _html.escape

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

        def fmt_line(s):
            name = esc(s['name'])
            mcap = esc(fmt_marcap(s['marcap']))
            line = f"• {name} / {mcap}"
            if s.get('warn_type') == '투자경고 지정예고':
                line = f"<u>{line}</u>"
            return line

        def render_category(stocks, prev_set, header):
            if not stocks:
                return []
            sorted_stocks = sorted(stocks, key=lambda x: (x.get('marcap') or 0), reverse=True)
            new_stocks = [s for s in sorted_stocks if s['name'] not in prev_set]
            existing_stocks = [s for s in sorted_stocks if s['name'] in prev_set]
            out = ["", f"<b><u>[{header}]</u></b>"]
            if new_stocks:
                out.append("(신규)")
                for s in new_stocks:
                    out.append(fmt_line(s))
                if existing_stocks:
                    out.append("----")
            for s in existing_stocks:
                out.append(fmt_line(s))
            return out

        lines = [f"<b><u>투자유의종목 현황</u></b> ({today})"]
        lines.extend(render_category(stocks_위험, prev_위험, '투자위험'))
        lines.extend(render_category(stocks_경고, prev_경고, '투자경고'))
        lines.extend(render_category(stocks_주의, prev_주의, '투자주의'))

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


# ============================================================
# main
# ============================================================
if __name__ == "__main__":
    if not TOKEN:
        print("Error: TELEGRAM_RA_SISYPHE_BOT_TOKEN environment variable is missing.")
        sys.exit(1)

    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('stop', stop))
    application.add_handler(CommandHandler('help', help_command))

    job_queue = application.job_queue
    import pytz
    kst = pytz.timezone('Asia/Seoul')

    job_queue.run_daily(
        daily_headlines_job,
        time=datetime.time(hour=5, minute=10, second=0, tzinfo=kst),
    )

    job_queue.run_daily(
        daily_market_alert_summary_job,
        time=datetime.time(hour=5, minute=15, second=0, tzinfo=kst),
    )

    for h in range(7, 18):
        job_queue.run_daily(
            wisereport_job,
            time=datetime.time(hour=h, minute=0, second=0, tzinfo=kst),
        )

    job_queue.run_daily(
        daily_kna_news_job,
        time=datetime.time(hour=18, minute=0, second=0, tzinfo=kst),
    )

    print(f"Research Alerts Bot started at {datetime.datetime.now()}")
    print("✅ Daily jobs scheduled:")
    print("  - Research Notes headlines: 05:10 KST")
    print("  - Market alert summary: 05:15 KST (투자유의종목 현황)")
    print("  - WiseReport: 07:00~17:00 KST (hourly)")
    print("  - KNA news: 18:00 KST")

    application.run_polling()
