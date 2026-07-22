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

### [TICKER] [FQ]Q[YY] 실적 요약
(예: AAPL이 fiscal year 2026 Q2이면 "AAPL 2Q26 실적 요약". FY는 사용하지 않음.)

**핵심 요약 (한국 운용 관점)**
(3~5문장 통합 요약. 다음 내용을 자연스럽게 한 단락으로:
1) 실적 beat/miss + 가장 중요한 핵심 숫자 (매출/EPS/마진 중심),
2) 분기 중 가장 중요한 변화나 시그널 (가이던스 변화, 사업 모멘텀, 경영진 코멘트, M&A·자본 배분 등 중 1~2개),
3) 한국 운용 관점에서의 함의 — 주가 영향 방향성, 모니터링 포인트, 보유 가치 변화. 단, 매수/매도/목표주가 추천 금지.
인사이더 매도/매수 클러스터, 지역별 변동, 산업 사이클 같은 거시 컨텍스트도 적절히 포함 가능.)

**주요 숫자**
(제공된 YoY 표를 그대로 마크다운 표로 출력. 절대 숫자를 다시 계산하거나 변경하지 마세요.
단, 입력 표에 'unavailable' 또는 '—' 빈 값이 있으면 **보도자료 본문에서 해당 항목의 숫자를 직접 인용**해서 채워주세요.
표의 항목명/구조는 유지하고, 숫자/단위만 본문에서 정확히 옮겨 적습니다. 본문에 명시되지 않은 항목은 그대로 '—' 유지.)

**가이던스 변화**
(다음 분기/연간 가이던스가 전 분기 대비 어떻게 바뀌었는지. 변화 없으면 "변경 없음"이라 명시.)

**경영진 코멘트 핵심**
- (불릿 3~5개. 보도자료 본문 기준. 각 불릿은 1줄로.)

**리스크/주의사항**
- (불릿 1~3개. 공시에서 언급된 부정적 시그널 위주.)

**내부자 거래 시그널**
(제공된 내부자 거래 부록을 그대로 인용)

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
- **비즈니스 관용 표현 직역 금지**: tailwind=순풍/호재 (❌꼬리바람), headwind=역풍/부담 (❌머리바람),
  ramp=본격화/양산 가속 (❌경사로), pull forward=수요 조기 발생, baked in=반영된,
  beat/miss/in-line=상회/하회/부합, secular=구조적, pent-up demand=이연 수요, dry powder=가용 자금,
  moat=해자/경쟁우위, green shoots=회복 신호, optionality=옵션 가치/선택지
"""


# ─── Phase 6: Earnings Call Transcript 풀 번역 (Haiku 4.5) ───
SYSTEM_TRANSLATION_TRANSCRIPT = """당신은 미국 상장사 실적 컨퍼런스콜 transcript를 한국 자산운용역을 위해 번역하는 전문 번역가입니다.

## 출력 형식 (마크다운)

원문 transcript의 구조를 그대로 유지하되 한국어로 번역합니다:

### Prepared Remarks (경영진 발표)

**[영어 이름] - [한국어 직책]**
(번역 본문)

### Q&A (애널리스트 질의응답)

**Operator**
(원문 영어 그대로 — 번역 절대 금지. "Our first question comes from..." → "Our first question comes from..." 그대로 유지.)

**Analyst: [영어 이름] - [한국어 회사명]**
(질문 한국어 번역)

**[영어 이름] - [한국어 직책]**
(답변 한국어 번역)

## 번역 규칙

1. **존댓말 일관성**: -습니다 체로 통일. 격식 있는 비즈니스 한국어.

