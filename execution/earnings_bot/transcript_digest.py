"""일일 transcript 다이제스트 — 23:00 KST systemd timer.

지난 24시간 동안 종료된 transcript_jobs 통계 + 미해결 needs_review 큐.
Telegram에 1건 메시지로 발송 (개별 즉시 알림 폐기).
"""
from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import db

logger = logging.getLogger(__name__)


def build_digest(now: datetime | None = None) -> str:
    """지난 24h 통계 + needs_review/stale_pending 큐 요약."""
    now = now or datetime.now(tz=timezone.utc)
    since = (now - timedelta(hours=24)).isoformat(timespec='seconds')

    db.init_db()
    conn = db.get_conn()
    try:
        # 24시간 동안 종료된 잡 통계
        rows = conn.execute(
            """
            SELECT j.last_status, j.source, COUNT(*) as cnt
            FROM transcript_jobs j
            JOIN filings f ON j.filing_id = f.id
            WHERE f.created_at >= ?
            GROUP BY j.last_status, j.source
            ORDER BY cnt DESC
            """,
            (since,),
        ).fetchall()
        status_counts = Counter()
        source_counts = Counter()
        for r in rows:
            status_counts[r['last_status']] += r['cnt']
            source_counts[r['source'] or 'unknown'] += r['cnt']

        # 현재 미해결 큐
        backlog = conn.execute(
            """
            SELECT j.last_status, COUNT(*) as cnt
            FROM transcript_jobs j
            WHERE j.last_status IN ('needs_review', 'stale_pending', 'pending', 'low_confidence')
            GROUP BY j.last_status
            """,
        ).fetchall()
        backlog_dict = {r['last_status']: r['cnt'] for r in backlog}

        # 신규 success transcript (지난 24h)
        new_success = conn.execute(
            """
            SELECT COUNT(*) as cnt FROM transcripts WHERE fetched_at >= ?
            """,
            (since,),
        ).fetchone()
        success_count = new_success['cnt'] if new_success else 0
    finally:
        conn.close()

    lines = [
        f"📊 Transcript 다이제스트 ({now.strftime('%Y-%m-%d %H:%M UTC')})",
        '',
        f"━━ 지난 24시간 ━━",
        f"성공: {success_count}건",
    ]
    for status, cnt in status_counts.most_common():
        if status == 'success':
            continue
        lines.append(f"  {status}: {cnt}")
    if source_counts:
        lines.append('')
        lines.append('소스별:')
        for src, cnt in source_counts.most_common():
            lines.append(f"  {src}: {cnt}")

    lines.extend(['', '━━ 미해결 큐 ━━'])
    if backlog_dict:
        for status, cnt in backlog_dict.items():
            lines.append(f"  {status}: {cnt}")
    else:
        lines.append("  (없음)")

    return '\n'.join(lines)


def run() -> str:
    digest = build_digest()
    print(digest)
    # Phase 5에서 ra-sisyphe-bot Telegram 채널로 발송 (별도 모듈에서 호출)
    return digest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    run()
