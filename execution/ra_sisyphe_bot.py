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
# Generic Source Pipeline (sources.json 기반)
# ============================================================
# sources.json 의 enabled=true 항목을 부팅 시 자동 등록.
# 각 사이트의 어댑터는 execution/sources/<name>.py (fetch_new_posts/commit_state/format_message).
sys.path.insert(0, os.path.join(DASHBOARD_DIR, 'execution'))


def _load_source_config(source_name: str) -> dict:
    """sources.json 에서 특정 source entry 가져오기 (없으면 빈 dict)."""
    from sources import load_sources_config
    for s in load_sources_config():
        if s.get('name') == source_name:
            return s
    return {}


async def _maybe_warn_staleness(context, adapter, cfg, source_name, label, icon):
    """피드 최신 글이 staleness_days 보다 오래되면 1일 1회 경보 발송.

    어댑터가 latest_item_date() 를 노출하고 sources.json 에 staleness_days 가
    설정된 소스만 점검. 어떤 예외도 밖으로 던지지 않는다 (본 수집 작업 보호).
    """
    try:
        threshold = int(cfg.get('staleness_days') or 0)
        if threshold <= 0:
            return
        get_date = getattr(adapter, 'latest_item_date', None)
        if not callable(get_date):
            return
        latest = get_date()
        from sources.base import check_and_record_staleness
        today_iso = datetime.datetime.now(KST).strftime('%Y-%m-%d')
        warn = check_and_record_staleness(source_name, latest, threshold, today_iso)
        if not warn:
            return
        msg = f"⚠️ <b>[{label}] {icon} 피드 staleness 경보</b>\n{_html.escape(warn)}"
        for chat_id in SUBSCRIBERS:
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
            except Exception as e:
                logging.error(f"{source_name} staleness notify 전송 실패: {e}")
        logging.warning(f"{source_name} staleness 경보: {warn}")
    except Exception as e:
        logging.error(f"{source_name} staleness 점검 오류 (무시): {e}")


