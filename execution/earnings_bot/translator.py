"""translator — Sonnet 분석 + Haiku 번역. SKILL.md prompt caching 적용.

흐름:
  edgar_monitor.fetched (filings 적재)
    ↓
  translator.process_filing(filing_id):
    1. attachment_parser 결과 (primary_text) 가져옴
    2. yoy_calculator.compute_yoy → YoY 표 (mechanical)
    3. insider_signal.fetch_insider_window → ±30일 부록
    4. prompt_builder → Sonnet 분석 호출 (SKILL.md cached)
    5. 분석 결과 = 한국어 1-page sheet
    6. (선택) Haiku 짧은 텔레그램 헤드라인 별도 생성
    7. DB filings.metadata_json 업데이트 (analysis 결과 + prompt_version)
    8. stage='analyzed' 진행
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone

from . import db, ticker_registry
from .insider_signal import fetch_insider_window, format_appendix
from .prompt_builder import (ANALYSIS_MODEL, SYSTEM_ANALYSIS, SYSTEM_TRANSLATION,
                             SYSTEM_TRANSLATION_TRANSCRIPT, TRANSLATION_MODEL,
                             AnalysisInput, build_analysis_messages,
                             build_prepared_messages, build_qa_chunk_messages,
                             build_qa_messages,
                             build_transcript_translation_messages,
                             build_translation_messages, get_anthropic_client,
                             prompt_version, skill_md_sha256,
                             transcript_translation_prompt_version)


# Q&A 자동 청크 분할: 한국어 출력이 ~1.5x 영문 chars로 늘어나므로
# 영문 22K chars (~7K input tokens) 정도가 16K output 한도 안전 상한.
QA_CHUNK_MAX_CHARS = 22000


def _chunk_qa_text(qa_text: str, max_chars: int = QA_CHUNK_MAX_CHARS) -> list[str]:
    """qa 본문을 자연 경계(`\nOperator:`)에서 분할.

    - max_chars 이하면 단일 청크
    - 그 이상이면 절반~max_chars 사이에서 가장 가까운 `\nOperator:` 위치에서 자름
    - Operator 경계 못 찾으면 \\n\\n (빈 줄) 또는 어절 경계 폴백
    """
    if not qa_text or len(qa_text) <= max_chars:
        return [qa_text or '']

    chunks: list[str] = []
    remaining = qa_text
    while len(remaining) > max_chars:
        # 절반 위치부터 max_chars 사이에서 가장 가까운 `\nOperator:` 찾기
        search_start = len(remaining) // 2
        idx = remaining.find('\nOperator:', search_start, max_chars + 2000)
        if idx == -1:
            # 폴백: \n\n 빈 줄
            idx = remaining.find('\n\n', search_start, max_chars + 1000)
        if idx == -1:
            # 폴백: max_chars 직전 가장 가까운 \n
            idx = remaining.rfind('\n', search_start, max_chars)
        if idx == -1 or idx <= search_start:
            # 마지막 폴백: 그냥 max_chars
            idx = max_chars
        chunks.append(remaining[:idx].strip())
        remaining = remaining[idx:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks
from .retry_helper import api_retry
from .yoy_calculator import compute_yoy, format_table

logger = logging.getLogger(__name__)

DRY_RUN = os.getenv('EARNINGS_BOT_DRY_RUN', '').lower() in ('1', 'true', 'yes')


@api_retry
def _call_sonnet(messages: list[dict]) -> dict:
    """Sonnet 4.5 호출. system= 파라미터 필수. dict 반환 (text + usage).

    모델 ID는 prompt_builder.ANALYSIS_MODEL 참조 (현재: claude-sonnet-4-5-20250929).
    """
    client = get_anthropic_client()
    resp = client.messages.create(
        model=ANALYSIS_MODEL,
        max_tokens=2000,
        system=SYSTEM_ANALYSIS,
        messages=messages,
    )
    usage = resp.usage
    return {
        'text': '\n'.join(b.text for b in resp.content if b.type == 'text'),
        'input_tokens': usage.input_tokens,
        'output_tokens': usage.output_tokens,
        'cache_read_input_tokens': getattr(usage, 'cache_read_input_tokens', 0) or 0,
        'cache_creation_input_tokens': getattr(usage, 'cache_creation_input_tokens', 0) or 0,
    }


@api_retry
def _call_haiku(messages: list[dict]) -> dict:
    """Haiku 4.5 호출 (짧은 번역용)."""
    client = get_anthropic_client()
    resp = client.messages.create(
        model=TRANSLATION_MODEL,
        max_tokens=500,
        system=SYSTEM_TRANSLATION,
        messages=messages,
    )
    return {
        'text': '\n'.join(b.text for b in resp.content if b.type == 'text'),
        'input_tokens': resp.usage.input_tokens,
        'output_tokens': resp.usage.output_tokens,
    }


def _register_prompt_version_once() -> str:
    pv = prompt_version()
    db.register_prompt_version(
        version=pv,
        description='earnings_bot 1-page sheet (Codex v2 반영)',
        analysis_model=ANALYSIS_MODEL,
        translation_model=TRANSLATION_MODEL,
        skill_md_sha256=skill_md_sha256(),
    )
    return pv


def process_filing(filing_id: int) -> dict:
    """filing 1건 분석. stage='fetched' → 'analyzed' 전이.

    DRY_RUN=1 환경변수 설정 시 API 호출 대신 prompt 빌드만 + 토큰 카운트 출력.
    """
    db.init_db()
    filing = db.get_filing_by_id(filing_id)
    if not filing:
        return {'error': f'filing_id={filing_id} 없음'}

    # 이미 'analyzed' 처리됐으면 skip
    if db.has_processed(filing['ticker'], filing['document_type'], 'analyzed',
                        accession_number=filing['accession_number']):
        return {'skip': True, 'reason': 'already analyzed'}

    # primary_text 복원: edgartools v5의 accession 직접 조회 (get_by_accession_number 우선, find 폴백)
    from .attachment_parser import parse_filing
    from edgar import set_identity
    set_identity(os.getenv('SEC_EDGAR_USER_AGENT', 'Kimtaesik (kts77775@gmail.com)'))
    target_filing = None
    try:
        from edgar import get_by_accession_number  # type: ignore
        target_filing = get_by_accession_number(filing['accession_number'])
    except (ImportError, Exception) as e:
        try:
            from edgar import find
            target_filing = find(filing['accession_number'])
        except Exception as e2:
            return {'error': f"filing {filing['accession_number']} accession lookup 실패: {e2}"}
    if target_filing is None:
        return {'error': f"filing {filing['accession_number']} 조회 결과 없음"}
    parsed = parse_filing(target_filing)

    # fiscal_year / quarter — earnings_calendar 우선
    event_date_str = (filing['filed_at'] or '')[:10] if filing.get('filed_at') else date.today().isoformat()
    conn = db.get_conn()
    try:
        cal = conn.execute(
            "SELECT year, quarter FROM earnings_calendar WHERE ticker=? AND event_date=?",
            (filing['ticker'], event_date_str),
        ).fetchone()
    finally:
        conn.close()
    if cal:
        fy, fq = cal['year'], cal['quarter']
    else:
        # filing_date에서 추정
        try:
            fd = date.fromisoformat(event_date_str)
            fy = fd.year
            fq = (fd.month - 1) // 3 + 1
        except Exception:
            fy, fq = datetime.now(tz=timezone.utc).year, 1

    # YoY 표 (기계 산출)
    yoy_snap = compute_yoy(filing['ticker'], fy, fq, press_release_text=parsed.primary_text)
    yoy_md = format_table(yoy_snap)

    # insider 부록 (±30일)
    try:
        insider = fetch_insider_window(filing['ticker'], date.fromisoformat(event_date_str))
        insider_md = format_appendix(insider)
    except Exception as e:
        logger.warning(f"[{filing['ticker']}] insider fetch 실패: {e}")
        insider_md = '### 내부자 거래\n조회 실패'

    # prompt 빌드
    inp = AnalysisInput(
        ticker=filing['ticker'],
        fiscal_year=fy,
        fiscal_quarter=fq,
        document_type=filing['document_type'],
        severity=filing.get('severity') or 'NORMAL',
        primary_text=parsed.primary_text,
        yoy_table_md=yoy_md,
        insider_appendix_md=insider_md,
        source_url=filing.get('source_url'),
    )
    messages = build_analysis_messages(inp)

    if DRY_RUN:
        # 토큰 카운트만
        try:
            import tiktoken
            enc = tiktoken.get_encoding('cl100k_base')
            tokens = sum(
                len(enc.encode(b['text'])) if isinstance(b, dict) and 'text' in b
                else len(enc.encode(c['text']))
                for m in messages for c in (m['content'] if isinstance(m['content'], list) else [{'text': m['content']}])
                for b in [c]
            )
            print(f'[DRY_RUN] {filing["ticker"]} prompt tokens: {tokens}')
        except Exception as e:
            print(f'[DRY_RUN] 토큰 카운트 실패: {e}')
        return {'dry_run': True, 'ticker': filing['ticker'], 'fy': fy, 'fq': fq,
                'yoy_md': yoy_md, 'insider_md': insider_md}

    # Sonnet 분석 호출
    pv = _register_prompt_version_once()
    sonnet_resp = _call_sonnet(messages)
    analysis_text = sonnet_resp['text']

    # 분석 결과는 filing_analyses 전용 테이블에 저장 (Codex 권고)
    # INSERT OR IGNORE 가 None 반환 시 = 동일 (filing_id, prompt_version) 중복 → analyzed stage 진행 X
    analysis_row_id = db.insert_analysis(
        filing_id=filing_id,
        analysis_kr=analysis_text,
        yoy_md=yoy_md,
        insider_md=insider_md,
        prompt_version=pv,
        analysis_model=ANALYSIS_MODEL,
        input_tokens=sonnet_resp['input_tokens'],
        output_tokens=sonnet_resp['output_tokens'],
        cache_read_tokens=sonnet_resp['cache_read_input_tokens'],
        cache_creation_tokens=sonnet_resp['cache_creation_input_tokens'],
        fiscal_year=fy,
        fiscal_quarter=fq,
    )
    if analysis_row_id is None:
        logger.warning(
            f"[{filing['ticker']}] filing_analyses 중복 (filing_id={filing_id}, "
            f"prompt_version={pv}) — analyzed stage 진행 안 함"
        )
        return {
            'filing_id': filing_id,
            'ticker': filing['ticker'],
            'skip': True,
            'reason': 'duplicate (filing_id, prompt_version)',
            'tokens': sonnet_resp,
        }

    # stage 'analyzed' 진행 — 동일 (ticker, accession, document_type)에 stage='analyzed' 새 행 추가
    db.upsert_filing(
        ticker=filing['ticker'],
        accession_number=filing['accession_number'],
        cik=filing['cik'],
        document_type=filing['document_type'],
        stage='analyzed',
        form_item=filing['form_item'],
        filed_at=filing['filed_at'],
        amc_or_bmo=filing['amc_or_bmo'],
        severity=filing['severity'],
        source_url=filing['source_url'],
        metadata_json=json.dumps({'parent_filing_id': filing_id, 'prompt_version': pv},
                                  ensure_ascii=False),
    )

    return {
        'filing_id': filing_id,
        'ticker': filing['ticker'],
        'analyzed': True,
        'tokens': sonnet_resp,
        'prompt_version': pv,
    }


# ─── Phase 6: transcript 풀 번역 (Haiku 4.5) ───
@api_retry
def _call_haiku_long(messages: list[dict], system_prompt: str, max_tokens: int = 16000) -> dict:
    """Haiku 4.5 풀 번역용 — max_tokens 16K (Haiku 4.5 한도)."""
    client = get_anthropic_client()
    resp = client.messages.create(
        model=TRANSLATION_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=messages,
    )
    return {
        'text': '\n'.join(b.text for b in resp.content if b.type == 'text'),
        'input_tokens': resp.usage.input_tokens,
        'output_tokens': resp.usage.output_tokens,
        'stop_reason': resp.stop_reason,
    }


def translate_transcript(transcript_id: int) -> dict:
    """transcripts 1건 한국어 풀 번역. translated_kr 미설정 행만 처리.

    분할 호출 전략 (max_tokens 16K 도달 회피):
    - prepared와 qa를 **별도 호출**해 합치기. 각 호출 max_tokens=16K (Haiku 한도).
    - 결과 합쳐서 translated_kr에 저장.

    DRY_RUN=1 이면 Haiku 호출 없이 prompt 빌드 + 토큰 추정만.
    """
    db.init_db()
    conn = db.get_conn()
    try:
        row = conn.execute('SELECT * FROM transcripts WHERE id=?', (transcript_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return {'error': f'transcript_id={transcript_id} 없음'}
    row = dict(row)
    if row.get('translated_kr'):
        return {'skip': True, 'reason': 'already translated', 'transcript_id': transcript_id}

    prepared = row.get('prepared_remarks') or ''
    qa = row.get('qa') or ''
    if not prepared and not qa:
        return {'skip': True, 'reason': 'empty content', 'transcript_id': transcript_id}

    pv = transcript_translation_prompt_version()

    if DRY_RUN:
        try:
            import tiktoken
            enc = tiktoken.get_encoding('cl100k_base')
            sys_tokens = len(enc.encode(SYSTEM_TRANSLATION_TRANSCRIPT))
            prep_tokens = len(enc.encode(prepared))
            qa_tokens = len(enc.encode(qa))
        except Exception:
            sys_tokens = prep_tokens = qa_tokens = -1
        return {
            'transcript_id': transcript_id,
            'dry_run': True,
            'system_tokens': sys_tokens,
            'prepared_input_tokens': prep_tokens,
            'qa_input_tokens': qa_tokens,
            'prompt_version': pv,
            'prepared_chars': len(prepared),
            'qa_chars': len(qa),
        }

    # 1) Prepared Remarks 호출
    prepared_resp = None
    if prepared:
        prepared_resp = _call_haiku_long(
            build_prepared_messages(prepared),
            SYSTEM_TRANSLATION_TRANSCRIPT,
            max_tokens=16000,
        )

    # 2) Q&A 호출 — 길이에 따라 자동 청크 분할 (각 청크 16K output 한도 안에서 풀 보존)
    qa_resps: list[dict] = []
    qa_chunks: list[str] = _chunk_qa_text(qa) if qa else []
    for i, chunk in enumerate(qa_chunks):
        if not chunk:
            continue
        msgs = build_qa_chunk_messages(chunk, i, len(qa_chunks))
        resp = _call_haiku_long(msgs, SYSTEM_TRANSLATION_TRANSCRIPT, max_tokens=16000)
        qa_resps.append(resp)

    # 결과 합치기
    parts = []
    if prepared_resp and prepared_resp['text']:
        parts.append(prepared_resp['text'])
    for r in qa_resps:
        if r.get('text'):
            parts.append(r['text'])
    translated_full = '\n\n'.join(parts)

    total_input = (prepared_resp['input_tokens'] if prepared_resp else 0) + sum(
        r['input_tokens'] for r in qa_resps)
    total_output = (prepared_resp['output_tokens'] if prepared_resp else 0) + sum(
        r['output_tokens'] for r in qa_resps)

    db.update_transcript_translation(
        transcript_id=transcript_id,
        translated_kr=translated_full,
        prompt_version_translation=pv,
        translation_model=TRANSLATION_MODEL,
        translation_input_tokens=total_input,
        translation_output_tokens=total_output,
    )

    return {
        'transcript_id': transcript_id,
        'translated': True,
        'prepared': {
            'input_tokens': prepared_resp['input_tokens'] if prepared_resp else 0,
            'output_tokens': prepared_resp['output_tokens'] if prepared_resp else 0,
            'stop_reason': prepared_resp['stop_reason'] if prepared_resp else None,
        } if prepared_resp else None,
        'qa_chunks': [{
            'input_tokens': r['input_tokens'],
            'output_tokens': r['output_tokens'],
            'stop_reason': r['stop_reason'],
        } for r in qa_resps],
        'qa_chunk_count': len(qa_chunks),
        'total_input_tokens': total_input,
        'total_output_tokens': total_output,
        'prompt_version': pv,
    }


def translate_pending_transcripts(limit: int = 3) -> list[dict]:
    """미번역 transcripts 일괄 처리. 비용 보호용 limit 작게."""
    db.init_db()
    rows = db.get_pending_translation_transcripts(limit=limit)
    results = []
    for r in rows:
        try:
            results.append(translate_transcript(r['id']))
        except Exception as e:
            logger.error(f'transcript {r["id"]} 번역 실패: {e}')
            results.append({'transcript_id': r['id'], 'error': str(e)})
    return results


def process_pending(limit: int = 5) -> list[dict]:
    """stage='fetched'인 filings 중 분석 필요한 것들 처리."""
    db.init_db()
    conn = db.get_conn()
    try:
        # severity != INFO 인 fetched filings 중 아직 analyzed 단계 없는 것
        rows = conn.execute(
            """
            SELECT f.id FROM filings f
            WHERE f.stage = 'fetched'
              AND f.severity IN ('CRITICAL', 'HIGH', 'NORMAL')
              AND NOT EXISTS (
                SELECT 1 FROM filings f2
                WHERE f2.ticker = f.ticker
                  AND f2.accession_number = f.accession_number
                  AND f2.document_type = f.document_type
                  AND f2.stage = 'analyzed'
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
            results.append(process_filing(r['id']))
        except Exception as e:
            logger.error(f"filing {r['id']} 분석 실패: {e}")
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
        result = process_filing(args.filing_id)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:3000])
    elif args.pending:
        result = process_pending()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:3000])
    else:
        p.print_help()
