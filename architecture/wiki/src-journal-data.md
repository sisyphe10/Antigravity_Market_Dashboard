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
writes: []
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

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[ext-google-workspace]] — Google Workspace (Sheets · Calendar · Drive)
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_journal_data.py`
