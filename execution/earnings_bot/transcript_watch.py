"""transcript 큐 워커 — 5분 systemd timer.

Codex Phase 2 v2:
- attempt 스케줄: 0/8/24/48/72/120/168/336h (지수 슬로우 다운)
- 상태 enum: pending/success/not_found/blocked/parse_failed/low_confidence/source_changed/needs_review/stale_pending/gave_up
- source iteration: motley_fool 먼저, 실패 시 marketbeat. needs_review은 manual_override 대기

신뢰도 ≥ 0.7 (matcher.DEFAULT_THRESHOLD) 이면 success.
미만이면 low_confidence → 다음 attempt 또는 needs_review.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Sequence

from . import db, ticker_registry
from .matcher import DEFAULT_THRESHOLD, score_parsed_breakdown
from .transcript_sources import (EarningsEvent, TranscriptSource,
                                 make_event_from_filing)
from .transcript_sources.marketbeat import MarketBeatSource
from .transcript_sources.q4cdn import Q4CdnSource
from .transcript_sources.cameco import CamecoSource
from .transcript_sources.insider_monkey import InsiderMonkeySource
from .transcript_sources.globe_and_mail import GlobeAndMailSource
from .transcript_sources.motley_fool import MotleyFoolSource

logger = logging.getLogger(__name__)

# attempt 스케줄 — 시간 단위 (event 시각 기준 누적)
ATTEMPT_SCHEDULE_HOURS = [0, 8, 24, 48, 72, 120, 168, 336]
# 8회 시도 후 stale_pending → 30일 후 gave_up
STALE_RETENTION_DAYS = 30


# 사용 가능한 자동 소스 (순서대로 시도)
def default_sources() -> list[TranscriptSource]:
    # CamecoSource는 CCJ/CCO만 처리하고 그 외엔 즉시 빈 리스트 → 맨 앞에 둬도 타 종목 영향 없음.
    return [CamecoSource(), Q4CdnSource(), MotleyFoolSource(), InsiderMonkeySource(), GlobeAndMailSource(), MarketBeatSource()]


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _next_attempt_iso(event_time: datetime, attempt_count: int) -> str | None:
    """다음 시도 시각 산출. attempt_count 초과 시 None (stale_pending)."""
    if attempt_count >= len(ATTEMPT_SCHEDULE_HOURS):
        return None
    delta_h = ATTEMPT_SCHEDULE_HOURS[attempt_count]
    next_dt = event_time + timedelta(hours=delta_h)
    # 과거이면 즉시 시도 (event_time + delta < now). 그래도 일단 그대로 적재.
    return next_dt.isoformat(timespec='seconds')


def initial_enqueue(filing_id: int) -> int | None:
    """edgar_monitor.fetched 직후 호출. event_time + 0h 시점에 첫 attempt 잡 생성."""
    db.init_db()
    filing = db.get_filing_by_id(filing_id)
    if not filing:
        return None
    if (filing.get('document_type') == 'NT 10-Q' or filing.get('document_type') == 'NT 10-K'
            or filing.get('severity') == 'INFO'):
        # NT 시그널 / INFO 등급은 transcript 없음 → enqueue 스킵
        return None
    if filing.get('amc_or_bmo'):
        # 정확한 발표 시각 lookup이 가능하면 활용
        from .transcript_sources import make_event_from_filing
        ticker_meta = ticker_registry.get_issuer_meta(filing['ticker'])
        event = make_event_from_filing(filing, ticker_meta)
        event_dt = event.expected_call_datetime
    else:
        # filed_at 그대로 사용
        try:
            event_dt = datetime.fromisoformat((filing.get('filed_at') or '').replace('Z', '+00:00'))
        except Exception:
            event_dt = _utcnow()
    next_iso = _next_attempt_iso(event_dt, 0)
    return db.enqueue_transcript_job(
        filing_id=filing_id, ticker=filing['ticker'],
        next_attempt_at=next_iso, source='motley_fool',
    )


def _process_one(job: dict, sources: Sequence[TranscriptSource]) -> None:
    """잡 1건 처리. 상태 전이 + 다음 attempt 스케줄."""
    filing = db.get_filing_by_id(job['filing_id'])
    if not filing:
        db.update_transcript_job(job['id'], last_status='gave_up',
                                 last_error='filing not found')
        return

    ticker_meta = ticker_registry.get_issuer_meta(filing['ticker'])
    event = make_event_from_filing(filing, ticker_meta)

    # 모든 소스 순회 — 첫 success로 종료
    last_failure_status = 'not_found'
    last_error: str | None = None
    for src in sources:
        try:
            candidates = src.search(event)
        except Exception as e:
            last_failure_status = 'blocked'
            last_error = f'{src.name} search 예외: {e}'
            logger.warning(last_error)
            continue
        if not candidates:
            last_failure_status = 'not_found'
            last_error = f'{src.name} 후보 없음'
            continue
        # 후보 점수 매겨 상위 1개부터 parse
        from .matcher import score_candidate
        ranked = sorted(
            candidates,
            key=lambda c: score_candidate(c, event),
            reverse=True,
        )
        for cand in ranked[:3]:  # 상위 3개만 fetch (rate limit 보호)
            try:
                parsed = src.parse(cand, event)
            except Exception as e:
                last_failure_status = 'parse_failed'
                last_error = f'{src.name} parse 예외: {e}'
                logger.warning(last_error)
                continue
            if parsed is None:
                last_failure_status = 'parse_failed'
                last_error = f'{src.name} parse 결과 None'
                continue
            breakdown = score_parsed_breakdown(parsed, cand, event)
            confidence = breakdown['total']
            parsed.match_confidence = confidence

            if confidence >= DEFAULT_THRESHOLD:
                # success → DB 적재 + 잡 종료
                db.insert_transcript(
                    filing_id=filing['id'], source=src.name,
                    source_url=parsed.source_url, normalized_url=parsed.normalized_url,
                    content_hash=parsed.content_hash,
                    prepared_remarks=parsed.prepared_remarks, qa=parsed.qa,
                    parser_version=parsed.parser_version,
                    match_confidence=confidence,
                )
                db.update_transcript_job(job['id'], last_status='success', source=src.name)
                logger.info(
                    f"[transcript_watch] success filing={filing['id']} ticker={filing['ticker']} "
                    f"source={src.name} confidence={confidence:.3f}"
                )
                return
            else:
                last_failure_status = 'low_confidence'
                last_error = (
                    f'{src.name} confidence={confidence:.3f} < {DEFAULT_THRESHOLD} '
                    f'| breakdown={json.dumps(breakdown, separators=(",", ":"))}'
                )

    # 여기 도달 = 모든 소스 실패. 다음 attempt 스케줄
    new_attempt_count = job['attempt_count'] + 1
    next_iso = _next_attempt_iso(event.expected_call_datetime, new_attempt_count)
    if next_iso is None:
        # attempt cap 도달 → stale_pending
        db.update_transcript_job(
            job['id'], last_status='stale_pending', last_error=last_error,
            attempt_count_delta=1,
        )
        # stale 30일 cap은 별도 cleanup job에서 gave_up 전이
    else:
        db.update_transcript_job(
            job['id'], last_status=last_failure_status,
            next_attempt_at=next_iso, last_error=last_error,
            attempt_count_delta=1,
        )


def cleanup_stale(now: datetime | None = None) -> int:
    """stale_pending 잡 중 event_time + STALE_RETENTION_DAYS 초과 → gave_up."""
    now = now or _utcnow()
    cutoff = now - timedelta(days=STALE_RETENTION_DAYS)
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """
            SELECT j.id FROM transcript_jobs j
            JOIN filings f ON j.filing_id = f.id
            WHERE j.last_status = 'stale_pending'
              AND f.filed_at < ?
            """,
            (cutoff.isoformat(),),
        ).fetchall()
        ids = [r['id'] for r in rows]
        if ids:
            conn.executemany(
                "UPDATE transcript_jobs SET last_status='gave_up' WHERE id=?",
                [(i,) for i in ids],
            )
            conn.commit()
        return len(ids)
    finally:
        conn.close()


def run_once(sources: Sequence[TranscriptSource] | None = None) -> dict:
    """한 번의 워커 실행 — due 잡 처리 + stale cleanup."""
    db.init_db()
    if sources is None:
        sources = default_sources()
    now_iso = _utcnow().isoformat(timespec='seconds')
    jobs = db.get_due_transcript_jobs(now_iso)
    for job in jobs:
        try:
            _process_one(job, sources)
        except Exception as e:
            logger.error(f"job {job['id']} 처리 실패: {e}")
            db.update_transcript_job(job['id'], last_status='parse_failed',
                                     last_error=str(e))
    cleaned = cleanup_stale()
    return {'processed': len(jobs), 'stale_cleaned': cleaned}


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--enqueue', type=int, help='filing_id로 즉시 enqueue')
    parser.add_argument('--run', action='store_true', help='워커 1회 실행')
    args = parser.parse_args()

    if args.enqueue:
        job_id = initial_enqueue(args.enqueue)
        print(f"enqueued job {job_id} for filing {args.enqueue}")
    elif args.run:
        result = run_once()
        print(result)
    else:
        parser.print_help()
