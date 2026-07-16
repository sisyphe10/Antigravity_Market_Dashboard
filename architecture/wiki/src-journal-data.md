---
id: "src-journal-data"
name: "투자일지 시장데이터 (fetch_journal_data.py)"
domain: "personal"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "16:10 (sisyphe-bot)"
status: "active"
code:
  - "execution/fetch_journal_data.py"
reads: []
writes:
  - "~/Journal/journal_market.json"
depends_on:
  - "ext-google-workspace"
  - "ext-data-apis"
alerts: ""
---

# 투자일지 시장데이터 (fetch_journal_data.py)

**Domain:** 개인 · 가족 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 16:10 (sisyphe-bot) · **Status:** active · **Project:** antigravity

투자일지용 시장데이터(상승/하락 종목수 등)를 수집해 Sisyphe의 Google Sheet Data 탭에 적재. Sisyphe-Bot 16:10 잡이 subprocess로 호출.

- 백필 `--date=YYYYMMDD`(상승하락 종목수는 과거 공란). apscheduler misfire로 행 누락되던 것을 grace+coalesce로 수정.
- 로컬 HTML 페이지 아님 — 산출처는 외부 Google Sheet.
- 2026-07-16 **이중기록**: 같은 데이터를 `~/Journal/journal_market.json`에도 upsert(패치 경로 포함). 시트 왕복 없이 로컬에서 읽으려는 것으로, **로컬 쓰기가 실패해도 시트 파이프라인은 경고만 남기고 계속**한다(부수 효과 취급). Journal 자산은 맥미니 로컬 전용이라 git·게시 파이프라인과 격리(전역 규칙 Journal 섹션).

## Reads
- (none)

## Writes
- `~/Journal/journal_market.json`

## Depends on
- [[ext-google-workspace]] — Google Workspace (Sheets · Calendar · Drive)
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_journal_data.py`
