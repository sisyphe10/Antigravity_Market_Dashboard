"""Notion 발행 — filing_analyses 결과를 Notion DB "Universe Earnings"에 publish.

흐름:
  filings.stage='analyzed' (translator 처리 완료)
    → filing_analyses에서 analysis_kr 가져옴
    → publish_analysis(filing_id) 호출
    → Notion 페이지 생성 + properties 채움
    → filings 새 행 stage='published' 추가

Notion DB 스키마 (사용자가 사전 생성):
  - 이름 (Title): "[TICKER] FYxxxx Qx 실적"
  - Ticker (rich_text)
  - Company (rich_text, 선택)
  - Quarter (rich_text): "FY2026 Q2"
  - Filed Date (date)
  - Type (select): 8-K_EARNINGS / 6-K_QUARTERLY / 6-K_MONTHLY / 6-K_AGM / NT_10
  - Severity (select): CRITICAL / HIGH / NORMAL / INFO
  - Source URL (url)
  - Accession (rich_text)
  - Prompt Version (rich_text)

마크다운 → Notion blocks 변환은 research_bot/notion_publisher.py 패턴 차용.
"""
from __future__ import annotations

import json
import logging
import os
import re

from . import db
from .retry_helper import api_retry

logger = logging.getLogger(__name__)

DRY_RUN = os.getenv('EARNINGS_BOT_DRY_RUN', '').lower() in ('1', 'true', 'yes')
NOTION_API_KEY = os.getenv('NOTION_API_KEY', '')
NOTION_DATABASE_ID = os.getenv('NOTION_EARNINGS_DATABASE_ID', '') or os.getenv('NOTION_DATABASE_ID', '')

SEVERITY_ICONS = {
    'CRITICAL': '🔴',
    'HIGH': '🟡',
    'NORMAL': '🟢',
    'INFO': '⚪',
}


# ─── 마크다운 → Notion blocks 변환 (research_bot 패턴 차용 + 단순화) ───
def markdown_to_blocks(md_text: str) -> list[dict]:
    blocks: list[dict] = []
    lines = md_text.split('\n')
    i = 0

    def _rt(text: str, bold: bool = False) -> dict:
        # 인라인 굵게 (**text**) 분리
        out_parts = []
        cursor = 0
        for m in re.finditer(r'\*\*(.+?)\*\*', text):
            if m.start() > cursor:
                out_parts.append({'text': {'content': text[cursor:m.start()]}})
            out_parts.append({
                'text': {'content': m.group(1)},
                'annotations': {'bold': True},
            })
            cursor = m.end()
        if cursor < len(text):
            out_parts.append({'text': {'content': text[cursor:]}})
        if not out_parts:
            out_parts = [{'text': {'content': text}}]
        if bold and out_parts:
            for p in out_parts:
                p.setdefault('annotations', {})['bold'] = True
        return out_parts

    while i < len(lines):
        stripped = lines[i].strip()
        i += 1
        if not stripped:
            continue

        # 마크다운 표
        if stripped.startswith('|') and '|' in stripped[1:]:
            table_rows = [stripped]
            while i < len(lines) and lines[i].strip().startswith('|'):
                row = lines[i].strip()
                i += 1
                if re.match(r'^\|[\s\-:]+\|', row):
                    continue
                table_rows.append(row)
            parsed = []
            for tr in table_rows:
                cells = [c.strip() for c in tr.strip('|').split('|')]
                parsed.append(cells)
            col_count = max(len(r) for r in parsed) if parsed else 1
            children = []
            for row_cells in parsed:
                while len(row_cells) < col_count:
                    row_cells.append('')
                children.append({
                    'object': 'block', 'type': 'table_row',
                    'table_row': {
                        'cells': [[{'text': {'content': c}}] for c in row_cells[:col_count]]
                    }
                })
            blocks.append({
                'object': 'block', 'type': 'table',
                'table': {
                    'table_width': col_count,
                    'has_column_header': True,
                    'children': children,
                }
            })
            continue

        # H1 / H2 / H3
        if stripped.startswith('### '):
            blocks.append({
                'object': 'block', 'type': 'heading_3',
                'heading_3': {'rich_text': _rt(stripped[4:])},
            })
        elif stripped.startswith('## '):
            blocks.append({
                'object': 'block', 'type': 'heading_2',
                'heading_2': {'rich_text': _rt(stripped[3:])},
            })
        elif stripped.startswith('# '):
            blocks.append({
                'object': 'block', 'type': 'heading_1',
                'heading_1': {'rich_text': _rt(stripped[2:])},
            })
        # bullet
        elif stripped.startswith('- ') or stripped.startswith('* '):
            blocks.append({
                'object': 'block', 'type': 'bulleted_list_item',
                'bulleted_list_item': {'rich_text': _rt(stripped[2:])},
            })
        # divider
        elif stripped.startswith('---'):
            blocks.append({'object': 'block', 'type': 'divider', 'divider': {}})
        else:
            # paragraph (굵게 시작 패턴 포함)
            blocks.append({
                'object': 'block', 'type': 'paragraph',
                'paragraph': {'rich_text': _rt(stripped)},
            })

    return blocks


