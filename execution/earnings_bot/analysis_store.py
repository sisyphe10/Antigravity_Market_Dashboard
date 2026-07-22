# -*- coding: utf-8 -*-
"""분석 1-page 시트를 datalake md로 발행 — Notion 대체 (2026-07-22 사용자 결정).

transcript_store(2026-07-21)와 동일 패턴. runner 6단계에서
notion_publisher.publish_pending 대신 호출된다 (구 Notion 코드는 롤백용 잔존).

저장 경로: $DATALAKE_ROOT/analyses/YYYY/YYYY-MM-DD_TICKER_<accession뒤6자리>.md
stage='published' upsert(메타 md_path)로 기존 dedup/다이제스트 판정 유지.
열람: ts.net /wiki/library (Earnings Library).
"""
import json
import os

from . import db

DRY_RUN = os.getenv('DRY_RUN', '') == '1'


def _datalake_root() -> str:
    root = os.path.expanduser(os.getenv('DATALAKE_ROOT', '~/datalake'))
    if not os.path.isdir(root):
        raise RuntimeError(
            f'DATALAKE_ROOT 미존재: {root} — 맥미니가 아닌 환경으로 보임. '
            'DRY_RUN=1 또는 DATALAKE_ROOT 지정 후 실행.')
    return root


def _md_relpath(filing: dict) -> str:
    filed_date = (filing.get('filed_at') or '')[:10] or 'unknown-date'
    acc6 = (filing.get('accession_number') or '').split('-')[-1][-6:] or f"f{filing['id']}"
    return os.path.join('analyses', filed_date[:4],
                        f"{filed_date}_{filing['ticker']}_{acc6}.md")


def publish_analysis_md(filing_id: int, *, force: bool = False) -> dict:
    """analyzed filing 1건의 분석 md 저장 + stage='published' 진행."""
    db.init_db()
    filing = db.get_filing_by_id(filing_id)
    if not filing:
        return {'error': f'filing_id={filing_id} 없음'}
    analysis = db.get_latest_analysis(filing_id)
    if not analysis:
        return {'error': f'filing_id={filing_id} 분석 결과 없음'}
    if not force and db.has_processed(filing['ticker'], filing['document_type'], 'published',
                                      accession_number=filing['accession_number']):
        return {'skip': True, 'reason': 'already published'}

    document_subtype = '8-K_OTHER'
    try:
        meta = json.loads(filing['metadata_json']) if filing.get('metadata_json') else {}
        document_subtype = meta.get('document_subtype', document_subtype)
    except json.JSONDecodeError:
        pass

    fy = analysis.get('fiscal_year') or 0
    fq = analysis.get('fiscal_quarter') or 0
    quarter = f'{fq}Q{fy % 100:02d}' if fy and fq else ''
    title = f"[{filing['ticker']}] {quarter or '?Q??'} 실적"

    fm = {
        'title': title,
        'ticker': filing['ticker'],
        'quarter': quarter,
        'type': document_subtype,
        'severity': filing.get('severity') or 'NORMAL',
        'accession': filing['accession_number'],
        'date': (filing.get('filed_at') or '')[:10],
        'source_url': filing.get('source_url') or '',
        'prompt_version': analysis.get('prompt_version') or '',
    }
    fm_text = '\n'.join(f'{k}: "{v}"' for k, v in fm.items() if v)
    md = f"---\n{fm_text}\n---\n\n{analysis['analysis_kr'].strip()}\n"

    rel = _md_relpath(filing)
    if DRY_RUN:
        return {'filing_id': filing_id, 'dry_run': True, 'rel': rel, 'chars': len(md)}

    root = _datalake_root()
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(md)
    os.replace(tmp, path)

    db.upsert_filing(
        ticker=filing['ticker'],
        accession_number=filing['accession_number'],
        cik=filing['cik'],
        document_type=filing['document_type'],
        stage='published',
        form_item=filing['form_item'],
        filed_at=filing['filed_at'],
        amc_or_bmo=filing['amc_or_bmo'],
        severity=filing['severity'],
        source_url=filing['source_url'],
        metadata_json=json.dumps({
            'parent_filing_id': filing_id,
            'md_path': rel,
            'action': 'md_saved',
            'prompt_version': analysis.get('prompt_version'),
        }, ensure_ascii=False),
    )
    return {'filing_id': filing_id, 'ticker': filing['ticker'], 'md_path': rel, 'chars': len(md)}


def publish_pending(limit: int = 5) -> list[dict]:
    """stage='analyzed' 이면서 아직 published 없는 filings 일괄 md 발행."""
    db.init_db()
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """
            SELECT f.id FROM filings f
            WHERE f.stage = 'analyzed'
              AND NOT EXISTS (
                SELECT 1 FROM filings f2
                WHERE f2.ticker = f.ticker
                  AND f2.accession_number = f.accession_number
                  AND f2.document_type = f.document_type
                  AND f2.stage = 'published'
              )
            ORDER BY f.filed_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    results = []
    for r in rows:
        try:
            results.append(publish_analysis_md(r['id']))
        except Exception as e:  # noqa: BLE001 — 단건 실패가 배치를 막지 않게
            results.append({'filing_id': r['id'], 'error': f'{type(e).__name__}: {e}'})
    return results