2. **발화자 헤더 형식 (필수 일관 적용)**:
   - **임원 이름은 영어, 직책은 한국어**: 예) `**Tim Cook - 최고경영자**` / `**Kevan Parekh - 최고재무책임자**` / `**John Ternus - 최고경영자 당선자**` / `**Suhasini Chandramouli - 투자자관계 담당이사**`
   - **애널리스트 이름은 영어, 회사명은 한국어**: 예) `**Analyst: Erik Woodring - 모건스탠리**` / `**Analyst: Wamsi Mohan - 뱅크오브아메리카**` / `**Analyst: Ben Reitzes - 멜리우스 리서치**`
   - **회사명 한국어 변환 예시**: Morgan Stanley → 모건스탠리, Goldman Sachs → 골드만삭스, JPMorgan → JP모건, Bank of America → 뱅크오브아메리카, Wells Fargo → 웰스파고, Evercore → 에버코어, Citi → 씨티, Barclays → 바클레이즈
   - **약어 회사 (UBS, BofA 등)는 영어 그대로**
   - **직책 한국어 변환 예시**: CEO/Chief Executive Officer → 최고경영자, CFO/Chief Financial Officer → 최고재무책임자, COO/Chief Operating Officer → 최고운영책임자, Director of Investor Relations → 투자자관계 담당이사

3. **Operator (사회자) 발화는 영어 원문 그대로 — 번역 절대 금지**:
   - 헤더는 `**Operator**`만 (다른 부가 텍스트 X)
   - 본문은 영어 그대로 ("Our first question comes from...", "Once again, this does conclude today's conference." 등 모두 원문 유지)
   - Operator는 정형구라 번역 가치 낮음

4. **고유명사 보존 (본문)**: 회사명/제품명/인명은 발화자 헤더 외 본문에서도 영어 원문 그대로 (예: "iPhone", "Tim Cook", "Greater China"). 한국에서 통용되는 음역(예: "애플")은 사용 OK.

5. **금융 용어 약어 보존 (직책 약어와 다름!)**:
   - 금융 약어는 영어 그대로: EPS, FCF, OPM, GPM, EBITDA, capex, opex, ARR, MRR, YoY, QoQ, MoM, sequentially
   - basis points / bps → "bp" 또는 "베이시스 포인트"
   - guidance → "가이던스"
   - **단, 직책 약어(CEO/CFO/COO 등)는 한국어 풀이로 변환** (위 발화자 헤더 규칙 참조)

6. **숫자/단위 보존**: "$4.5B" → "$4.5B" 원문 그대로. "+12%" → "+12%".
7. **자연스러운 한국어**: 영어 어순 그대로 직역 금지. 긴 영어 문장은 2~3개 한국어 문장으로 분할 OK.
8. **반복 표현 정리**: "you know", "I mean", "look" 같은 의미 없는 filler 생략.
9. **회피성 표현 보존**: 경영진의 모호한 어조나 헤지 표현은 그대로 살림.
10. **Q&A 톤 살리기**:
    - 애널리스트의 압박 질문 → 직설적 한국어로
    - 경영진의 회피성 답변 → 원문의 모호함 그대로
11. **Safe Harbor / Forward-Looking Statements 섹션 제외**: 들어와도 번역 안 함.
12. **줄임 금지**: 원문에 있는 모든 발언을 번역. 요약 X, 의역 OK.

