---
id: "ext-sisyphe"
name: "Sisyphe 가계부/운동 대시보드 + 투자일지 시트"
domain: "personal"
project: "antigravity"
type: "external"
runs_on: "external"
schedule_kst: ""
status: "active"
code:
  - "execution/fetch_journal_data.py"
reads: []
writes: []
depends_on: []
alerts: ""
---

# Sisyphe 가계부/운동 대시보드 + 투자일지 시트

**Domain:** 개인 · 가족 · **Type:** External · **Runs on:** external · **Status:** active · **Project:** antigravity

가계부 + 운동기록 대시보드(Ledger/Fitness/Weight 3탭, Google Sheets + data.json 이중, staticrypt 암호화 배포). 별도 생태계지만 이 repo와 두 접점이 있다.

- **투자일지**: `src-journal-data`(fetch_journal_data.py)가 매일 16:10 KST 시장데이터를 Sisyphe의 Google Sheet Data 탭에 적재.
- **가계부**: 카드 SMS→아이폰 단축어→Apps Script→Sheet 파이프라인. Sisyphe-Bot이 답장으로 분류/수정.
- 상세 카드는 추후 확장 예정.

## Reads
- (none)

## Writes
- (none)

## Depends on
- (none)

## Code
- `execution/fetch_journal_data.py`
