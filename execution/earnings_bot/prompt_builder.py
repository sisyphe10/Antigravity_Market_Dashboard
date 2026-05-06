"""prompt builder — earnings-analysis SKILL.md 임베드 + 1-page sheet 템플릿.

Codex 권고:
- prompt_version은 SKILL.md sha256 + bot 자체 prompt sha256 합산으로 산출
- 각 출력에 prompt_version 태깅 (Notion 저장 시 metadata)
- prompt caching 활용 (SKILL.md는 5분 TTL이지만 분기당 1회 write 비용만 발생)

prompt 구조:
  system: bot 정체성 + 출력 형식 + 한국 자산운용 컨텍스트
  user (cache): SKILL.md 전문 (5,406 tokens)
  user: 분석할 filing 데이터 + YoY + insider 부록
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

SKILL_PATH = os.path.expanduser('~/.claude/skills/earnings-analysis/SKILL.md')

ANALYSIS_MODEL = 'claude-sonnet-4-5-20250929'      # 분석용
TRANSLATION_MODEL = 'claude-haiku-4-5-20251001'    # 번역용

BOT_PROMPT_VERSION_TAG = 'earnings_bot_v1.0'


# ─── 시스템 프롬프트 (분석용) — Anthropic API system= 파라미터로 전달 ───
# placeholder 사용 안 함 — 구체적 데이터(ticker/fiscal/yoy/insider)는 user 메시지에 담음.
SYSTEM_ANALYSIS = """당신은 한국 자산운용사의 미국 주식 분석 어시스턴트입니다. 미국 상장사의 분기 실적 발표(8-K Item 2.02 / 6-K)를 받아 한국어로 1-page 분석 시트를 작성합니다.

## 출력 형식 (1-page sheet, 한국어, 정확히 이 헤더 순서로)

### [TICKER] [FY] Q[FQ] 실적 요약

**한 줄 핵심**
(실적 beat/miss + 가장 중요한 변화 1개. 1문장.)

**주요 숫자**
(제공된 YoY 표를 그대로 마크다운 표로 출력. 절대 숫자를 다시 계산하거나 변경하지 마세요.)

**가이던스 변화**
(다음 분기/연간 가이던스가 전 분기 대비 어떻게 바뀌었는지. 변화 없으면 "변경 없음"이라 명시.)

**경영진 코멘트 핵심**
- (불릿 3~5개. 보도자료 본문 기준. 각 불릿은 1줄로.)

**리스크/주의사항**
- (불릿 1~3개. 공시에서 언급된 부정적 시그널 위주.)

**내부자 거래 시그널**
(제공된 내부자 거래 부록을 그대로 인용)

**투자 함의 (한국 운용 관점)**
(1~2문장. 매수/매도 추천 금지. "주가 영향" 표현 OK.)

## 톤·스타일 (필수 준수)
- 한국어 존댓말 (-요/-습니다 체)
- 한국 펀드매니저 대상이므로 EPS/FCF/YoY/QoQ 등 영어 약어는 그대로 사용
- "~것으로 보입니다" "~할 가능성이 있어 보입니다" 같은 회피성 헤지 표현 최소화. 사실은 단정적으로 진술.
- 가이던스·숫자 인용 시 "회사 발표 기준" 명시
- 전체 200~500단어 안에 들어가도록 압축

## 절대 규칙 (위반 시 출력 무효)
1. YoY 표 숫자는 입력으로 받은 표 그대로 사용. 다시 계산해서 다른 숫자를 만들지 마세요.
2. 공시에 명시되지 않은 사실은 "공시에 명시되지 않음"으로 표기. 추측 금지.
3. 매수/매도/목표주가 추천 금지. 분석만.
4. 영어 본문은 한국어로 번역해서 제공. 회사 공식 영어 표현은 괄호 안에 병기 가능 (예: "잉여현금흐름(Free Cash Flow)").
"""

# ─── 시스템 프롬프트 (번역용 — 짧은 헤드라인 텔레그램용) ───
SYSTEM_TRANSLATION = """당신은 한국어 번역기입니다. 영어 보도자료/실적 발표 문장을 한국어로 자연스럽게 번역합니다.

