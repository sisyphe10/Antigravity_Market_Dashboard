---
id: "src-dart-disclosures"
name: "DART 공시 (fetch_disclosures.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "16:30 (gha-daily-disclosures)"
status: "active"
code:
  - "execution/fetch_disclosures.py"
reads: []
writes:
  - "disclosures.json"
  - "corp_codes.json"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# DART 공시 (fetch_disclosures.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 16:30 (gha-daily-disclosures) · **Status:** active · **Project:** antigravity

보유종목 DART 전자공시를 수집·누적해 `disclosures.json`+`corp_codes.json` 갱신. RA_Sisyphe_bot 공시 다이제스트가 소비.

- 보유종목 기준 current holdings, accumulate.

## Reads
- (none)

## Writes
- `disclosures.json`
- `corp_codes.json`

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_disclosures.py`
