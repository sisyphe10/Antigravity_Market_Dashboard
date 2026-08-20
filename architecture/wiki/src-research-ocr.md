---
id: "src-research-ocr"
name: "리서치노트 이미지 OCR (datalake/ocr_worker.py)"
domain: "news-research"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "23:20 step 0 (datalake-research-export)"
status: "active"
code:
  - "datalake/ocr_worker.py"
reads:
  - "store-research-notes-db"
writes:
  - "ocr_state.sqlite"
depends_on:
  - "infra-datalake"
  - "store-research-notes-db"
  - "ext-data-apis"
  - "infra-headless-llm"
alerts: "OCR 실패는 warn (아카이브·태깅은 계속)"
---

# 리서치노트 이미지 OCR (datalake/ocr_worker.py)

**Domain:** 뉴스 · 리서치 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 23:20 step 0 (datalake-research-export) · **Status:** active · **Project:** antigravity

2026-07-31 신설. Research Notes 원문([[store-research-notes-db]])의 **사진·이미지 첨부를 Claude 비전으로 옮겨 적는(OCR, 표 포함)** 캐시-우선 워커. [[src-research-tagging]]의 태깅 파이프라인과 **동일한 설계 원칙** — exporter([[infra-datalake]]의 `export_research_notes.py`)는 매일 어제+오늘을 통째로 재생성하는 멱등 구조라 거기에 LLM을 넣으면 같은 이미지에 매일 재과금된다. 그래서 OCR 정본을 `~/datalake/notes/ocr_state.sqlite`에 두고, md·태깅은 그 캐시를 **투영만** 한다.

- **캐시 정본 = `ocr_state.sqlite`**. 캐시 키(v2, 2026-08-20) = 파일 sha + 프롬프트 버전이라 같은 이미지는 두 번 호출하지 않는다. 인자 없이 부르면 미처리 전량이 대상(전날 실패분 자동 회수). `--date`·`--dry-run`(비용 견적, DB 무부작용)·`--retry-failed` 지원. `fcntl` 파일 락으로 중복 실행 방지.
- **소비처 2곳(둘 다 LLM 미사용)**: ① `export_research_notes.py`가 사진 아이템 아래에 OCR 텍스트를 투영(`load_ocr`, 성공 건만 읽는 read-only 접속 — 캐시 없으면 OCR 블록 없이 md 생성). ② `tag_worker.py`가 OCR 텍스트를 태깅 입력에 덧붙인다 — content_hash가 바뀌므로 이미지가 딸린 노트는 **자동으로 재태깅**돼 "#HBM 이 이미지 표에 있었다"를 잃지 않는다.
- ★**구독 headless 전환(2026-08-20)**: 비전 호출이 종량 Anthropic API에서 **구독 headless**([[infra-headless-llm]])로 넘어갔다 — 어닝봇 어댑터의 `call_multimodal`·`preflight`를 그대로 재사용(base64 이미지 블록을 stream-json으로 싣는 경로가 이미 리서치노트 요약용으로 검증돼 있었다). 엔진 스위치 `OCR_ENGINE`(기본 `headless`, 롤백=`api`), 모델 `OCR_HEADLESS_MODEL`(기본 `claude-sonnet-5`). 실사용 모델은 행 단위 `model`에 `claude-sonnet-5@headless` 형태로 기록돼 사후 백엔드 판별이 된다.
  - **캐시 키에서 모델명을 뺀 것이 전환의 전제**(v1=sha(file_sha, PROMPT_VER, model) → v2=sha(file_sha, PROMPT_VER), `tag_worker` 8/5 정책 승계). 안 그러면 엔진·모델을 바꾸는 순간 캐시가 통째로 무효화돼 전량 재OCR 과금이 난다. 기존 succeeded 행은 **정확한 v1 기대키가 일치할 때만** 제자리 이관(1,280건, 재OCR 0건·멱등)하고, `--dry-run`은 무부작용 계약대로 이관도 하지 않는다. ★대신 **PROMPT 문구를 고치면 `PROMPT_VER`를 반드시 bump** — 키에 모델이 없으니 프롬프트 버전이 유일한 무효화 손잡이다.
  - **실패 위계 = rc**: 인증·쿼터 장애는 항목을 failed로 마킹하지 않고 즉시 중단해 rc **75**(다음 실행에서 자연 회수), 대상 건수가 `OCR_HEADLESS_MAX_ITEMS`(200)를 넘으면 대량 무효화 의심으로 **호출 0회 rc 78**. 이미지 페이로드는 b64 700만자 상한으로 사전 차단. 두 rc 모두 `daily_tag_export.sh`가 **재시도 없이 warn 후 계속**(일반 실패만 `--retry-failed` 재시도).
- **일일 실행 위치**: `daily_tag_export.sh`의 **step 0/5**(태깅·아카이브보다 앞) — OCR을 먼저 채워야 당일 md·태그가 이미지 텍스트를 담는다. 실패해도 아카이브·태깅은 계속(OCR은 파생물).

## Reads
- [[store-research-notes-db]] — research_notes.db + media/ (리서치봇)

## Writes
- `ocr_state.sqlite`

## Depends on
- [[infra-datalake]] — 맥미니 데이터레이크 (~/datalake + 문답 위키)
- [[store-research-notes-db]] — research_notes.db + media/ (리서치봇)
- [[ext-data-apis]] — 외부 데이터 API/소스 집합
- [[infra-headless-llm]] — 구독 LLM 백엔드 (headless claude · codex 폴백)

## Code
- `datalake/ocr_worker.py`

## Alerts
⚠ OCR 실패는 warn (아카이브·태깅은 계속)
