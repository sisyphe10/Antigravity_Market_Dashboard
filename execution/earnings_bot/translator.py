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
import re
from datetime import date, datetime, timezone

from . import db, headless_llm, ticker_registry
from .insider_signal import fetch_insider_window, format_appendix
from .prompt_builder import (ANALYSIS_MODEL, SYSTEM_ANALYSIS, SYSTEM_TRANSLATION,
                             SYSTEM_TRANSLATION_TRANSCRIPT, TRANSLATION_MODEL,
                             AnalysisInput, build_analysis_messages,
                             build_prepared_chunk_messages,
                             build_prepared_messages, build_qa_chunk_messages,
                             build_qa_messages,
                             build_transcript_translation_messages,
                             build_translation_messages, get_anthropic_client,
                             prompt_version, skill_md_sha256,
                             transcript_translation_prompt_version)


# 청크 분할: 한국어 출력이 ~1.5x 영문 chars로 늘어나므로
# 영문 22K chars (~7K input tokens) 정도가 16K output 한도 안전 상한.
QA_CHUNK_MAX_CHARS = 22000
PREPARED_CHUNK_MAX_CHARS = 22000


def _chunk_text(text: str, max_chars: int, boundaries: list[str]) -> list[str]:
    """텍스트를 자연 경계에서 분할.

    - max_chars 이하면 단일 청크
    - 그 이상이면 절반~max_chars 사이에서 boundaries 순서대로 매칭점 탐색
    - 모두 실패 시 max_chars 직전 가장 가까운 \\n 폴백, 그것도 없으면 max_chars
    """
    if not text or len(text) <= max_chars:
        return [text or '']

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        search_start = len(remaining) // 2
        idx = -1
        for marker in boundaries:
            idx = remaining.find(marker, search_start, max_chars + 2000)
            if idx != -1:
                break
        if idx == -1:
            idx = remaining.rfind('\n', search_start, max_chars)
        if idx == -1 or idx <= search_start:
            idx = max_chars
        chunks.append(remaining[:idx].strip())
        remaining = remaining[idx:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _chunk_qa_text(qa_text: str, max_chars: int = QA_CHUNK_MAX_CHARS) -> list[str]:
    return _chunk_text(qa_text, max_chars, ['\nOperator:', '\n\n'])


# 참석자 명단(200~500자)과 실제 발표(수천 자~) 사이의 경계.
# 실측: 정상 전문의 prepared 는 최소 3,059자(ALV), 날조된 것은 231·276자였다.
MIN_PREPARED_CHARS = 1_500


def _chunk_prepared_text(prepared_text: str, max_chars: int = PREPARED_CHUNK_MAX_CHARS) -> list[str]:
    return _chunk_text(prepared_text, max_chars, ['\n\n'])
from .retry_helper import api_retry
from .yoy_calculator import compute_yoy, format_table

logger = logging.getLogger(__name__)

DRY_RUN = os.getenv('EARNINGS_BOT_DRY_RUN', '').lower() in ('1', 'true', 'yes')


# ── 백엔드 스위치 (2026-08-18 headless 이관, 설계 v2) ─────────────
#   'api'(기본) = 기존 Anthropic API 경로 그대로 / 'headless' = 구독 claude CLI (0원).
#   env는 호출 시점에 읽는다 — .env 전환·롤백이 재기동 없이 다음 배치부터 적용되게.
def _analysis_backend() -> str:
    return os.getenv('EARNINGS_ANALYSIS_BACKEND', 'api').strip().lower()


def _translate_backend() -> str:
    return os.getenv('EARNINGS_TRANSLATE_BACKEND', 'api').strip().lower()


def _call_sonnet(messages: list[dict]) -> dict:
    """분석시트 호출 — 백엔드 디스패치. headless는 stamina를 타지 않는다(설계 C4:
    쿼터 메시지의 'rate limit' 문자열이 transient로 오판돼 5회 재시도되는 사고 차단)."""
    if _analysis_backend() == 'headless':
        return headless_llm.call_with_retry(SYSTEM_ANALYSIS, messages)
    return _call_sonnet_api(messages)


@api_retry
def _call_sonnet_api(messages: list[dict]) -> dict:
    """Sonnet API 호출. system= 파라미터 필수. dict 반환 (text + usage).

    모델 ID는 prompt_builder.ANALYSIS_MODEL 참조 (현재: claude-sonnet-4-5-20250929).
    """
    client = get_anthropic_client()
    resp = client.messages.create(
        model=ANALYSIS_MODEL,
        max_tokens=4000,
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


def _resolve_analysis_text(parsed) -> tuple[str, str]:
    """분석 입력 본문 선택. primary_text 가 실적 수치를 담고 있으면 그대로 사용한다.

    ARM 전례(2026-07-30): EX-99.1 이 수치 없는 짧은 커버 PR 이고 실적 본문은
    EX-99.2 주주서한(86KB)에 있어, primary_text 만 넣으면 분석시트가 전부
    "본문 미제공" 으로 나왔다. 강한 재무 신호가 부족할 때만 최장 EX-99 를 덧붙인다.

    반환: (본문, 선택 근거) — 근거는 로그·관측용.
    """
    from .attachment_parser import STRONG_EARNINGS_KEYWORDS, STRONG_EARNINGS_MIN_HITS

    def _hits(text: str) -> int:
        low = (text or '').lower()
        return sum(1 for k in STRONG_EARNINGS_KEYWORDS if k in low)

    primary = parsed.primary_text or ''
    primary_hits = _hits(primary)
    if primary_hits >= STRONG_EARNINGS_MIN_HITS:
        return primary, f'primary_text (신호 {primary_hits}개)'

    ex99 = {k: v for k, v in (parsed.exhibits or {}).items() if k.startswith('EX-99')}
    if not ex99:
        return primary, f'primary_text (EX-99 없음, 신호 {primary_hits}개)'

    key, text = max(ex99.items(), key=lambda kv: len(kv[1] or ''))
    ex_hits = _hits(text)
    if ex_hits <= primary_hits:
        return primary, f'primary_text (폴백 미채택: {key} 신호 {ex_hits}개)'

    # 커버 PR 은 제목·발표 맥락을 담고 있어 함께 보존한다.
    merged = f'{primary}\n\n[{key}]\n{text}' if primary else text
    return merged, f'primary_text + {key} (신호 {primary_hits} -> {ex_hits}개)'


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
        # filing_date에서 추정: 45일 lag 빼면 직전 분기 종료 = 발표 분기
        from datetime import timedelta
        try:
            fd = date.fromisoformat(event_date_str)
            anchor = fd - timedelta(days=45)
            fy = anchor.year
            fq = (anchor.month - 1) // 3 + 1
        except Exception:
            fy, fq = datetime.now(tz=timezone.utc).year, 1

    # YoY 표 (기계 산출)
    analysis_text, text_source = _resolve_analysis_text(parsed)
    logger.info(f"[{filing['ticker']}] 분석 본문 선택: {text_source} ({len(analysis_text):,}자)")

    yoy_snap = compute_yoy(filing['ticker'], fy, fq, press_release_text=analysis_text)
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
        primary_text=analysis_text,
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

    # 생성 주체 이력 (설계 C1/C2): prompt_version은 내용 해시로 불변,
    # 백엔드·실사용 모델은 행 단위 model 필드에 '@headless' 접미로 기록
    _model_label = (f"{sonnet_resp.get('resolved_model', '')}@headless"
                    if sonnet_resp.get('backend') == 'headless' else ANALYSIS_MODEL)

    # 분석 결과는 filing_analyses 전용 테이블에 저장 (Codex 권고)
    # INSERT OR IGNORE 가 None 반환 시 = 동일 (filing_id, prompt_version) 중복 → analyzed stage 진행 X
    analysis_row_id = db.insert_analysis(
        filing_id=filing_id,
        analysis_kr=analysis_text,
        yoy_md=yoy_md,
        insider_md=insider_md,
        prompt_version=pv,
        analysis_model=_model_label,
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


# ─── Phase 6: transcript 풀 번역 (Haiku 4.5 / headless Sonnet) ───
def _call_haiku_long(messages: list[dict], system_prompt: str, max_tokens: int = 16000) -> dict:
    """전문 청크 번역 호출 — 백엔드 디스패치 (headless는 stamina 미적용, 설계 C4).
    headless엔 max_tokens 제어가 없다 — 입력 기준 청크 분할(22K자)이 출력 길이를 가드."""
    if _translate_backend() == 'headless':
        return headless_llm.call_with_retry(system_prompt, messages)
    return _call_haiku_long_api(messages, system_prompt, max_tokens)


@api_retry
def _call_haiku_long_api(messages: list[dict], system_prompt: str, max_tokens: int = 16000) -> dict:
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

    # ── 번역 전 게이트 (2026-07-31): 전문이 아닌 문서를 번역기에 넣지 않는다.
    #    프롬프트가 "전문 형식으로 출력하라"를 강제하므로, 기사를 넣으면 모델이
    #    발언을 만들어낼 여지가 생긴다. 입력 단계에서 끊는 게 유일한 확실한 방어.
    from .transcript_gate import check_collect, check_translation
    _fa = ''
    _c = db.get_conn()
    try:
        _r = _c.execute('SELECT filed_at FROM filings WHERE id=?',
                        (row.get('filing_id'),)).fetchone()
        _fa = (dict(_r).get('filed_at') or '')[:10] if _r else ''
    finally:
        _c.close()
    _g = check_collect(row.get('source_url') or '', prepared, qa, _fa)
    if not _g.ok:
        logger.warning(f'[translator] GATE REJECT transcript={transcript_id} {_g.reasons}')
        return {'skip': True, 'transcript_id': transcript_id,
                'reason': 'gate_reject', 'gate_reasons': _g.reasons}

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

    # 1) Prepared Remarks — 길이에 따라 자동 청크 분할 (qa와 동일 max 16K output 가드)
    prepared_resps: list[dict] = []
    # ★ stub prepared 차단 (2026-07-31): 참석자 명단만 있는 섹션을 번역시키면
    #   모델이 발표 내용을 통째로 지어낸다(RGTI·CEG 실측). 수집 실패는 빈칸으로 둔다.
    if prepared and len(prepared) < MIN_PREPARED_CHARS:
        logger.warning(
            f'[translator] transcript={transcript_id} prepared {len(prepared)}자 — '
            f'참석자 명단 수준이라 번역하지 않음(날조 방지). Q&A 만 번역한다.')
        prepared = ''
    prepared_chunks: list[str] = _chunk_prepared_text(prepared) if prepared else []
    for i, chunk in enumerate(prepared_chunks):
        if not chunk:
            continue
        msgs = build_prepared_chunk_messages(chunk, i, len(prepared_chunks))
        resp = _call_haiku_long(msgs, SYSTEM_TRANSLATION_TRANSCRIPT, max_tokens=16000)
        prepared_resps.append(resp)

    # 2) Q&A 호출 — 길이에 따라 자동 청크 분할
    qa_resps: list[dict] = []
    qa_chunks: list[str] = _chunk_qa_text(qa) if qa else []
    for i, chunk in enumerate(qa_chunks):
        if not chunk:
            continue
        msgs = build_qa_chunk_messages(chunk, i, len(qa_chunks))
        resp = _call_haiku_long(msgs, SYSTEM_TRANSLATION_TRANSCRIPT, max_tokens=16000)
        qa_resps.append(resp)

    # 결과 합치기 — 섹션 헤더는 모델 출력에서 제거하고 **코드가 결정적으로 조립**
    # (2026-08-03: 모델의 헤더 표기 변형·중복·누락이 구조 검증을 무력화하는 것 차단.
    #  프롬프트의 헤더 지시는 유지 — 모델 동작 안정성 목적, 출력물은 여기서 정규화)
    from .transcript_gate import PREP_HEADER, QA_HEADER

    def _strip_headers(t: str) -> str:
        return re.sub(r'^[ \t]*##[ \t]*(?:경영진 발표|Q\s*&\s*A[^\n]*)[ \t]*$\n?',
                      '', t, flags=re.MULTILINE).strip()

    prep_kr = '\n\n'.join(_strip_headers(r['text']) for r in prepared_resps
                          if r.get('text') and _strip_headers(r['text']))
    qa_kr = '\n\n'.join(_strip_headers(r['text']) for r in qa_resps
                        if r.get('text') and _strip_headers(r['text']))
    parts = []
    if prep_kr:
        parts.append(f'{PREP_HEADER}\n\n{prep_kr}')
    if qa_kr:
        parts.append(f'{QA_HEADER}\n\n{qa_kr}')
    translated_full = '\n\n'.join(parts)

    # 입력 토큰 = 직접 입력 + 캐시 생성/히트 합산 (2026-08-18: headless CLI는 입력을
    # 프롬프트 캐시로 계상해 inputTokens가 1로 나온다 — 실측. API 경로는 캐시 키 없음→0)
    def _in_tokens(r: dict) -> int:
        return (r['input_tokens'] + r.get('cache_creation_input_tokens', 0)
                + r.get('cache_read_input_tokens', 0))

    total_input = sum(_in_tokens(r) for r in prepared_resps + qa_resps)
    total_output = sum(r['output_tokens'] for r in prepared_resps) + sum(
        r['output_tokens'] for r in qa_resps)

    # ── 청크 단위 검사 (2026-07-31): 합본 전체 검사만으로는 한 청크의 환각·거부가
    #    나머지 정상 청크에 희석되어 통과할 수 있다. sentinel·거부문구는 청크별로 본다.
    from .transcript_gate import SENTINEL, REFUSAL_MARKERS
    for _r in prepared_resps + qa_resps:
        _t = _r.get('text') or ''
        _ts = _t.strip()
        if ((_ts.startswith(SENTINEL) and len(_ts) < 1200)
                or (len(_ts) < 1500 and any(mk in _ts for mk in REFUSAL_MARKERS))):
            logger.warning(
                f'[translator] CHUNK GATE REJECT transcript={transcript_id} — '
                f'청크에 sentinel/거부문구: {_t[:120]!r}')
            return {'transcript_id': transcript_id, 'translated': False,
                    'reason': 'chunk_gate_reject', 'chunk_head': _t[:200]}

    # ── 번역 후 게이트: sentinel / 거부문구 / 분량비율 / 섹션 구조 / 화자 귀속 역대조
    _og = check_translation(prepared + '\n' + qa, translated_full,
                            prepared=prepared, qa=qa)
    if not _og.ok:
        logger.warning(
            f'[translator] OUTPUT GATE REJECT transcript={transcript_id} '
            f'{_og.reasons} info={_og.info}')
        return {'transcript_id': transcript_id, 'translated': False,
                'reason': 'output_gate_reject', 'gate_reasons': _og.reasons,
                'gate_info': _og.info}

    # 생성 주체 이력 (설계 C1/C2) — headless면 '실사용모델@headless'로 기록
    _all_resps = prepared_resps + qa_resps
    _tm_label = TRANSLATION_MODEL
    if _all_resps and _all_resps[0].get('backend') == 'headless':
        _tm_label = f"{_all_resps[0].get('resolved_model', '')}@headless"

    db.update_transcript_translation(
        transcript_id=transcript_id,
        translated_kr=translated_full,
        prompt_version_translation=pv,
        translation_model=_tm_label,
        translation_input_tokens=total_input,
        translation_output_tokens=total_output,
    )

    return {
        'transcript_id': transcript_id,
        'translated': True,
        'prepared_chunks': [{
            'input_tokens': r['input_tokens'],
            'output_tokens': r['output_tokens'],
            'stop_reason': r['stop_reason'],
        } for r in prepared_resps],
        'prepared_chunk_count': len(prepared_chunks),
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


def translate_pending_transcripts(limit: int = 3, oldest_first: bool = False) -> list[dict]:
    """미번역 transcripts 일괄 처리. 비용 보호용 limit 작게.

    oldest_first=True = 새벽 백로그 모드 (설계 C9 기아 방지).
    ★Auth/Quota 터미널 예외는 삼키지 않고 재전파한다 (설계 C4) —
      삼키면 다음 항목도 계속 호출해 쿼터 소진 상태에서 헛돈다.
    """
    db.init_db()
    rows = db.get_pending_translation_transcripts(limit=limit, oldest_first=oldest_first)
    results = []
    for r in rows:
        try:
            results.append(translate_transcript(r['id']))
        except (headless_llm.HeadlessAuthError, headless_llm.HeadlessQuotaError):
            raise
        except Exception as e:
            logger.error(f'transcript {r["id"]} 번역 실패: {e}')
            results.append({'transcript_id': r['id'], 'error': str(e)})
    return results


def process_pending(limit: int = 5, oldest_first: bool = False) -> list[dict]:
    """stage='fetched'인 filings 중 분석 필요한 것들 처리.

    oldest_first=True = 새벽 백로그 모드 (설계 C9). 터미널 예외 재전파는 위와 동일.
    """
    db.init_db()
    order = 'ASC' if oldest_first else 'DESC'
    conn = db.get_conn()
    try:
        # severity != INFO 인 fetched filings 중 아직 analyzed 단계 없는 것
        rows = conn.execute(
            f"""
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
            ORDER BY f.filed_at {order} LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    results = []
    for r in rows:
        try:
            results.append(process_filing(r['id']))
        except (headless_llm.HeadlessAuthError, headless_llm.HeadlessQuotaError):
            raise
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