async def _run_source_job(
    context: ContextTypes.DEFAULT_TYPE,
    source_name: str,
    retry_count: int = 0,
):
    """소스 1건 본 로직. fetch → format → 발송 → commit_state.

    retry_count=0=정기, 1+=재시도. retry 정책은 sources.json 의 retry.count / interval_min.
    """
    cfg = _load_source_config(source_name)
    if not cfg:
        logging.warning(f"source '{source_name}' not in sources.json — skipping")
        return

    label = cfg.get('label', source_name)
    icon = cfg.get('icon', '📰')
    retry_cfg = cfg.get('retry') or {}
    max_retries = int(retry_cfg.get('count', 2))
    retry_interval_min = int(retry_cfg.get('interval_min', 30))

    now_str = datetime.datetime.now(KST).strftime('%Y-%m-%d %H:%M')
    retry_prefix = f"🔁 재시도 {retry_count}/{max_retries} " if retry_count > 0 else ""

    try:
        from sources import load_adapter
        adapter = load_adapter(source_name)

        # 피드 staleness 사전 점검 — 신규 글이 0건이어도 피드 자체가 죽었는지 감지.
        # 완전 방어적: 절대 본 작업을 깨지 않음 (내부에서 모든 예외 흡수).
        await _maybe_warn_staleness(context, adapter, cfg, source_name, label, icon)

        try:
            posts = adapter.fetch_new_posts(update_state=False)
        except Exception as fetch_err:
            raise RuntimeError(
                f"사이트 접속/파싱 실패 — {type(fetch_err).__name__}: {fetch_err}"
            ) from fetch_err

        if not posts:
            # 신규 글이 없으면 알림을 보내지 않는다 (조용히 종료).
            # "신규 글 없음" 스팸 방지 — 피드가 죽어 0건만 반복되는 경우는
            # 위의 _maybe_warn_staleness 가 별도로 경보하므로 침묵해도 안전.
            logging.info(f"{source_name}: 신규 글 없음 (알림 미발송)")
            return

        from sources.base import split_for_telegram, sanitize_telegram_html, html_to_plain
        send_errors = []
        for p in posts:
            # 발송 직전 1회 안전화 — 본문 속 stray '<...>' 꺾쇠가 잘못된 태그로
            # 파싱돼 메시지 전체 전송이 실패하는 사고 방지 (모든 소스 공통).
            full = sanitize_telegram_html(adapter.format_message(p, label, icon))
            for chat_id in SUBSCRIBERS:
                try:
                    for chunk in split_for_telegram(full, 4000):
                        try:
                            await context.bot.send_message(
                                chat_id=chat_id, text=chunk, parse_mode='HTML',
                                disable_web_page_preview=True,
                            )
                        except Exception as parse_err:
                            # HTML 파싱 실패 시 평문으로 폴백 — job 자체는 성공시켜
                            # 재시도/restart/SIGKILL/OnFailure 연쇄를 차단.
                            if 'parse' not in str(parse_err).lower():
                                raise
                            logging.warning(
                                f"{source_name} HTML 파싱 실패 → 평문 폴백 "
                                f"(id={p.get('id')}): {parse_err}"
                            )
                            await context.bot.send_message(
                                chat_id=chat_id, text=html_to_plain(chunk),
                                disable_web_page_preview=True,
                            )
                except Exception as e:
                    send_errors.append(f"id={p.get('id')} chat={chat_id}: {e}")
                    logging.error(f"{source_name} 전송 실패 (id={p.get('id')}): {e}")

        if send_errors:
            raise RuntimeError(
                f"텔레그램 전송 실패 {len(send_errors)}건 — 첫 오류: {send_errors[0]}"
            )

        adapter.commit_state(posts)
        logging.info(f"{source_name} sent: {len(posts)}건, state committed")

    except Exception as e:
        logging.error(f"{source_name} job failed (retry={retry_count}): {e}")
        will_retry = retry_count < max_retries
        retry_note = (
            f"\n\n{retry_interval_min}분 뒤 자동 재시도 (시도 {retry_count + 1}/{max_retries})"
            if will_retry else
            "\n\n재시도 한도 초과. 수동 점검 필요."
        )
        err_msg = (
            f"⚠️ <b>[{label}] {retry_prefix}수집/전송 오류</b>\n"
            f"{now_str}\n\n"
            f"{_html.escape(str(e))}"
            f"{retry_note}"
        )
        for chat_id in SUBSCRIBERS:
            try:
                await context.bot.send_message(chat_id=chat_id, text=err_msg, parse_mode='HTML')
            except Exception as send_err:
                logging.error(f"{source_name} error notify 전송 실패: {send_err}")

        if will_retry:
            context.job_queue.run_once(
                _source_retry_job,
                when=retry_interval_min * 60,
                data={'source_name': source_name, 'retry_count': retry_count + 1},
                name=f'{source_name}_retry',
            )


def _make_source_job(source_name: str):
    """closure 로 source_name 바인딩한 정기 잡 생성."""
    async def _job(context: ContextTypes.DEFAULT_TYPE):
        logging.info(f"Source job started: {source_name}")
        await _run_source_job(context, source_name, retry_count=0)
    _job.__name__ = f'source_job_{source_name}'
    return _job


async def _source_retry_job(context: ContextTypes.DEFAULT_TYPE):
    """run_once 로 호출되는 재시도 잡 (모든 source 공용)."""
    source_name = 'unknown'
    retry_count = 1
    if context.job and context.job.data:
        source_name = context.job.data.get('source_name', 'unknown')
        retry_count = context.job.data.get('retry_count', 1)
    logging.info(f"Source retry job started: {source_name} (retry={retry_count})")
    await _run_source_job(context, source_name, retry_count=retry_count)


# ============================================================
# 해외 IR 수집 사각지대 주간 점검 (월요일 09:10 KST)
# ============================================================
# foreign_ir 은 회사별 fetch 실패를 개별 텔레그램 오류로 보내지 않는다
# (실패율 60% 미만이면 systemic 경보 안 뜸 → 12~14개사가 조용히 죽어도 모름).
# 주 1회 foreign_ir_health 상태를 읽어 '오래 성공 못한' 회사를 1건으로 모아 알린다.
FOREIGN_IR_DEAD_DAYS = 3   # 최근 성공이 N일 이상 전이면 '사각지대'로 본다


