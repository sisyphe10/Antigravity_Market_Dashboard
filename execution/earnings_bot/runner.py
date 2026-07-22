"""runner — earnings_bot orchestrator. systemd timer가 매일 08:00 KST 1회 호출.

각 호출마다 (1일 1회 통합 사이클):
  1. scheduler.sync_calendar() — Finnhub earnings calendar 14일 윈도우 적재
  2. edgar_monitor.poll_universe() — universe 신규 8-K/6-K/NT-10 폴링
  3. transcript_watch.run_once() — 큐에 있는 transcript 잡 처리 (search 시도)
  4. translator.process_pending() — fetched filings 분석 (Sonnet 호출, 비용 발생)
  5. translator.translate_pending_transcripts() — 번역 미완료 transcript Haiku 처리
  6. notion_publisher.publish_pending() — analyzed 결과 Notion 발행
  7. transcript_store.save_pending() — 번역 완료 transcript를 datalake md로 저장
     (2026-07-21 Notion append 대체 — 구 append_pending_translations는 롤백용 잔존)
  8. transcript_digest.run() — 운영 다이제스트 (콘솔/journal 디버그용)
  9. morning_digest.run() — 사용자용 텔레그램 다이제스트 (RA_Sisyphe 채널)

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
        analysis_store,
        edgar_monitor,
        morning_digest,
        scheduler,
        transcript_digest,
        transcript_store,
        transcript_watch,
        translator,
    )

    started = _now_kst()
    summary: list[dict] = []

    # 1) scheduler.sync_calendar — Finnhub 14일 윈도우 캘린더 적재
    summary.append(_safe('scheduler.sync_calendar', scheduler.sync_calendar))

    # 2) edgar_monitor — Universe USD 종목 (Sheets 라이브 fetch) 8-K/6-K/NT-10 폴링
    summary.append(_safe('edgar_monitor.poll_universe', edgar_monitor.poll_universe))

    # 3) transcript_watch — 큐에 있는 transcript 잡 처리 (search 시도)
    summary.append(_safe('transcript_watch.run_once', transcript_watch.run_once))

    # 4) translator (1-page 분석, Sonnet) — 비용 발생. limit 20.
    summary.append(_safe('translator.process_pending',
                         lambda: translator.process_pending(limit=20)))

    # 5) translator (transcript 풀 번역, Haiku 분할) — 비용 발생. limit 3.
    summary.append(_safe('translator.translate_pending_transcripts',
                         lambda: translator.translate_pending_transcripts(limit=3)))

    # 6) analysis_store (분석 md 발행 — 2026-07-22 Notion publish 대체, 구 코드는 롤백용 잔존)
    summary.append(_safe('analysis_store.publish_pending',
                         lambda: analysis_store.publish_pending(limit=5)))

    # 7) transcript_store (한국어 transcript → datalake md 저장, 2026-07-21 Notion append 대체)
    summary.append(_safe('transcript_store.save_pending',
                         lambda: transcript_store.save_pending(limit=10)))

    # 8) transcript_digest — 운영 디버그 (journal에만, 텔레그램 발송 X)
    summary.append(_safe('transcript_digest.run', transcript_digest.run))

    # 9) morning_digest — 사용자용 텔레그램 다이제스트 (RA_Sisyphe_bot 채널)
    summary.append(_safe('morning_digest.run', morning_digest.run))

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