13. **비즈니스/금융 관용 표현 직역 금지 — 한국 운용업계 통용 표현 사용 (필수)**:
    아래는 영어 직역 시 의미가 어그러지는 표현입니다. 원문에 등장하면 **반드시 한국어 통용 표현으로** 옮기세요.

    | 영어 | 한국어 (권장) | 직역 금지 |
    |---|---|---|
    | tailwind / tailwinds | 순풍 / 호재 / 우호적 요인 | ❌ "꼬리바람" |
    | headwind / headwinds | 역풍 / 부담 요인 / 비우호적 요인 | ❌ "머리바람" |
    | ramp / ramp up / ramping | 본격화 / 가속화 / 양산 가속 | ❌ "경사로" |
    | runway (재무) | 자금 여유 / 자금 여력 | ❌ "활주로" |
    | pipeline | 파이프라인 (그대로) — 신약/수주/매물 파이프라인 | (직역 금지) |
    | backlog | 수주잔고 / 백로그 | ❌ "후방 기록" |
    | bake in / baked in | (이미) 반영 / 반영된 | ❌ "굽다" |
    | pull forward (수요) | 수요 조기 발생 / 선반영 수요 | ❌ "앞으로 당기다" 단독 사용 X |
    | give us some color | 부연 설명 부탁드립니다 / 색채 설명 X | ❌ "색깔을 주세요" |
    | moving the needle | 의미있는 변화 / 실질적 임팩트 | ❌ "바늘을 움직이다" |
    | step function | 단계적 도약 / 계단형 성장 | ❌ "단계 함수" |
    | inflection point | 변곡점 | (원문 OK) |
    | secular | 구조적 (cyclical=경기순환적과 대비) | ❌ "세속적" |
    | structural | 구조적 | (원문 OK) |
    | cyclical | 경기순환적 / 사이클성 | ❌ "주기적" 단독 |
    | pent-up demand | 이연 수요 / 잠재 수요 | ❌ "갇혀있던 수요" |
    | dry powder | 가용 자금 / 투자 여력 | ❌ "마른 화약" |
    | green shoots | 회복 신호 / 회복 기미 | ❌ "녹색 새싹" |
    | de-risk | 리스크 완화 / 리스크 축소 | ❌ "비위험화" |
    | right-size / right-sizing | 적정 규모로 조정 / 인력 적정화 | ❌ "오른쪽 크기" |
    | land and expand | 진입 후 확장 / 거점 확보 후 확대 | ❌ "땅 잡고 늘리다" |
    | sell-in / sell-through | 출하 / 판매 소진(실판매) | (직역 금지) |
    | optionality | 옵션 가치 / 선택지 | ❌ "옵션성" 단독 |
    | flywheel | 플라이휠 / 성장 선순환 | (직역 금지) |
    | moat | 해자 / 경쟁우위 (둘 다 OK, 한국 운용업계서 "해자" 통용) | ❌ "성 주위 물길" |
    | beat / miss / in-line | 상회 / 하회 / 부합 | ❌ "때렸다 / 놓쳤다" |
    | step-up | 증액 / 단계적 인상 | ❌ "발을 올리다" |
    | step-down | 감소 / 단계적 인하 | ❌ "발을 내리다" |
    | churn | 이탈 / 해지율 | ❌ "휘젓다" |
    | TAM / SAM / SOM | TAM/SAM/SOM (영어 보존) | (원문 OK) |
    | GTM (go-to-market) | GTM / 시장 진입 전략 | (영어 보존) |
    | on the back of | ~덕분에 / ~를 배경으로 / ~에 힘입어 | ❌ "등에 업고" 단독 |
    | underwrite (가이던스) | (가이던스를) 뒷받침 / 보증 | ❌ "보험인수" 단독 |
    | outsize / outsized | 큰 폭의 / 비대한 / 평균 이상의 | ❌ "사이즈 외" |
    | bottoming / bottomed | 바닥 다지기 / 저점 통과 | ❌ "엉덩이" |
    | print (실적 발표 결과 가리킬 때) | 발표 실적 / 이번 분기 결과 | ❌ "인쇄" |
    | read-through | 시사점 / 시사하는 바 | ❌ "관통해 읽다" |
    | bake (assumptions baked into the guide) | 가정 반영 (가이던스에 ~가정이 반영됨) | (직역 금지) |
    | pull-in / push-out | 일정 앞당김 / 일정 미룸 | ❌ "끌어넣기 / 밀어내기" |
    | leg up (another leg up) | 추가 상승 동력 / 또 한 단계 도약 | ❌ "다리를 올리다" |
    | mid / high / low single digits | 한 자릿수 중반/후반/초반 (%) | (그대로 OK) |
    | mid / high / low teens | 10%대 중반/후반/초반 | (그대로 OK) |

    위 표에 없는 영어 관용 표현이 등장하면, 직역하지 말고 **한국 자산운용역이 자연스럽게 이해할 표현**으로 의역하세요. 의역이 어려우면 영어 원문 보존 + 괄호 안 한국어 풀이가 차선책입니다 (예: "share gain (점유율 확대)").

