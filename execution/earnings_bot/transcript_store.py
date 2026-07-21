"""transcript_store — 번역 완료 어닝콜 transcript를 datalake에 .md로 저장.

2026-07-21 Notion append 대체 (사용자 결정: transcript 본문은 Notion 미접촉,
맥미니 ~/datalake/transcripts/ 가 정본. 기존 Notion 페이지 분은 아카이브로 유지).

저장 경로: $DATALAKE_ROOT/transcripts/YYYY/YYYY-MM-DD_TICKER_<accession뒤6자리>.md
  - 파일명에 accession 뒤 6자리 필수 — 동일 티커·동일일 복수 filing/복수 소스 충돌 방지
  - 위키 검색(datalake/webui/server.py SEARCH_ROOTS)에 transcripts 루트 등록됨

CLI (맥미니 repo root에서):
  python3 -m execution.earnings_bot.transcript_store --backfill        # 번역 전건 md 생성 (멱등)
  python3 -m execution.earnings_bot.transcript_store --backfill --force  # md_saved_at 무시 재생성
  python3 -m execution.earnings_bot.transcript_store --id 5            # 단건
"""
from __future__ import annotations

import logging
import os

from . import db

logger = logging.getLogger('earnings_bot.transcript_store')

DRY_RUN = os.getenv('EARNINGS_BOT_DRY_RUN', '').lower() in ('1', 'true', 'yes')


def _datalake_root() -> str:
    """DATALAKE_ROOT 해석 + 존재 가드 (맥미니 밖 실수 실행 차단)."""
    root = os.path.expanduser(os.getenv('DATALAKE_ROOT', '~/datalake'))
    if not DRY_RUN and not os.path.isdir(root):
        raise RuntimeError(
            f'DATALAKE_ROOT 미존재: {root} — 맥미니가 아닌 환경으로 보임. '
            f'로컬 테스트는 EARNINGS_BOT_DRY_RUN=1 로.'
        )
    return root


def _quarter_label(filing_id: int) -> str:
    """filing_analyses에서 분기 라벨. 분석이 아직 없으면 빈 문자열 (순서 보장 없음)."""
    a = db.get_latest_analysis(filing_id)
    if a and a.get('fiscal_year') and a.get('fiscal_quarter'):
        return f"{a['fiscal_quarter']}Q{a['fiscal_year'] % 100:02d}"
    return ''


def _md_relpath(row: dict) -> str:
    """transcripts/YYYY/YYYY-MM-DD_TICKER_<acc6>.md (filed_at 기준)."""
    filed_date = (row.get('filed_at') or '')[:10] or 'unknown-date'
    year = filed_date[:4]
    acc6 = (row.get('accession_number') or '').split('-')[-1][-6:] or f"t{row['id']}"
    return os.path.join('transcripts', year, f"{filed_date}_{row['ticker']}_{acc6}.md")


def _build_md(row: dict) -> str:
    quarter = _quarter_label(row['filing_id'])
    title_q = f' {quarter}' if quarter else ''
    fm = [
        '---',
        f"ticker: {row['ticker']}",
        f"filed_at: {(row.get('filed_at') or '')[:10]}",
        f"fiscal: {quarter or '?'}",
        f"accession: {row.get('accession_number') or ''}",
        f"source: {row.get('source') or ''}",
        f"source_url: {row.get('source_url') or ''}",
        f"match_confidence: {row.get('match_confidence')}",
        f"translation_model: {row.get('translation_model') or 'haiku'}",
        f"translated_at: {row.get('translated_at') or ''}",
        '---',
    ]
    body = (
        f"# {row['ticker']}{title_q} 컨퍼런스콜 전문 (한국어 번역)\n\n"
        f"{row['translated_kr']}\n\n"
        f"---\n\n"
        f"_원문 출처: [{row['source']}]({row['source_url']}) | "
        f"번역 모델: {row.get('translation_model') or 'haiku'} | "
        f"prompt_version: {row.get('prompt_version_translation', '')}_\n"
    )
    return '\n'.join(fm) + '\n\n' + body


def save_transcript_md(transcript_id: int, *, force: bool = False) -> dict:
    """단건 저장. 이미 저장됐고 force 아니면 skip."""
    db.init_db()
    conn = db.get_conn()
    try:
        row = conn.execute(
            """
            SELECT t.*, f.ticker, f.accession_number, f.filed_at
            FROM transcripts t JOIN filings f ON t.filing_id = f.id
            WHERE t.id = ?
            """,
            (transcript_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {'error': f'transcript_id={transcript_id} 없음'}
    row = dict(row)
    if not row.get('translated_kr'):
        return {'skip': True, 'transcript_id': transcript_id, 'reason': 'not yet translated'}
    if row.get('md_saved_at') and not force:
        return {'skip': True, 'transcript_id': transcript_id, 'reason': 'already saved',
                'md_path': row.get('md_path')}

    relpath = _md_relpath(row)
    content = _build_md(row)

    if DRY_RUN:
        return {'transcript_id': transcript_id, 'dry_run': True, 'ticker': row['ticker'],
                'md_relpath': relpath, 'chars': len(content)}

    abspath = os.path.join(_datalake_root(), relpath)
    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    with open(abspath, 'w', encoding='utf-8') as f:
        f.write(content)
    db.mark_transcript_md_saved(transcript_id, relpath)
    logger.info(f"transcript {transcript_id} ({row['ticker']}) → {relpath} ({len(content)} chars)")
    return {'transcript_id': transcript_id, 'ticker': row['ticker'],
            'md_path': relpath, 'chars': len(content)}


def save_pending(limit: int = 10) -> list[dict]:
    """번역됐지만 md 미저장 transcripts 일괄 처리 (runner 7단계)."""
    db.init_db()
    rows = db.get_pending_md_save_transcripts(limit=limit)
    results = []
    for r in rows:
        try:
            results.append(save_transcript_md(r['id']))
        except Exception as e:
            logger.error(f"transcript {r['id']} md 저장 실패: {e}")
            results.append({'transcript_id': r['id'], 'error': str(e)})
    return results


def backfill(*, force: bool = False) -> dict:
    """번역 완료 전건 md 생성 (기존 Notion 발행분 이전용, 멱등)."""
    db.init_db()
    conn = db.get_conn()
    try:
        ids = [r[0] for r in conn.execute(
            'SELECT id FROM transcripts WHERE translated_kr IS NOT NULL ORDER BY id')]
    finally:
        conn.close()
    saved = skipped = errors = 0
    for tid in ids:
        try:
            r = save_transcript_md(tid, force=force)
        except Exception as e:
            logger.error(f'transcript {tid} backfill 실패: {e}')
            errors += 1
            continue
        if r.get('skip'):
            skipped += 1
        elif r.get('error'):
            errors += 1
        else:
            saved += 1
    return {'total': len(ids), 'saved': saved, 'skipped': skipped, 'errors': errors}


if __name__ == '__main__':
    import argparse
    import json

    logging.basicConfig(level='INFO', format='%(asctime)s [%(levelname)s] %(name)s %(message)s')
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--backfill', action='store_true', help='번역 전건 md 생성 (멱등)')
    g.add_argument('--id', type=int, help='단건 transcript_id')
    ap.add_argument('--force', action='store_true', help='md_saved_at 무시하고 재생성')
    args = ap.parse_args()

    if args.backfill:
        out = backfill(force=args.force)
    else:
        out = save_transcript_md(args.id, force=args.force)
    print(json.dumps(out, ensure_ascii=False, default=str))
