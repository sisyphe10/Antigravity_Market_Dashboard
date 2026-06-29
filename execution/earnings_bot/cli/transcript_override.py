"""사용자 수동 URL 주입 CLI — needs_review/stale_pending 큐 해결.

사용:
  python -m execution.earnings_bot.cli.transcript_override --filing-id 5 --url https://...
  python -m execution.earnings_bot.cli.transcript_override --list-needs-review
"""
from __future__ import annotations

import argparse
import logging

from .. import db
from ..transcript_sources import TranscriptCandidate, make_event_from_filing
from ..transcript_sources.manual import ManualOverrideSource
from .. import ticker_registry

logger = logging.getLogger(__name__)


def list_needs_review() -> None:
    db.init_db()
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """
            SELECT j.id as job_id, j.filing_id, j.ticker, j.last_status, j.attempt_count,
                   j.last_error, f.accession_number, f.document_type, f.severity, f.filed_at
            FROM transcript_jobs j
            JOIN filings f ON j.filing_id = f.id
            WHERE j.last_status IN ('needs_review', 'stale_pending', 'low_confidence')
            ORDER BY f.filed_at DESC
            LIMIT 50
            """,
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        print("미해결 큐 비어 있음")
        return

    print(f"{'ticker':6}  {'filing_id':9}  {'status':14}  {'attempts':8}  {'doc':10}  {'filed_at':20}  {'error'}")
    for r in rows:
        print(f"{r['ticker']:6}  {r['filing_id']:9}  {r['last_status']:14}  "
              f"{r['attempt_count']:8}  {r['document_type']:10}  "
              f"{r['filed_at'] or '':20}  {r['last_error'] or ''}")


def dismiss(ticker: str) -> None:
    """needs_review/stale_pending/low_confidence 상태의 해당 ticker 잡을 'gave_up'으로 종결.

    자동 해결이 불가능해 다이제스트(보류·수동대기)에 계속 노출되는 잡을 수동 정리할 때 사용.
    'gave_up'은 cleanup_stale가 retention 만료 시 부여하는 것과 동일한 종결 상태라
    재시도/보류·수동대기/다이제스트 어디에도 다시 나타나지 않는다 (신규 상태값 도입 없음).
    """
    db.init_db()
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """
            SELECT j.id, j.filing_id, j.last_status, j.attempt_count, f.filed_at
            FROM transcript_jobs j JOIN filings f ON j.filing_id = f.id
            WHERE UPPER(j.ticker) = ?
              AND j.last_status IN ('needs_review', 'stale_pending', 'low_confidence')
            """,
            (ticker.upper(),),
        ).fetchall()
        if not rows:
            print(f"{ticker}: needs_review/stale_pending/low_confidence 잡 없음 "
                  f"(이미 종결됐거나 미존재)")
            return
        conn.execute(
            """
            UPDATE transcript_jobs SET last_status='gave_up'
            WHERE UPPER(ticker) = ?
              AND last_status IN ('needs_review', 'stale_pending', 'low_confidence')
            """,
            (ticker.upper(),),
        )
        conn.commit()
        fids = [r['filing_id'] for r in rows]
        print(f"OK — {ticker}: {len(rows)}건 'gave_up' 종결 처리 (filing_id={fids})")
    finally:
        conn.close()


def override(filing_id: int, url: str) -> None:
    db.init_db()
    filing = db.get_filing_by_id(filing_id)
    if not filing:
        print(f"filing_id={filing_id} 없음")
        return
    ticker_meta = ticker_registry.get_issuer_meta(filing['ticker'])
    event = make_event_from_filing(filing, ticker_meta)

    src = ManualOverrideSource()
    candidate = TranscriptCandidate(
        url=url, title='manual override', snippet='', source=src.name,
    )
    parsed = src.parse(candidate, event)
    if parsed is None:
        print(f"URL fetch 실패: {url}")
        return

    transcript_id = db.insert_transcript(
        filing_id=filing_id, source=src.name,
        source_url=parsed.source_url, normalized_url=parsed.normalized_url,
        content_hash=parsed.content_hash,
        prepared_remarks=parsed.prepared_remarks, qa=parsed.qa,
        parser_version=parsed.parser_version,
        match_confidence=parsed.match_confidence,
    )
    if transcript_id is None:
        print(f"중복 transcript (이미 존재). filing_id={filing_id}")
        return

    # 해당 filing의 transcript_job 상태도 success로 갱신
    conn = db.get_conn()
    try:
        conn.execute(
            "UPDATE transcript_jobs SET last_status='success', source=? WHERE filing_id=?",
            (src.name, filing_id),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"OK — transcript_id={transcript_id}, filing_id={filing_id}, "
          f"prepared={len(parsed.prepared_remarks)}자, qa={len(parsed.qa)}자")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--filing-id', type=int, help='수동 주입 대상 filing_id')
    p.add_argument('--url', help='transcript URL')
    p.add_argument('--list-needs-review', action='store_true',
                   help='미해결 큐 (needs_review / stale_pending / low_confidence) 출력')
    p.add_argument('--dismiss', metavar='TICKER',
                   help="해당 ticker의 미해결 잡을 'gave_up'으로 종결 (다이제스트에서 제거)")
    args = p.parse_args()

    if args.list_needs_review:
        list_needs_review()
    elif args.dismiss:
        dismiss(args.dismiss)
    elif args.filing_id and args.url:
        override(args.filing_id, args.url)
    else:
        p.print_help()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    main()
