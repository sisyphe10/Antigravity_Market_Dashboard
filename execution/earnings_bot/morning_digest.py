"""아침 다이제스트 — 어제 신규 발표 + 미해결 transcript 큐 + 다음 7일 예정.

ra-sisyphe-bot 채널로 발송 (TELEGRAM_RA_SISYPHE_BOT_TOKEN + subscribers_ra_sisyphe.json).
runner.py 마지막 단계에서 호출 — 매 사이클(08:00 KST) 작업 끝에 한 번 발송.

EARNINGS_BOT_DRY_RUN=1: 메시지 빌드만 하고 텔레그램 발송 스킵.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
DASHBOARD_DIR = Path(__file__).resolve().parents[2]
SUBSCRIBERS_FILE = DASHBOARD_DIR / 'subscribers_ra_sisyphe.json'

LOOKBACK_HOURS = 24
LOOKAHEAD_DAYS = 7
STALE_DAYS = 7  # 7일 이상 미해결 → [stale] 마킹
TG_MAX = 4000   # Telegram 4096자 한도 - 여유


# ─── subscribers 로딩 (ra_sisyphe_bot.load_subscribers와 동일 형식) ───
def _load_subscribers() -> list[int]:
    try:
        with SUBSCRIBERS_FILE.open() as f:
            data = json.load(f)
        return [int(x) for x in data]
    except FileNotFoundError:
        logger.warning(f'subscribers 파일 없음: {SUBSCRIBERS_FILE}')
        return []
    except Exception as e:
        logger.error(f'subscribers 로드 실패: {e}')
        return []


# ─── filing 상태 분류 (accession_number 기준 전수 join) ───
def _classify_by_accession(accession_number: str, conn) -> tuple[str, str, str]:
    """accession 단위로 (분류 이모지, 분기 레이블, Notion URL) 반환.

    🟢 완료: filing_analyses 있음 + transcript translated_kr + notion_appended_at
    🟡 분석만: filing_analyses 있음, transcript 미게시·미번역·미append
    ⚪ 진행중: filing_analyses 없음 (큐 대기)
    """
    a = conn.execute(
        """SELECT a.fiscal_quarter, a.fiscal_year FROM filing_analyses a
           JOIN filings f ON a.filing_id = f.id
           WHERE f.accession_number=? ORDER BY a.id DESC LIMIT 1""",
        (accession_number,),
    ).fetchone()
    if not a:
        return ('⚪', '', '')

    q_label = ''
    if a['fiscal_year'] and a['fiscal_quarter']:
        q_label = f"{a['fiscal_quarter']}Q{a['fiscal_year'] % 100:02d}"

    t = conn.execute(
        """SELECT t.translated_kr, t.notion_appended_at, t.notion_page_id
           FROM transcripts t JOIN filings f ON t.filing_id = f.id
           WHERE f.accession_number=? AND t.match_confidence >= 0.7
           ORDER BY t.match_confidence DESC, t.fetched_at DESC LIMIT 1""",
        (accession_number,),
    ).fetchone()

    # Notion URL 우선순위: transcripts.notion_page_id (가장 정확) → filings.published.metadata_json (폴백)
    notion_url = ''
    if t and t['notion_page_id']:
        pid = t['notion_page_id'].replace('-', '')
        if pid:
            notion_url = f'https://www.notion.so/{pid}'
    if not notion_url:
        n = conn.execute(
            """SELECT metadata_json FROM filings
               WHERE accession_number=? AND stage='published'
               ORDER BY id DESC LIMIT 1""",
            (accession_number,),
        ).fetchone()
        if n and n['metadata_json']:
            try:
                m = json.loads(n['metadata_json'])
                pid = (m.get('notion_page_id') or '').replace('-', '')
                if pid:
                    notion_url = f'https://www.notion.so/{pid}'
            except Exception:
                pass

    if t and t['translated_kr'] and t['notion_appended_at']:
        return ('🟢', q_label, notion_url)
    return ('🟡', q_label, notion_url)


# ─── 메시지 빌더 ───
def build_morning_digest(now: datetime | None = None) -> str:
    now = now or datetime.now(tz=timezone.utc)
    since_iso = (now - timedelta(hours=LOOKBACK_HOURS)).isoformat(timespec='seconds')
    today_kst = now.astimezone(KST).date()

    db.init_db()
    conn = db.get_conn()
    try:
        # Section 1. 어제 신규 발표 — accession_number 기준 dedup (한 종목이 같은 분기 여러 stage 가능)
        rows = conn.execute(
            """SELECT ticker, accession_number, MIN(filed_at) AS filed_at,
                      MAX(severity) AS severity, MAX(document_type) AS document_type
               FROM filings
               WHERE filed_at >= ?
                 AND document_type IN ('8-K', '6-K')
               GROUP BY accession_number
               ORDER BY filed_at ASC""",
            (since_iso,),
        ).fetchall()
        new_unique = [dict(r) for r in rows]

        green, yellow, white = [], [], []
        for f in new_unique:
            cat, q, url = _classify_by_accession(f['accession_number'], conn)
            label = q or f['document_type']
            entry = (f['ticker'], label, url)
            if cat == '🟢':
                green.append(entry)
            elif cat == '🟡':
                yellow.append(entry)
            else:
                white.append(entry)

        # Section 2. 미해결 transcript 큐
        backlog = conn.execute(
            """SELECT j.ticker, j.last_status, j.attempt_count, j.last_error,
                      f.filed_at
               FROM transcript_jobs j JOIN filings f ON j.filing_id = f.id
               WHERE j.last_status NOT IN ('success', 'gave_up')
               ORDER BY f.filed_at DESC LIMIT 30""",
        ).fetchall()
        backlog = [dict(r) for r in backlog]

        # Section 3. 다음 7일 예정
        upcoming = conn.execute(
            """SELECT ticker, event_date, hour FROM earnings_calendar
               WHERE event_date BETWEEN ? AND ?
               ORDER BY event_date, ticker""",
            (today_kst.isoformat(),
             (today_kst + timedelta(days=LOOKAHEAD_DAYS)).isoformat()),
        ).fetchall()
        upcoming = [dict(r) for r in upcoming]
    finally:
        conn.close()

    # ── 메시지 조립 ──
    lines = [f"📊 어닝봇 일일 다이제스트 ({today_kst.isoformat()})", '']

    total_new = len(new_unique)
    lines.append(f'━━ 어제 발표 신규 ({total_new}건) ━━')
    if total_new == 0:
        lines.append('  (없음)')
    else:
        if green:
            lines.append(f'🟢 완료 ({len(green)}):')
            for ticker, label, url in green:
                tail = f' — {url}' if url else ''
                lines.append(f'  • {ticker} {label}{tail}')
        if yellow:
            lines.append(f'🟡 분석만 발행, Q&A 번역 대기 ({len(yellow)}):')
            for ticker, label, url in yellow:
                tail = f' — {url}' if url else ''
                lines.append(f'  • {ticker} {label}{tail}')
        if white:
            lines.append(f'⚪ 진행중 ({len(white)}):')
            for ticker, label, _ in white:
                lines.append(f'  • {ticker} {label}')

    lines.extend(['', f'━━ 미해결 transcript 큐 ({len(backlog)}건) ━━'])
    if not backlog:
        lines.append('  (없음)')
    else:
        for r in backlog[:15]:
            try:
                filed_dt = datetime.fromisoformat(
                    r['filed_at'].replace('Z', '+00:00') if r['filed_at'] else ''
                )
                age_days = (now - filed_dt).days
            except Exception:
                age_days = '?'
            stale = ' [stale]' if isinstance(age_days, int) and age_days >= STALE_DAYS else ''
            lines.append(
                f"  • {r['ticker']} — {age_days}일 전, "
                f"{r['attempt_count']}회 재시도, {r['last_status']}{stale}"
            )
        if len(backlog) > 15:
            lines.append(f'  ... 외 {len(backlog) - 15}건')

    lines.extend(['', f'━━ 다음 {LOOKAHEAD_DAYS}일 예정 ({len(upcoming)}건) ━━'])
    if not upcoming:
        lines.append('  (없음)')
    else:
        # 한 줄에 여러 종목 묶기 (가독성)
        chunks = []
        for r in upcoming:
            hr = (r['hour'] or '').upper()
            chunks.append(f"{r['ticker']} {r['event_date'][5:]}{(' ' + hr) if hr else ''}")
        line = '  '
        for c in chunks:
            if len(line) + len(c) + 3 > 80:
                lines.append(line.rstrip(' ·'))
                line = '  '
            line += c + ' · '
        if line.strip():
            lines.append(line.rstrip(' ·'))

    return '\n'.join(lines)


# ─── Telegram 발송 ───
def _telegram_send(token: str, chat_id: int, text: str) -> bool:
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    body = urllib.parse.urlencode({
        'chat_id': chat_id,
        'text': text,
        'disable_web_page_preview': 'true',
    }).encode()
    req = urllib.request.Request(url, data=body)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        logger.warning(f'Telegram 발송 실패 chat={chat_id}: {e}')
        return False


def send_to_telegram(message: str) -> dict:
    token = os.getenv('TELEGRAM_RA_SISYPHE_BOT_TOKEN')
    if not token:
        logger.error('TELEGRAM_RA_SISYPHE_BOT_TOKEN 미설정')
        return {'sent': 0, 'failed': 0, 'reason': 'token missing'}

    subs = _load_subscribers()
    if not subs:
        logger.warning('subscribers 비어있음')
        return {'sent': 0, 'failed': 0, 'reason': 'no subscribers'}

    # 메시지 분할 (라인 단위 4000자)
    parts: list[str] = []
    cur = ''
    for line in message.split('\n'):
        if len(cur) + len(line) + 1 > TG_MAX:
            parts.append(cur)
            cur = line
        else:
            cur = (cur + '\n' + line) if cur else line
    if cur:
        parts.append(cur)

    sent, failed = 0, 0
    for chat_id in subs:
        for p in parts:
            if _telegram_send(token, chat_id, p):
                sent += 1
            else:
                failed += 1
            time.sleep(0.05)  # rate limit 안전 여유
    return {'sent': sent, 'failed': failed, 'subscribers': len(subs), 'parts': len(parts)}


def run() -> dict:
    msg = build_morning_digest()
    if os.getenv('EARNINGS_BOT_DRY_RUN', '').lower() in ('1', 'true', 'yes'):
        logger.info(f'morning_digest DRY_RUN — {len(msg)} chars')
        return {'dry_run': True, 'msg_chars': len(msg), 'msg': msg}
    result = send_to_telegram(msg)
    logger.info(f'morning_digest 발송: {result}')
    return result


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    result = run()
    if 'msg' in result:
        print(result['msg'])
    print()
    print('Result:', {k: v for k, v in result.items() if k != 'msg'})
