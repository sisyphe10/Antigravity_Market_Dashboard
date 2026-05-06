"""runner — earnings_bot orchestrator. systemd timer가 5분마다 호출.

각 호출마다:
  1. (08:00 KST 시간대) scheduler.sync_calendar() — Finnhub earnings calendar 적재
  2. edgar_monitor.poll_universe() — universe 신규 8-K/6-K/NT-10 폴링
  3. transcript_watch.run_once() — 큐에 있는 transcript 잡 처리
  4. translator.process_pending() — fetched filings 분석 (Sonnet 호출, 비용 발생)
  5. notion_publisher.publish_pending() — analyzed 결과 Notion 발행
  6. (23:00 KST 시간대) transcript_digest.run() — 일일 다이제스트

매 단계 결과는 JSON 줄로 출력 → systemd journal에 기록 → 디버깅 용이.
한 단계 실패해도 다음 단계 진행 (운영 안정성).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta

logger = logging.getLogger('earnings_bot.runner')

KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    return datetime.now(tz=KST)


def _is_within_hour(target_hour: int, dt: datetime, slack_min: int = 5) -> bool:
    """timer 5분 간격이라 target_hour:00 ~ target_hour:slack_min 범위에서만 1회 실행."""
    if dt.hour != target_hour:
        return False
    return dt.minute < slack_min


def _safe(name: str, fn) -> dict:
    """예외 잡고 결과를 dict로 표준화."""
    t0 = time.time()
    try:
        result = fn()
        elapsed = time.time() - t0
        return {'step': name, 'status': 'ok', 'elapsed_s': round(elapsed, 2), 'result': result}
    except Exception as e:
        elapsed = time.time() - t0
        logger.exception(f'[{name}] failed')
        return {'step': name, 'status': 'error', 'elapsed_s': round(elapsed, 2), 'error': str(e)}


def run_pipeline() -> dict:
    """orchestrator main entry."""
    from . import (
        edgar_monitor,
        notion_publisher,
        scheduler,
        transcript_digest,
        transcript_watch,
        translator,
    )

    started = _now_kst()
    summary: list[dict] = []

    # 1) scheduler — 하루 1회 (08:00 KST 시간대)
    if _is_within_hour(8, started):
        summary.append(_safe('scheduler.sync_calendar', scheduler.sync_calendar))

    # 2) edgar_monitor — 매 호출
    summary.append(_safe('edgar_monitor.poll_universe', edgar_monitor.poll_universe))

    # 3) transcript_watch — 매 호출 (5분 단위)
    summary.append(_safe('transcript_watch.run_once', transcript_watch.run_once))

    # 4) translator (1-page 분석) — 매 호출. 비용 발생하므로 limit 작게.
    summary.append(_safe('translator.process_pending',
                         lambda: translator.process_pending(limit=5)))

    # 4b) translator (transcript 풀 번역, Haiku) — 매 호출. limit 3.
    summary.append(_safe('translator.translate_pending_transcripts',
                         lambda: translator.translate_pending_transcripts(limit=3)))

    # 5) notion_publisher (분석 publish) — 매 호출
    summary.append(_safe('notion_publisher.publish_pending',
                         lambda: notion_publisher.publish_pending(limit=5)))

    # 5b) notion_publisher (한국어 transcript append) — 매 호출
    summary.append(_safe('notion_publisher.append_pending_translations',
                         lambda: notion_publisher.append_pending_translations(limit=5)))

    # 6) digest — 하루 1회 (23:00 KST 시간대)
    if _is_within_hour(23, started):
        summary.append(_safe('transcript_digest.run', transcript_digest.run))

    completed = _now_kst()
    return {
        'started_kst': started.isoformat(timespec='seconds'),
        'completed_kst': completed.isoformat(timespec='seconds'),
        'duration_s': round((completed - started).total_seconds(), 2),
        'steps': summary,
        'errors': sum(1 for s in summary if s['status'] == 'error'),
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv('EARNINGS_BOT_LOG_LEVEL', 'INFO'),
        format='%(asctime)s [%(levelname)s] %(name)s %(message)s',
    )
    result = run_pipeline()
    # 한 줄 JSON으로 systemd journal에 기록
    print(json.dumps(result, ensure_ascii=False, default=str))
    sys.exit(1 if result['errors'] else 0)