규칙:
- 한국어 존댓말 (-요/-습니다)
- 영어 약어(EPS, FCF 등) 그대로 유지
- 숫자/통화 단위는 원문 그대로 (예: "$4.5B", "+12% YoY")
- 의역 OK. 단, 가이던스/숫자는 정확히 보존
"""


@dataclass
class AnalysisInput:
    ticker: str
    fiscal_year: int
    fiscal_quarter: int
    document_type: str        # '8-K' / '6-K'
    severity: str             # 'CRITICAL' / 'HIGH' / 'NORMAL' / 'INFO'
    primary_text: str         # EX-99.1 본문 (보도자료)
    yoy_table_md: str         # yoy_calculator.format_table 결과
    insider_appendix_md: str  # insider_signal.format_appendix 결과
    source_url: str | None


def _read_skill_md() -> str:
    if not os.path.exists(SKILL_PATH):
        return ''
    with open(SKILL_PATH, encoding='utf-8') as f:
        return f.read()


def skill_md_sha256() -> str:
    content = _read_skill_md()
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]


def prompt_version() -> str:
    """SKILL.md sha + bot prompt 결합."""
    bot_sha = hashlib.sha256(
        (SYSTEM_ANALYSIS + SYSTEM_TRANSLATION + BOT_PROMPT_VERSION_TAG).encode('utf-8')
    ).hexdigest()[:16]
    return f'{BOT_PROMPT_VERSION_TAG}_skill-{skill_md_sha256()}_bot-{bot_sha}'


def build_analysis_messages(inp: AnalysisInput) -> list[dict]:
    """Anthropic Messages API 형식. SKILL.md는 cache_control로 prompt caching 활용."""
    skill_md = _read_skill_md()
    user_input = f"""[분석 대상]
ticker: {inp.ticker}
회계 기간: FY{inp.fiscal_year} Q{inp.fiscal_quarter}
문서 유형: {inp.document_type} (severity={inp.severity})
원문 URL: {inp.source_url or 'N/A'}

[기계 산출 YoY 표 — 그대로 인용할 것]
{inp.yoy_table_md}

[내부자 거래 부록 — 그대로 인용할 것]
{inp.insider_appendix_md}

[보도자료 본문 (EX-99.1 등)]
{inp.primary_text[:30000]}

위 데이터로 시스템에 정의된 1-page sheet 형식 그대로 한국어 분석 시트를 작성하세요."""

    messages: list[dict] = []
    if skill_md:
        # SKILL.md를 prompt cache 블록으로
        messages.append({
            'role': 'user',
            'content': [
                {
                    'type': 'text',
                    'text': f'[참고: earnings-analysis skill 프레임]\n\n{skill_md}',
                    'cache_control': {'type': 'ephemeral'},  # 5분 TTL
                },
                {'type': 'text', 'text': user_input},
            ],
        })
    else:
        messages.append({'role': 'user', 'content': user_input})
    return messages


def build_translation_messages(english_text: str) -> list[dict]:
    """Haiku 번역용 — 짧은 헤드라인/요약 입력."""
    return [{
        'role': 'user',
        'content': f"다음 영어 텍스트를 한국어로 자연스럽게 번역하세요. 숫자와 단위는 보존하세요.\n\n{english_text[:8000]}",
    }]


def get_anthropic_client():
    """anthropic SDK 클라이언트 — API 키는 환경변수에서."""
    import anthropic
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY 미설정')
    return anthropic.Anthropic(api_key=api_key)


if __name__ == "__main__":
    print(f'SKILL.md sha256[:16]: {skill_md_sha256()}')
    print(f'prompt_version: {prompt_version()}')
    print()
    print(f'SYSTEM_ANALYSIS chars: {len(SYSTEM_ANALYSIS)}')
    print(f'SYSTEM_TRANSLATION chars: {len(SYSTEM_TRANSLATION)}')
    skill = _read_skill_md()
    print(f'SKILL.md chars: {len(skill)}')
    # 토큰 추정
    try:
        import tiktoken
        enc = tiktoken.get_encoding('cl100k_base')
        print(f'SYSTEM_ANALYSIS tokens: {len(enc.encode(SYSTEM_ANALYSIS))}')
        print(f'SKILL.md tokens: {len(enc.encode(skill))}')
    except ImportError:
        pass
