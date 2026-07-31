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
alerts: "OCR 실패는 warn (아카이브·태깅은 계속)"
---

# 리서치노트 이미지 OCR (datalake/ocr_worker.py)

**Domain:** 뉴스 · 리서치 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 23:20 step 0 (datalake-research-export) · **Status:** active · **Project:** antigravity

2026-07-31 신설. Research Notes 원문([[store-research-notes-db]])의 **사진·이미지 첨부를 Haiku 비전으로 옮겨 적는(OCR, 표 포함)** 캐시-우선 워커. [[src-research-tagging]]의 태깅 파이프라인과 **동일한 설계 원칙** — exporter([[infra-datalake]]의 `export_research_notes.py`)는 매일 어제+오늘을 통째로 재생성하는 멱등 구조라 거기에 LLM을 넣으면 같은 이미지에 매일 재과금된다. 그래서 OCR 정본을 `~/datalake/notes/ocr_state.sqlite`에 두고, md·태깅은 그 캐시를 **투영만** 한다.

- **캐시 정본 = `ocr_state.sqlite`**. 캐시 키 = 파일 sha + 프롬프트 버전 + 모델이라 같은 이미지는 두 번 호출하지 않는다. 인자 없이 부르면 미처리 전량이 대상(전날 실패분 자동 회수). `--date`·`--dry-run`(비용 견적, DB 무부작용)·`--retry-failed` 지원. `fcntl` 파일 락으로 중복 실행 방지.
- **소비처 2곳(둘 다 LLM 미사용)**: ① `export_research_notes.py`가 사진 아이템 아래에 OCR 텍스트를 투영(`load_ocr`, 성공 건만 읽는 read-only 접속 — 캐시 없으면 OCR 블록 없이 md 생성). ② `tag_worker.py`가 OCR 텍스트를 태깅 입력에 덧붙인다 — content_hash가 바뀌므로 이미지가 딸린 노트는 **자동으로 재태깅**돼 "#HBM 이 이미지 표에 있었다"를 잃지 않는다.
- **일일 실행 위치**: `daily_tag_export.sh`의 **step 0/5**(태깅·아카이브보다 앞) — OCR을 먼저 채워야 당일 md·태그가 이미지 텍스트를 담는다. 실패해도 아카이브·태깅은 계속(OCR은 파생물).

## Reads
- [[store-research-notes-db]] — research_notes.db + media/ (리서치봇)

## Writes
- `ocr_state.sqlite`

## Depends on
- [[infra-datalake]] — 맥미니 데이터레이크 (~/datalake + 문답 위키)
- [[store-research-notes-db]] — research_notes.db + media/ (리서치봇)
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `datalake/ocr_worker.py`

## Alerts
⚠ OCR 실패는 warn (아카이브·태깅은 계속)
