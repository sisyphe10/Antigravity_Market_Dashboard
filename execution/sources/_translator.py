"""SemiAnalysis 등 영문 블로그/뉴스 본문 한국어 번역.

earnings_bot.translator._call_haiku_long 를 재사용 (Haiku 4.5, max_tokens 16K).
시스템 프롬프트는 컨퍼런스콜 transcript 와 달리 IT/반도체/AI 인프라 분석글 톤.

청크 분할: 영문 본문이 길면 자연 경계(빈 줄, 문장)에서 ~22K chars씩 자름.
"""
from __future__ import annotations

import logging
import os
import re
import sys

# earnings_bot 모듈 import 위해 execution/ 경로 추가
_EXECUTION_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _EXECUTION_DIR not in sys.path:
    sys.path.insert(0, _EXECUTION_DIR)

logger = logging.getLogger(__name__)

# ── 시스템 프롬프트 (SemiAnalysis 톤) ───────────────────────────────────
SYSTEM_TRANSLATION_TECH_BLOG = """당신은 미국 IT/반도체/AI 인프라 분석 블로그(SemiAnalysis 등)를 한국 자산운용역을 위해 번역하는 전문 번역가입니다.

## 출력 형식 (텔레그램 HTML)

원문의 구조(섹션 헤더 / 단락 / 리스트 / 도표 캡션)를 살리되 한국어로 풀 번역합니다. 출력은 텔레그램이 지원하는 HTML 태그만 사용:
- 섹션 헤더 (원문 ## 또는 굵은 단락 시작) → `<b><u>섹션 제목</u></b>`
- 단락 내 강조 → `<b>...</b>`
- 인용/캡션 → `<i>[그림: ...]</i>` 또는 `<i>...</i>`
- 리스트 항목 → 줄 시작 `• ` 또는 `- ` 그대로
- 본문 단락 사이는 빈 줄 1개

**금지 태그**: `<h1>`, `<h2>`, `<p>`, `<div>`, `<ul>`, `<li>` (텔레그램이 무시함). 반드시 위 4개 태그만 사용.

## 번역 규칙

1. **존댓말**: -습니다 체로 통일. 격식 있는 비즈니스 한국어.

2. **고유명사 영문 유지**:
   - 회사명: NVIDIA, AMD, Intel, TSMC, SK hynix, Samsung, Meta, OpenAI, Anthropic, xAI, Tesla 등 그대로
   - 제품/아키텍처: GB200 NVL72, H100, H200, B100, MI300, Blackwell, Hopper, Rubin, Trainium, HBM3E, DDR5, CoWoS 등 그대로
   - 사람 이름: Jensen Huang, Sam Altman, Elon Musk 등 영문 유지 (한국에서 통용되는 음역도 허용)
   - 지명: Memphis, Mississippi, Greater China 등 영문 유지 (서울/중국 같은 통용 한국어는 OK)

3. **금융/기술 약어 영문 유지**:
   - 금융: EPS, FCF, capex, opex, ARR, YoY, QoQ, FY25, bps, IPO, M&A 등
   - 기술: AI, ML, LLM, RL, FLOPS, GPU, ASIC, DC (datacenter), MW, GW, TDP, ROCE 등
   - 단위: $4.5B, 300MW, 2.3GW, 122일 등 원문 그대로

4. **자연스러운 한국어**:
   - 영어 어순 그대로 직역 금지
   - 긴 영문 한 문장 → 한국어 2~3개 문장으로 분할 OK
   - "you know", "I mean" 같은 필러는 생략

5. **숫자/단위 정확성**: 가이던스/수치는 절대 변형 금지.

6. **이미지/도표**: `<figure>`/`<figcaption>` 은 `<i>[그림: 캡션 한국어 번역]</i>` 형식. 원문에 캡션이 없으면 `<i>[그림]</i>` 만.

7. **외부 링크**: 본문 내 링크는 텍스트만 살리고 URL 은 제거 (텔레그램 메시지에 URL 폭주 방지).

8. **Privacy Policy / Terms / Subscribe CTA**: 등장하면 번역 생략 (본문 끝 footer 패턴).

9. **길이**: 줄임 금지. 원문 모든 분석 단락을 번역. 출력 끝에 "[이하 생략]" 등 메타 안내 금지 — 본문 마지막 문단으로 자연 종료.

## 출력 시작

번역 본문만 출력. 도입부에 "다음은 ... 번역입니다." 같은 메타 멘트 절대 금지.
"""