async def foreign_ir_health_job(context: ContextTypes.DEFAULT_TYPE):
    """월요일 1회 해외 IR 수집 사각지대 요약. 사각지대 없으면 조용히 종료."""
    now = datetime.datetime.now(KST)
    if now.weekday() != 0:   # 0=월요일만 실제 발송
        return
    try:
        from sources.base import load_state, split_for_telegram
        comps = (load_state('foreign_ir_health').get('companies') or {})
        if not comps:
            logging.info("foreign_ir health: 데이터 없음 — 점검 skip")
            return
        today = now.date()
        dead = []
        for tk, h in comps.items():
            streak = int(h.get('fail_streak') or 0)
            if streak <= 0:
                continue   # 최근 실행 성공 → 정상
            last_ok = h.get('last_ok')
            age = None
            if last_ok:
                try:
                    age = (today - datetime.date.fromisoformat(last_ok)).days
                except Exception:
                    age = None
            if last_ok is None or (age is not None and age >= FOREIGN_IR_DEAD_DAYS):
                dead.append((tk, h.get('name') or tk, last_ok, streak, h.get('last_error') or ''))
        if not dead:
            logging.info("foreign_ir health: 사각지대 없음 — 알림 미발송")
            return
        dead.sort(key=lambda x: (x[2] or '', -x[3]))   # 마지막 성공 오래된 순 → 연속실패 많은 순
        lines = [
            "🩺 <b>[해외 기업 뉴스룸] 수집 사각지대 점검</b>",
            f"{now.strftime('%Y-%m-%d')} · {len(dead)}개사 {FOREIGN_IR_DEAD_DAYS}일+ 신규 미수집\n",
        ]
        for tk, name, last_ok, streak, err in dead:
            since = f"마지막 성공 {last_ok}" if last_ok else "추적 후 성공 없음"
            lines.append(f"• <b>{_html.escape(str(name))}</b> ({_html.escape(str(tk))}) — {since}, 연속실패 {streak}회")
            if err:
                lines.append(f"   ↳ {_html.escape(str(err)[:120])}")
        msg = '\n'.join(lines)
        for chat_id in SUBSCRIBERS:
            try:
                for chunk in split_for_telegram(msg, 4000):
                    await context.bot.send_message(
                        chat_id=chat_id, text=chunk, parse_mode='HTML',
                        disable_web_page_preview=True,
                    )
            except Exception as e:
                logging.error(f"foreign_ir health notify 전송 실패: {e}")
        logging.info(f"foreign_ir health: 사각지대 {len(dead)}개사 알림 발송")
    except Exception as e:
        logging.error(f"foreign_ir health job failed (무시): {e}")


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
# 20일 신고가 (매일 16:00) — KIS featured 배치 산출물(newhigh_20d.json) 사용
# ============================================================
_NEWHIGH_FILE = os.path.join(DASHBOARD_DIR, 'newhigh_20d.json')


def render_newhigh_message(data, today):
    """
    newhigh_20d.json data → HTML 메시지 (섹터 > 테마 > 종목). 잡/테스트 공용.
    레이아웃: 섹터 •(볼드+밑줄) / 테마 ◦(1단 들여쓰기, 볼드) / 종목 -(2단 들여쓰기).
    들여쓰기는 점자공백 U+2800 — 텔레그램이 일반/nbsp 연속공백을 합치므로.
    테마 미부여(theme 없음) 종목은 섹터 바로 아래(1단)에 나열.
    """
    esc = _html.escape
    NB = "⠀"          # 점자공백(빈 글자) — 들여쓰기 1칸
    I1, I2 = NB * 2, NB * 4
    stocks = data.get('stocks', [])
    total = len(stocks)

    def fmt_cap(won):
        jo = (won or 0) / 1e12
        if jo >= 10:
            return f"{jo:,.0f}조"
        if jo >= 1:
            return f"{jo:,.1f}조"
        return f"{(won or 0)/1e8:,.0f}억"

    def stock_line(s, indent):
        sign = '+' if s.get('chg', 0) >= 0 else ''
        badge = ' | 🔥' if s.get('is_52w') else ''
        return f"{indent}- {esc(s['name'])} | {fmt_cap(s.get('mktcap'))} | {sign}{s.get('chg', 0)}%{badge}"

    if total == 0:
        return f"{today}\n<b><u>20일 신고가</u></b> (0종목)\n\n오늘 신고가 종목 없음"

    n52 = sum(1 for s in stocks if s.get('is_52w'))

    # 섹터 > 종목 (테마 계층 일단 제외 — theme 데이터는 enrich가 계속 부여, 렌더만 생략)
    sectors = {}
    for s in stocks:
        sectors.setdefault(s.get('sector') or '기타', []).append(s)
    sec_order = sorted(sectors, key=lambda k: -len(sectors[k]))

    head = f"<b><u>20일 신고가</u></b> ({total}종목)"
    if n52:
        head += f" / <b><u>52주 신고가</u></b>({n52}종목🔥)"
    lines = [today, head, ""]
    for sec in sec_order:
        rows = sorted(sectors[sec], key=lambda x: -x.get('mktcap', 0))
        lines.append(f"• <b><u>{esc(sec)}_({len(rows)})</u></b>")
        for s in rows:
            lines.append(stock_line(s, I1))
        lines.append("")

    # (테마 블록은 일단 제거 — enrich가 theme/theme_descriptions는 계속 생성하므로 복원 용이)
    return "\n".join(lines).rstrip()


