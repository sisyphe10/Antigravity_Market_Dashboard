"""새벽 LLM 배치 (02:30 KST) — 분석 백로그 → 대량 번역, 쿼터·인증 실패 시 안전 중단.

2026-08-18 설계 v2 (정본=맥미니 ~/work/design/260817_earnings_headless_llm/).
launchd `com.antigravity.earnings-night-llm` → run_timer_job.sh 'earnings-night-llm' 이 호출
(잡 락·타임아웃 워치독·stamp·실패 notify는 래퍼가 담당 — 여기선 exit 코드만 정직하게).

순서가 곧 정책이다 (codex #4):
  ① 분석 백로그 먼저 — 번역이 쿼터를 다 먹어 분석이 영구 후순위가 되는 역전 차단
  ② 대량 번역 (오래된 것 먼저 — codex #9 기아 방지)
  ③ finally: 발행·md 저장은 실패와 무관하게 항상 실행
Quota 소진 = 정상 종료(partial, 잔여는 다음 새벽 이월) / Auth 실패 = exit 1 → 래퍼 notify.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime

logger = logging.getLogger(__name__)

# 이 시각(KST) 이후 신규 항목 착수 금지 — five_hour 쿼터 창이 사용자 오전과 겹치는
# 꼬리 축소 + 08:00 러너와의 간격 확보. 시각 판단 = 이 맥의 로컬시(KST) 기준(하우스 룰).
DEADLINE_HHMM = os.getenv('NIGHT_LLM_DEADLINE', '06:30')
MAX_ITEMS = int(os.getenv('NIGHT_LLM_MAX_ITEMS', '60'))   # 폭주 방지 상한 (분석+번역 합산)


def _deadline_passed() -> bool:
    return datetime.now().strftime('%H:%M') >= DEADLINE_HHMM


def main() -> int:
    from . import analysis_store, headless_llm, translator, transcript_store

    backends = (os.getenv('EARNINGS_ANALYSIS_BACKEND', 'api'),
                os.getenv('EARNINGS_TRANSLATE_BACKEND', 'api'))
    if 'headless' in backends:
        headless_llm.preflight()   # 구독 인증 아니면 여기서 AuthError → exit 1

    stats: dict = {'analysis_ok': 0, 'analysis_fail': 0,
                   'translate_ok': 0, 'translate_fail': 0,
                   'partial': False, 'stopped': None}
    rc = 0
    items = 0
    try:
        # 실행 내 실패 항목 재선택 제외 — 독약 1건이 배치 전체를 소진하는 루프 차단
        # (2026-08-22 실사고: 오수집 tid 284가 청크 게이트에 매번 걸리며 이틀 연속
        #  60슬롯 전부 소진. 게이트는 정상 작동, 재선택 로직 부재가 원인)
        failed_filings: set[int] = set()
        failed_tids: set[int] = set()

        # ① 분석 백로그 (오래된 것 먼저)
        while not _deadline_passed() and items < MAX_ITEMS:
            batch = translator.process_pending(limit=1, oldest_first=True,
                                               exclude_ids=failed_filings)
            if not batch:
                break
            items += 1
            r = batch[0] if isinstance(batch[0], dict) else {}
            ok = bool(r) and not r.get('error') and not r.get('skip')
            stats['analysis_ok' if ok else 'analysis_fail'] += 1
            logger.info(f"[night_llm] 분석 {r.get('ticker', r.get('filing_id'))}: "
                        f"{'OK' if ok else r.get('error') or r.get('reason')}")
            if not ok:
                fid = r.get('filing_id')
                if fid is None:
                    # id 미상이면 제외가 불가능 → 같은 항목 무한 재시도 방지 위해 단계 종료
                    logger.error('[night_llm] 분석 실패 항목 filing_id 미상 — 분석 단계 중단')
                    break
                failed_filings.add(fid)

        # ② 대량 번역 (오래된 것 먼저)
        while not _deadline_passed() and items < MAX_ITEMS:
            batch = translator.translate_pending_transcripts(limit=1, oldest_first=True,
                                                             exclude_ids=failed_tids)
            if not batch:
                break
            items += 1
            r = batch[0] if isinstance(batch[0], dict) else {}
            ok = bool(r.get('translated'))
            stats['translate_ok' if ok else 'translate_fail'] += 1
            logger.info(f"[night_llm] 번역 tid={r.get('transcript_id')}: "
                        f"{'OK' if ok else r.get('error') or r.get('reason')}")
            if not ok:
                tid = r.get('transcript_id')
                if tid is None:
                    logger.error('[night_llm] 번역 실패 항목 transcript_id 미상 — 번역 단계 중단')
                    break
                failed_tids.add(tid)

        if _deadline_passed():
            stats['partial'] = True
            stats['stopped'] = f'deadline {DEADLINE_HHMM}'
        elif items >= MAX_ITEMS:
            stats['partial'] = True
            stats['stopped'] = f'max_items {MAX_ITEMS}'
    except headless_llm.HeadlessQuotaError as e:
        # 쿼터 소진 = 예상된 상태. 잔여는 pending 그대로 → 다음 새벽 이월 (exit 0)
        stats['partial'] = True
        stats['stopped'] = f'quota: {str(e)[:150]}'
        logger.warning(f'[night_llm] 쿼터 소진으로 중단 — 잔여는 다음 배치 이월: {e}')
    except headless_llm.HeadlessAuthError as e:
        # 인증 실패 = 사람 개입 필요 (재로그인). 래퍼가 notify 하도록 비정상 종료.
        stats['stopped'] = f'auth: {str(e)[:150]}'
        logger.error(f'[night_llm] 구독 인증 실패 — 맥미니에서 claude /login 필요: {e}')
        rc = 1
    finally:
        # 완료분 발행·저장은 LLM 실패와 무관하게 (codex #4)
        try:
            pub = analysis_store.publish_pending(limit=50)
            sav = transcript_store.save_pending(limit=60)
            stats['published'] = len(pub)
            stats['md_saved'] = len(sav)
        except Exception as e:
            logger.error(f'[night_llm] 발행/저장 단계 실패: {e}')
            stats['publish_error'] = str(e)[:200]
            rc = rc or 1

    print(json.dumps({'night_llm': stats, 'kst': datetime.now().isoformat(timespec='seconds')},
                     ensure_ascii=False))
    return rc


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(message)s')
    sys.exit(main())
