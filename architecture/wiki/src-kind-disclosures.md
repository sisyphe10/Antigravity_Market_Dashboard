---
id: "src-kind-disclosures"
name: "KIND 거래소 공시 (fetch_kind_disclosures.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "16:30 (gha-daily-disclosures)"
status: "active"
code:
  - "execution/fetch_kind_disclosures.py"
reads: []
writes:
  - "disclosures.json"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# KIND 거래소 공시 (fetch_kind_disclosures.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 16:30 (gha-daily-disclosures) · **Status:** active · **Project:** antigravity

KIND(한국거래소) 공시를 수집·누적해 `disclosures.json`에 append(DART와 함께). gha-daily-disclosures 내 DART 다음 스텝.

## Reads
- (none)

## Writes
- `disclosures.json`

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_kind_disclosures.py`