# ─── 페이지 dedup: 동일 accession_number 페이지 검색 ───
def _find_existing_page(notion_client, database_id: str, accession_number: str) -> str | None:
    try:
        result = notion_client.databases.query(
            database_id=database_id,
            filter={'property': 'Accession', 'rich_text': {'equals': accession_number}},
            page_size=1,
        )
        if result.get('results'):
            return result['results'][0]['id']
    except Exception as e:
        logger.warning(f"existing page search 실패: {e}")
    return None


# ─── 페이지 생성/업데이트 ───
def _build_properties(filing: dict, analysis: dict, document_subtype: str) -> dict:
    fy = analysis.get('fiscal_year') or 0
    fq = analysis.get('fiscal_quarter') or 0
    severity = filing.get('severity') or 'NORMAL'
    icon = SEVERITY_ICONS.get(severity, '⚪')
    title = f"{icon} [{filing['ticker']}] FY{fy} Q{fq} 실적"

    props = {
        '이름': {'title': [{'text': {'content': title}}]},
        'Ticker': {'rich_text': [{'text': {'content': filing['ticker']}}]},
        'Quarter': {'rich_text': [{'text': {'content': f'FY{fy} Q{fq}'}}]},
        'Type': {'select': {'name': document_subtype}},
        'Severity': {'select': {'name': severity}},
        'Accession': {'rich_text': [{'text': {'content': filing['accession_number']}}]},
        'Prompt Version': {'rich_text': [{'text': {'content': analysis['prompt_version']}}]},
    }
    if filing.get('filed_at'):
        props['Filed Date'] = {'date': {'start': filing['filed_at'][:10]}}
    if filing.get('source_url'):
        props['Source URL'] = {'url': filing['source_url']}
    return props


@api_retry
def _create_notion_page(notion_client, database_id: str, properties: dict, blocks: list[dict]):
    return notion_client.pages.create(
        parent={'database_id': database_id},
        properties=properties,
        children=blocks[:100],  # Notion API 한 번에 최대 100 블록
    )


@api_retry
def _append_blocks(notion_client, page_id: str, blocks: list[dict]):
    for i in range(0, len(blocks), 100):
        notion_client.blocks.children.append(block_id=page_id, children=blocks[i:i+100])


def publish_analysis(filing_id: int) -> dict:
    """analyzed stage 의 filing 1건을 Notion에 publish.

    DRY_RUN=1 이면 Notion 호출 없이 페이지 구조 dict 반환.
    """
    db.init_db()

    # filing_id로 분석 결과 + filing 정보 조회
    filing = db.get_filing_by_id(filing_id)
    if not filing:
        return {'error': f'filing_id={filing_id} 없음'}
    analysis = db.get_latest_analysis(filing_id)
    if not analysis:
        return {'error': f'filing_id={filing_id} 분석 결과 없음 (translator 먼저 실행 필요)'}

    # 이미 published stage 있으면 skip
    if db.has_processed(filing['ticker'], filing['document_type'], 'published',
                        accession_number=filing['accession_number']):
        return {'skip': True, 'reason': 'already published'}

    # document_subtype 추출 (filings.metadata_json)
    document_subtype = '8-K_OTHER'
    try:
        meta = json.loads(filing['metadata_json']) if filing.get('metadata_json') else {}
        document_subtype = meta.get('document_subtype', document_subtype)
    except json.JSONDecodeError:
        pass

    # 본문: analysis_kr + (번역된 transcript가 있으면 풀 번역 append)
    body_md = analysis['analysis_kr']
    transcript_row = db.get_transcript_for_filing(filing_id)
    if transcript_row:
        translated_kr = transcript_row.get('translated_kr')
        if translated_kr:
            # 풀 번역 본문
            body_md += (
                f"\n\n---\n\n## 컨퍼런스콜 전문 (한국어 번역)\n\n"
                f"_원문 출처: [{transcript_row['source']}]({transcript_row['source_url']})_\n\n"
                f"{translated_kr}\n"
            )
        else:
            # 번역 미완료 — 원문 URL만 표시
            body_md += (
                f"\n\n---\n\n## 컨퍼런스콜\n\n"
                f"원문: [{transcript_row['source']}]({transcript_row['source_url']}) "
                f"(한국어 번역 대기 중)\n"
            )

    blocks = markdown_to_blocks(body_md)
    properties = _build_properties(filing, analysis, document_subtype)

    if DRY_RUN or not NOTION_API_KEY or not NOTION_DATABASE_ID:
        reason = 'DRY_RUN' if DRY_RUN else 'NOTION 키/DB ID 미설정'
        return {
            'filing_id': filing_id,
            'dry_run': True,
            'reason': reason,
            'title': properties['이름']['title'][0]['text']['content'],
            'severity': filing['severity'],
            'document_subtype': document_subtype,
            'block_count': len(blocks),
            'properties_keys': list(properties.keys()),
            'first_3_blocks': blocks[:3],
        }

    # 실 Notion 호출
    from notion_client import Client
    notion = Client(auth=NOTION_API_KEY)

    existing = _find_existing_page(notion, NOTION_DATABASE_ID, filing['accession_number'])
    if existing:
        # 기존 페이지에 transcript append (구분선 포함)
        append_blocks = [{'object': 'block', 'type': 'divider', 'divider': {}}] + blocks
        _append_blocks(notion, existing, append_blocks)
        page_id = existing
        action = 'appended'
    else:
        page = _create_notion_page(notion, NOTION_DATABASE_ID, properties, blocks)
        page_id = page['id']
        if len(blocks) > 100:
            _append_blocks(notion, page_id, blocks[100:])
        action = 'created'

    # stage='published' 진행
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
            'notion_page_id': page_id,
            'action': action,
            'prompt_version': analysis['prompt_version'],
        }, ensure_ascii=False),
    )

    return {
        'filing_id': filing_id,
        'ticker': filing['ticker'],
        'notion_page_id': page_id,
        'action': action,
        'block_count': len(blocks),
    }