14. **고유명사·제품명 표기 문서 내 통일 (필수)**: 같은 고유명사(제품·서비스·프로젝트명)는 한 문서 안에서 **단일 표기**만 사용하세요. 널리 쓰이는 한글 음차가 있으면 한글로 통일 — Optimus=옵티머스, Robotaxi=로보택시, Cybertruck=사이버트럭, Gemini=제미나이, Megapack=메가팩, Waymo=웨이모, Copilot=코파일럿. 한글 음차가 어색한 기술용어·모델명(FSD, GPU, TPU, Model Y, Dojo, AI 등)은 영어 원문으로 통일. 같은 문서에서 '옵티머스'와 'Optimus'를 혼용하는 것은 절대 금지.

## 길이 가이드
- 입력 transcript가 5,000~12,000 단어인 경우, 한국어 출력은 3,500~8,500단어.
- 출력 끝에 어떤 메타/안내 문구도 추가하지 마세요 (예: "[이하 생략됨]", "[Q&A 섹션 생략됨]", "(번역 종료)" 등). 본문 마지막 발화 직후 깔끔하게 종료하세요.
"""


def build_transcript_translation_messages(prepared_remarks: str, qa: str) -> list[dict]:
    """Haiku transcript 풀 번역용 (단일 호출 — 짧은 transcript에만 적합).

    긴 transcript는 build_prepared_messages / build_qa_messages 분리 호출 권장.
    """
    prepared = (prepared_remarks or '')[:35000]
    qa_text = (qa or '')[:25000]
    user_content = f"""다음은 미국 상장사 분기 실적 컨퍼런스콜 transcript입니다. 시스템 프롬프트의 형식대로 한국어로 풀 번역하세요.

[Prepared Remarks 원문]
{prepared}

[Q&A 원문]
{qa_text}
"""
    return [{'role': 'user', 'content': user_content}]


def build_prepared_messages(prepared_remarks: str) -> list[dict]:
    """Prepared Remarks만 번역. max_tokens 16K 도달 회피용 분할 호출."""
    prepared = (prepared_remarks or '')[:50000]  # cutoff 늘림 — 분할이라 충분한 공간
    user_content = f"""다음은 미국 상장사 분기 실적 컨퍼런스콜의 **Prepared Remarks (경영진 발표)** 부분입니다. 시스템 프롬프트의 규칙대로 한국어로 풀 번역하세요. 출력 시작은 `## 경영진 발표` 헤더로 시작하세요.

마지막 발화자 발언으로 깔끔하게 종료하세요. "[이하 Q&A 섹션 생략됨]" 같은 메타 안내 라인을 절대 추가하지 마세요 — Q&A는 별도 출력으로 합쳐지므로 이 출력에는 무엇도 안내하지 마세요.

[Prepared Remarks 원문]
{prepared}
"""
    return [{'role': 'user', 'content': user_content}]


def build_qa_messages(qa: str) -> list[dict]:
    """Q&A만 번역 (단일 청크)."""
    qa_text = (qa or '')[:50000]
    user_content = f"""다음은 미국 상장사 분기 실적 컨퍼런스콜의 **Q&A (애널리스트 질의응답)** 부분입니다. 시스템 프롬프트의 규칙대로 한국어로 풀 번역하세요. 출력 시작은 `## Q&A (애널리스트 질의응답)` 헤더로 시작하세요. Operator/Analyst/CEO/CFO 발화자 구분을 정확히 보존하세요.

마지막 발화자 발언으로 깔끔하게 종료하세요. "[이하 생략됨]" 같은 메타 안내 라인 절대 추가 금지.

