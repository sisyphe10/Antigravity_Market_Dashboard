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
                             TRANSLATION_MODEL, AnalysisInput,
                             build_analysis_messages, build_translation_messages,
                             get_anthropic_client, prompt_version, skill_md_sha256)
from .retry_helper import api_retry
from .yoy_calculator import compute_yoy, format_table

logger = logging.getLogger(__name__)

DRY_RUN = os.getenv('EARNINGS_BOT_DRY_RUN', '').lower() in ('1', 'true', 'yes')


@api_retry
def _call_sonnet(messages: list[dict]) -> dict:
    """Sonnet 4.6 호출. system= 파라미터 필수. dict 반환 (text + usage)."""
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

    # primary_text 복원: edgartools v5는 accession_number로 직접 조회 가능 (find())
    from .attachment_parser import parse_filing
    from edgar import set_identity, find
    set_identity(os.getenv('SEC_EDGAR_USER_AGENT', 'Kimtaesik (kts77775@gmail.com)'))
    try:
        target_filing = find(filing['accession_number'])
    except Exception as e:
        return {'error': f"filing {filing['accession_number']} find() 실패: {e}"}
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
    db.insert_analysis(
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