def append_translated_transcript(transcript_id: int) -> dict:
    """번역 완료된 transcript를 기존 Notion 페이지에 append.

    DRY_RUN=1 또는 NOTION_API_KEY 미설정 시 페이지 구조만 출력.
    """
    db.init_db()
    conn = db.get_conn()
    try:
        row = conn.execute(
            """
            SELECT t.*, f.ticker, f.accession_number, f.severity
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
        return {'skip': True, 'reason': 'not yet translated'}
    if row.get('notion_appended_at'):
        return {'skip': True, 'reason': 'already appended'}

    body_md = (
        f"## 컨퍼런스콜 전문 (한국어 번역)\n\n"
        f"_원문 출처: [{row['source']}]({row['source_url']}) | "
        f"번역 모델: {row.get('translation_model') or 'haiku'} | "
        f"prompt_version: {row.get('prompt_version_translation', '')}_\n\n"
        f"{row['translated_kr']}\n"
    )
    blocks = [{'object': 'block', 'type': 'divider', 'divider': {}}] + markdown_to_blocks(body_md)

    if DRY_RUN or not NOTION_API_KEY or not NOTION_DATABASE_ID:
        reason = 'DRY_RUN' if DRY_RUN else 'NOTION 키/DB ID 미설정'
        return {
            'transcript_id': transcript_id,
            'dry_run': True,
            'reason': reason,
            'ticker': row['ticker'],
            'accession': row['accession_number'],
            'block_count': len(blocks),
            'translated_chars': len(row['translated_kr']),
        }

    from notion_client import Client
    notion = Client(auth=NOTION_API_KEY)
    page_id = _find_existing_page(notion, NOTION_DATABASE_ID, row['accession_number'])
    if not page_id:
        return {'error': f'기존 Notion 페이지 없음 (accession={row["accession_number"]}). publish_analysis 먼저 실행 필요.'}

    _append_blocks(notion, page_id, blocks)
    db.mark_transcript_appended(transcript_id, page_id)

    return {
        'transcript_id': transcript_id,
        'ticker': row['ticker'],
        'notion_page_id': page_id,
        'block_count': len(blocks),
    }


def append_pending_translations(limit: int = 5) -> list[dict]:
    """번역됐지만 Notion 미append된 transcripts 일괄 처리."""
    db.init_db()
    rows = db.get_pending_notion_append_transcripts(limit=limit)
    results = []
    for r in rows:
        try:
            results.append(append_translated_transcript(r['id']))
        except Exception as e:
            logger.error(f'transcript {r["id"]} append 실패: {e}')
            results.append({'transcript_id': r['id'], 'error': str(e)})
    return results


def publish_pending(limit: int = 10) -> list[dict]:
    """stage='analyzed' 면서 아직 published 안 된 filings 일괄 publish."""
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
            # filing_analyses는 fetched filing_id를 참조하므로 parent_filing_id를 거슬러 올라가야 함
            conn = db.get_conn()
            try:
                meta_row = conn.execute(
                    "SELECT metadata_json FROM filings WHERE id=?", (r['id'],)
                ).fetchone()
                parent_id = r['id']
                if meta_row and meta_row['metadata_json']:
                    try:
                        m = json.loads(meta_row['metadata_json'])
                        parent_id = m.get('parent_filing_id', r['id'])
                    except json.JSONDecodeError:
                        pass
            finally:
                conn.close()
            results.append(publish_analysis(parent_id))
        except Exception as e:
            logger.error(f"filing {r['id']} publish 실패: {e}")
            results.append({'filing_id': r['id'], 'error': str(e)})
    return results


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    p = argparse.ArgumentParser()
    p.add_argument('--filing-id', type=int)
    p.add_argument('--pending', action='store_true')
    args = p.parse_args()

    if args.filing_id:
        result = publish_analysis(args.filing_id)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:3000])
    elif args.pending:
        result = publish_pending()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:3000])
    else:
        p.print_help()