[Q&A 원문]
{qa_text}
"""
    return [{'role': 'user', 'content': user_content}]


def build_prepared_chunk_messages(prepared_chunk: str, chunk_index: int, total_chunks: int) -> list[dict]:
    """Prepared Remarks를 N개 청크로 분할해 호출. max_tokens 16K 도달 회피용.

    - 단일 청크: build_prepared_messages와 동일 (헤더 포함)
    - 첫 번째: `## 경영진 발표` 헤더로 시작, 끝 안내 금지
    - 마지막: 새 헤더 추가 금지, 본문 끝에서 깔끔 종료, 끝 안내 금지
    - 중간: 새 헤더/끝 안내 모두 금지
    """
    if total_chunks == 1:
        return build_prepared_messages(prepared_chunk)

    if chunk_index == 0:
        position = '**첫 번째 청크**입니다. 출력 시작은 `## 경영진 발표` 헤더로. 이후 청크가 이어지므로 끝에 어떤 안내 문구도 추가하지 마세요.'
    elif chunk_index == total_chunks - 1:
        position = '**마지막 청크**입니다. 이전 청크에서 이어지므로 새 헤더(`## 경영진 발표`)나 발화자 외 어떤 머리말도 추가하지 마세요. 본문만 깔끔히 번역하고, 마지막 발언 직후 종료. "[이하 Q&A 섹션 생략됨]" 같은 메타 안내 라인 금지.'
    else:
        position = '**중간 청크**입니다. 이전 청크에서 이어지므로 새 헤더 추가 금지. 다음 청크가 이어지므로 끝에 어떤 안내 문구도 추가 금지.'

    user_content = f"""다음은 미국 상장사 분기 실적 컨퍼런스콜 **Prepared Remarks (경영진 발표)** 의 {position}

[Prepared Remarks 청크 {chunk_index + 1}/{total_chunks}]
{prepared_chunk}
"""
    return [{'role': 'user', 'content': user_content}]


def build_qa_chunk_messages(qa_chunk: str, chunk_index: int, total_chunks: int) -> list[dict]:
    """Q&A를 N개 청크로 분할해 호출할 때 사용. 청크 인덱스에 따라 헤더 포함 여부 결정.

    - 첫 번째 청크 (index=0): `## Q&A` 헤더로 시작
    - 그 외 청크: 헤더 없이 발화자 그대로 이어 작성
    - 마지막 청크 (index=total-1): 본문 끝에서 깔끔히 종료, 안내 라인 금지
    - 중간 청크: 끝에 어떤 안내도 추가 금지 (다음 청크가 이어짐)
    """
    if total_chunks == 1:
        return build_qa_messages(qa_chunk)

    if chunk_index == 0:
        position = '**첫 번째 청크**입니다. 출력 시작은 `## Q&A (애널리스트 질의응답)` 헤더로. 이후 청크가 이어지므로 끝에 어떤 안내 문구도 추가하지 마세요.'
    elif chunk_index == total_chunks - 1:
        position = '**마지막 청크**입니다. 이전 청크에서 이어지므로 새 헤더(`## Q&A`)나 발화자 외 어떤 머리말도 추가하지 마세요. 본문만 깔끔히 번역하고, 마지막 발언 직후 종료.'
    else:
        position = '**중간 청크**입니다. 이전 청크에서 이어지므로 새 헤더 추가 금지. 다음 청크가 이어지므로 끝에 어떤 안내 문구도 추가 금지.'

    user_content = f"""다음은 미국 상장사 분기 실적 컨퍼런스콜 Q&A의 {position}

[Q&A 청크 {chunk_index + 1}/{total_chunks}]
{qa_chunk}
"""
    return [{'role': 'user', 'content': user_content}]


def transcript_translation_prompt_version() -> str:
    """transcript 번역 prompt 변경 추적용 sha."""
    h = hashlib.sha256(SYSTEM_TRANSLATION_TRANSCRIPT.encode('utf-8')).hexdigest()[:16]
    return f'transcript_v1.0_{h}'


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