async def daily_newhigh_job(context: ContextTypes.DEFAULT_TYPE):
    """매일 16:00 20일 신고가 리스트 알림 (fetch_featured_data_kis.py가 먼저 생성)."""
    logging.info("Newhigh 20d job started")
    try:
        with open(_NEWHIGH_FILE, encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        logging.warning("newhigh_20d.json 없음 → 신고가 알림 건너뜀")
        return
    except Exception as e:
        logging.error(f"Newhigh load failed: {e}")
        return

    today = datetime.datetime.now(tz=KST).strftime('%Y-%m-%d')
    if data.get('date') != today:
        logging.warning(f"Newhigh 데이터 날짜 불일치(date={data.get('date')} != {today}) → 건너뜀")
        return

    msg = render_newhigh_message(data, today)
    total = len(data.get('stocks', []))
    sent = 0
    for chat_id in SUBSCRIBERS:
        try:
            for i in range(0, len(msg), 4000):
                await context.bot.send_message(chat_id=chat_id, text=msg[i:i+4000], parse_mode='HTML')
            sent += 1
        except Exception as e:
            logging.error(f"Newhigh send failed ({chat_id}): {e}")
    logging.info(f"Newhigh 20d sent: {total}종목 → {sent}명")


# ============================================================
# 공시 알림 (매일 16:40) — daily_disclosures.yml(16:30 KST 수집) 산출물(disclosures.json) 사용
# ============================================================
import urllib.request

_DISCLOSURES_FILE = os.path.join(DASHBOARD_DIR, 'disclosures.json')
_DISCLOSURES_RAW_URL = (
    'https://raw.githubusercontent.com/sisyphe10/Antigravity_Market_Dashboard/main/disclosures.json'
)


def _fetch_disclosures_data():
    """16:30 GHA 커밋분을 VM pull 없이 반영하기 위해 GitHub raw에서 우선 조회.
    실패 시 로컬 disclosures.json 폴백. 동기 호출(다른 잡과 동일 패턴)."""
    try:
        req = urllib.request.Request(
            _DISCLOSURES_RAW_URL,
            headers={'User-Agent': 'ra-sisyphe-bot', 'Cache-Control': 'no-cache'},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        logging.warning(f"Disclosures raw fetch 실패 → 로컬 폴백: {e}")
        try:
            with open(_DISCLOSURES_FILE, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e2:
            logging.error(f"Disclosures 로컬 로드도 실패: {e2}")
            return None


def render_disclosures_message(items, today):
    """오늘(today) 공시 항목들 → HTML 메시지 (종목별 그룹).
    레이아웃: 종목 •(볼드+밑줄) / 공시 -(1단 들여쓰기, 제목 링크 + 출처배지).
    들여쓰기는 점자공백 U+2800 — 텔레그램이 일반/nbsp 연속공백을 합치므로.
    source 누락 항목은 DART로 취급(fetch_kind_disclosures.py 스키마 주석 기준)."""
    esc = _html.escape
    NB = "⠀"          # 점자공백(빈 글자) — 들여쓰기 1칸
    I1 = NB * 2

    total = len(items)
    if total == 0:
        return f"{today}\n<b><u>오늘 공시</u></b> (0건)\n\n오늘 공시 없음"

    # 종목명별 그룹 (종목 내 항목 수 많은 순 → 종목명 가나다 보조정렬)
    groups = {}
    for it in items:
        groups.setdefault(it.get('name') or '기타', []).append(it)
    grp_order = sorted(groups, key=lambda k: (-len(groups[k]), k))

    head = f"<b><u>오늘 공시</u></b> ({total}건)"
    lines = [today, head, ""]
    for name in grp_order:
        rows = groups[name]
        lines.append(f"• <b><u>{esc(name)}_({len(rows)})</u></b>")
        for it in rows:
            src = (it.get('source') or 'DART').upper()
            badge = '🟦KIND' if src == 'KIND' else '🟧DART'
            title = esc(it.get('title') or '(제목없음)')
            url = it.get('url')
            title_html = f'<a href="{esc(url)}">{title}</a>' if url else title
            lines.append(f"{I1}- {title_html} | {badge}")
        lines.append("")

    return "\n".join(lines).rstrip()


async def daily_disclosures_job(context: ContextTypes.DEFAULT_TYPE):
    """매일 16:40 당일 공시 알림 (daily_disclosures.yml가 16:30 KST에 수집·커밋)."""
    logging.info("Disclosures job started")
    data = _fetch_disclosures_data()
    if not data:
        logging.warning("disclosures.json 로드 실패 → 공시 알림 건너뜀")
        return

    items = data.get('items', []) if isinstance(data, dict) else (data or [])
    today = datetime.datetime.now(tz=KST).strftime('%Y-%m-%d')
    today_items = [it for it in items if it.get('date') == today]

    if not today_items:
        logging.info(f"오늘({today}) 공시 0건 → 알림 건너뜀")
        return

    msg = render_disclosures_message(today_items, today)
    sent = 0
    for chat_id in SUBSCRIBERS:
        try:
            for i in range(0, len(msg), 4000):
                await context.bot.send_message(
                    chat_id=chat_id, text=msg[i:i+4000],
                    parse_mode='HTML', disable_web_page_preview=True,
                )
            sent += 1
        except Exception as e:
            logging.error(f"Disclosures send failed ({chat_id}): {e}")
    logging.info(f"Disclosures sent: {len(today_items)}건 → {sent}명")


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

    # 20일 신고가 (장 마감 후 16:00 — fetch_featured_data_kis.py 산출물 사용)
    job_queue.run_daily(
        daily_newhigh_job,
        time=datetime.time(hour=16, minute=0, second=0, tzinfo=kst),
    )

    # 당일 공시 알림 (16:40 — daily_disclosures.yml가 16:30 KST 수집·커밋 후, GitHub raw 조회)
    job_queue.run_daily(
        daily_disclosures_job,
        time=datetime.time(hour=16, minute=40, second=0, tzinfo=kst),
    )

    for h in range(7, 18):
        job_queue.run_daily(
            wisereport_job,
            time=datetime.time(hour=h, minute=0, second=0, tzinfo=kst),
        )

    # ── sources.json 기반 동적 등록 ───────────────────────────────
    from sources import load_sources_config
    source_schedule_log: list[str] = []
    for src in load_sources_config():
        src_name = src.get('name')
        if not src_name:
            continue
        schedule = src.get('schedule') or []
        if isinstance(schedule, str):
            schedule = [schedule]
        if not schedule:
            logging.warning(f"source '{src_name}' has no schedule — skipping")
            continue
        job_fn = _make_source_job(src_name)
        for hhmm in schedule:
            try:
                h_str, m_str = hhmm.split(':')
                hh = int(h_str)
                mm = int(m_str)
            except Exception:
                logging.error(f"source '{src_name}' bad schedule entry: {hhmm}")
                continue
            job_queue.run_daily(
                job_fn,
                time=datetime.time(hour=hh, minute=mm, second=0, tzinfo=kst),
            )
            source_schedule_log.append(f"  - {src.get('label', src_name)} ({src_name}): {hhmm} KST")

    # 해외 IR 수집 사각지대 주간 점검 (잡은 매일 등록되나 월요일에만 실제 발송)
    job_queue.run_daily(
        foreign_ir_health_job,
        time=datetime.time(hour=9, minute=10, second=0, tzinfo=kst),
    )

    print(f"Research Alerts Bot started at {datetime.datetime.now()}")
    print("✅ Daily jobs scheduled:")
    print("  - Research Notes headlines: 05:10 KST")
    print("  - Market alert summary: 05:15 KST (투자유의종목 현황)")
    print("  - 20일 신고가: 16:00 KST (newhigh_20d.json)")
    print("  - WiseReport: 07:00~17:00 KST (hourly)")
    print("  - 해외 IR 사각지대 점검: 월요일 09:10 KST")
    for line in source_schedule_log:
        print(line)

    application.run_polling()