# ── Haiku 호출 (earnings_bot.translator 의 _call_haiku_long 재사용) ─────
def _call_haiku(messages: list[dict], system_prompt: str, max_tokens: int = 16000) -> dict:
    """Haiku 4.5 호출. earnings_bot.translator._call_haiku_long 의 얇은 위임."""
    from earnings_bot.translator import _call_haiku_long
    return _call_haiku_long(messages, system_prompt, max_tokens=max_tokens)


# ── 청크 분할 ─────────────────────────────────────────────────────────
TRANSLATE_CHUNK_MAX_CHARS = 22000


def _chunk_text(text: str, max_chars: int = TRANSLATE_CHUNK_MAX_CHARS) -> list[str]:
    """본문을 자연 경계(빈 줄 → 문장 마침표 → 어절)에서 분할."""
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        # 절반 위치부터 max_chars 사이에서 가장 가까운 빈 줄
        search_start = len(remaining) // 2
        idx = remaining.find('\n\n', search_start, max_chars + 2000)
        if idx == -1:
            # 폴백: 문장 끝 마침표
            idx = remaining.rfind('. ', search_start, max_chars)
        if idx == -1:
            # 폴백: 줄바꿈
            idx = remaining.rfind('\n', search_start, max_chars)
        if idx == -1 or idx <= search_start:
            idx = max_chars
        chunks.append(remaining[:idx].strip())
        remaining = remaining[idx:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _build_messages(chunk: str, title: str, chunk_index: int, total_chunks: int) -> list[dict]:
    """청크별 user 메시지 빌드."""
    if total_chunks == 1:
        header = f'다음은 영문 IT/반도체/AI 인프라 분석글입니다. 시스템 프롬프트의 규칙대로 한국어로 풀 번역하세요.\n\n[원문 제목] {title}\n\n[원문 본문]\n{chunk}'
    elif chunk_index == 0:
        header = f'다음은 영문 IT/반도체/AI 인프라 분석글의 {total_chunks}개 청크 중 첫 번째입니다. 본문 시작 부분이며 뒤에 청크가 이어집니다. 끝맺음 문구 없이 자연스럽게 종료하세요.\n\n[원문 제목] {title}\n\n[원문 본문 청크 1/{total_chunks}]\n{chunk}'
    elif chunk_index == total_chunks - 1:
        header = f'다음은 영문 IT/반도체/AI 인프라 분석글의 {total_chunks}개 청크 중 마지막({chunk_index + 1})입니다. 이전 청크에서 이어집니다. 도입부 멘트 없이 본문만 번역하세요.\n\n[원문 제목] {title}\n\n[원문 본문 청크 {chunk_index + 1}/{total_chunks}]\n{chunk}'
    else:
        header = f'다음은 영문 IT/반도체/AI 인프라 분석글의 {total_chunks}개 청크 중 {chunk_index + 1}번째입니다. 앞뒤로 청크가 이어집니다. 도입부/끝맺음 멘트 없이 본문만 번역하세요.\n\n[원문 제목] {title}\n\n[원문 본문 청크 {chunk_index + 1}/{total_chunks}]\n{chunk}'
    return [{'role': 'user', 'content': header}]


# ── 공개 API ──────────────────────────────────────────────────────────
def translate_to_korean(text: str, title: str = '', dry_run: bool = False) -> dict:
    """영문 본문을 한국어로 번역. 자동 청크 분할.

    Returns:
        {
            'text': str,  # 합쳐진 한국어 번역
            'chunks': int,
            'input_tokens': int,
            'output_tokens': int,
            'dry_run': bool,
        }
    """
    chunks = _chunk_text(text)
    if dry_run:
        return {
            'text': f'[DRY_RUN] {len(chunks)}개 청크, 총 {len(text)} chars',
            'chunks': len(chunks),
            'input_tokens': 0,
            'output_tokens': 0,
            'dry_run': True,
        }

    parts: list[str] = []
    total_in = 0
    total_out = 0
    for i, chunk in enumerate(chunks):
        msgs = _build_messages(chunk, title, i, len(chunks))
        resp = _call_haiku(msgs, SYSTEM_TRANSLATION_TECH_BLOG, max_tokens=16000)
        if resp.get('text'):
            parts.append(resp['text'])
        total_in += resp.get('input_tokens', 0)
        total_out += resp.get('output_tokens', 0)
        logger.info(
            f'translate chunk {i + 1}/{len(chunks)}: '
            f'in={resp.get("input_tokens")} out={resp.get("output_tokens")} stop={resp.get("stop_reason")}'
        )

    return {
        'text': '\n\n'.join(parts),
        'chunks': len(chunks),
        'input_tokens': total_in,
        'output_tokens': total_out,
        'dry_run': False,
    }


# ── IR 보도자료 제목 배치 번역 (foreign_ir 어댑터용) ──────────────────────
SYSTEM_TRANSLATION_IR_TITLE = """당신은 해외 상장사의 IR 보도자료 제목을 한국 자산운용역을 위해 번역하는 전문 번역가입니다.

번호가 매겨진 영문 제목 목록을 받아, 각 제목을 한국어로 자연스럽게 번역합니다.

## 번역 규칙
1. 회사명/티커/제품명/사람 이름은 영문 유지 (NVIDIA, TSMC, GB200, Jensen Huang 등).
2. 금융/실적 약어·표기는 원형 유지: EPS, FCF, EBITDA, FY26, Q1, YoY, capex, GW, MW, bps, IPO, M&A, ADR 등.
3. 숫자·통화·단위는 절대 변형 금지 ($4.5B, 30%, 122일 등 그대로).
4. 비즈니스 관용 표현 직역 금지: tailwind→순풍, headwind→부담, secular→구조적, pent-up demand→이연 수요, guidance→가이던스, ramp→양산 가속.
5. 제목체(명사형 어미)로 간결하게. 예: "Q1 2026 Results" → "2026년 1분기 실적".
6. 의역 허용하되 의미 보존.

## 출력 형식 (엄격)
- 입력과 정확히 같은 번호를 유지.
- 한 줄에 하나: `<번호>. <한국어 번역>`
- 번역문만 출력. 머리말/꼬리말/설명 절대 금지.
"""

_TITLE_LINE_RE = re.compile(r'^\s*(\d+)[.)\]]\s*(.+?)\s*$')
TITLE_BATCH_SIZE = 30


def translate_titles(titles: list[str], dry_run: bool = False) -> dict:
    """IR 보도자료 제목 목록을 한국어로 배치 번역.

    Args:
        titles: 영문 제목 리스트.
        dry_run: True 면 API 호출 없이 원문 반환.

    Returns:
        {
            'titles_kr': list[str],  # titles 와 같은 길이/순서 (실패 항목은 원문 유지)
            'input_tokens': int,
            'output_tokens': int,
            'dry_run': bool,
        }
    """
    if not titles:
        return {'titles_kr': [], 'input_tokens': 0, 'output_tokens': 0, 'dry_run': dry_run}
    if dry_run:
        return {'titles_kr': list(titles), 'input_tokens': 0, 'output_tokens': 0, 'dry_run': True}

    result: list[str] = list(titles)  # 기본값 = 원문 (파싱 실패 시 폴백)
    total_in = 0
    total_out = 0

    for batch_start in range(0, len(titles), TITLE_BATCH_SIZE):
        batch = titles[batch_start:batch_start + TITLE_BATCH_SIZE]
        numbered = '\n'.join(f'{i + 1}. {t}' for i, t in enumerate(batch))
        user_msg = (
            '다음 영문 보도자료 제목들을 시스템 프롬프트 규칙대로 한국어로 번역하세요. '
            '입력과 같은 번호로만 출력하세요.\n\n' + numbered
        )
        try:
            resp = _call_haiku(
                [{'role': 'user', 'content': user_msg}],
                SYSTEM_TRANSLATION_IR_TITLE,
                max_tokens=4096,
            )
        except Exception as e:
            logger.error(f'translate_titles 배치 실패 (start={batch_start}): {e}')
            continue
        total_in += resp.get('input_tokens', 0)
        total_out += resp.get('output_tokens', 0)

        # 번호별 파싱 → 해당 인덱스에 매핑
        parsed: dict[int, str] = {}
        for line in (resp.get('text') or '').splitlines():
            m = _TITLE_LINE_RE.match(line)
            if m:
                n = int(m.group(1))
                if 1 <= n <= len(batch):
                    parsed[n - 1] = m.group(2).strip()
        for local_idx, kr in parsed.items():
            if kr:
                result[batch_start + local_idx] = kr
        logger.info(
            f'translate_titles 배치 {batch_start}-{batch_start + len(batch)}: '
            f'parsed={len(parsed)}/{len(batch)} in={resp.get("input_tokens")} out={resp.get("output_tokens")}'
        )

    return {
        'titles_kr': result,
        'input_tokens': total_in,
        'output_tokens': total_out,
        'dry_run': False,
    }


# ── 뉴스 제목+요약 (trendforce 등 다이제스트 어댑터용) ─────────────────────
SYSTEM_NEWS_SUMMARY = """당신은 영문 IT/반도체/AI/테크 뉴스를 한국 자산운용역을 위해 한국어로 요약하는 전문 애널리스트입니다.

영문 기사 1건(제목 + 본문)을 받아, (1) 제목을 한국어로 번역하고 (2) 핵심을 3~5개 불릿으로 요약합니다.

## 규칙
1. **고유명사 영문 유지**: 회사/제품/사람/지명은 영문 그대로 (NVIDIA, TSMC, SK hynix, Samsung, HBM4, GB200, Jensen Huang, Arizona 등).
2. **약어 영문 유지**: EPS, FCF, capex, YoY, QoQ, FY26, bps, GW, MW, AI, GPU, HBM, DRAM, NAND, foundry 등.
3. **숫자/단위 정확**: 매출·수율·가격·% 등 수치는 절대 변형 금지 ($40.2B, 65.5%, 10~20% 등 그대로).
4. **관용 표현**: tailwind→순풍, headwind→부담, secular→구조적, guidance→가이던스, ramp→양산 가속.
5. **불릿 내용**: 사실·수치 중심으로 압축. 기사에 없는 추측 금지. 각 불릿 1~2문장, 존댓말 명사형/평서형 혼용 가능.
6. 분량: 불릿 3~5개. 본문이 짧으면 2개도 허용.

## 출력 형식 (엄격)
첫 줄: `제목: <한국어 제목>`
다음 줄부터 불릿, 각 줄 `- ` 로 시작.
머리말/꼬리말/메타 멘트 절대 금지. 위 형식만 출력.
"""

_SUMMARY_TITLE_RE = re.compile(r'^\s*제목\s*[:：]\s*(.+?)\s*$')


def summarize_news_to_korean(title: str, body: str, dry_run: bool = False) -> dict:
    """영문 뉴스 1건 → 한국어 제목 + 불릿 요약.

    Args:
        title: 영문 제목.
        body:  영문 본문(평문, HTML 태그 제거된 상태 권장).
        dry_run: True 면 API 호출 없이 원문 기반 더미 반환.

    Returns:
        {
            'title_kr': str,        # 한국어 제목 (실패 시 원문)
            'summary_kr': str,      # 불릿 요약 ('- '로 시작하는 줄들, \n 결합)
            'input_tokens': int,
            'output_tokens': int,
            'dry_run': bool,
        }
    """
    if dry_run:
        return {
            'title_kr': title,
            'summary_kr': '- [DRY_RUN] 요약 생략',
            'input_tokens': 0, 'output_tokens': 0, 'dry_run': True,
        }

    # 본문이 너무 길면 앞부분만 (뉴스 1건은 보통 4K 이하라 충분)
    body_trimmed = (body or '')[:8000]
    user_msg = (
        '다음 영문 뉴스를 시스템 프롬프트 규칙대로 한국어 제목 + 불릿 요약으로 출력하세요.\n\n'
        f'[원문 제목] {title}\n\n[원문 본문]\n{body_trimmed}'
    )
    resp = _call_haiku(
        [{'role': 'user', 'content': user_msg}],
        SYSTEM_NEWS_SUMMARY,
        max_tokens=1500,
    )
    text = (resp.get('text') or '').strip()

    title_kr = title
    bullets: list[str] = []
    for line in text.splitlines():
        m = _SUMMARY_TITLE_RE.match(line)
        if m and title_kr == title:
            title_kr = m.group(1).strip()
            continue
        ls = line.strip()
        if ls.startswith(('-', '•', '*')):
            bullets.append('- ' + ls.lstrip('-•* ').strip())
        elif ls and bullets:
            # 불릿 줄바꿈 이어짐
            bullets[-1] += ' ' + ls
    summary_kr = '\n'.join(bullets) if bullets else (text or '- (요약 없음)')

    return {
        'title_kr': title_kr,
        'summary_kr': summary_kr,
        'input_tokens': resp.get('input_tokens', 0),
        'output_tokens': resp.get('output_tokens', 0),
        'dry_run': False,
    }
