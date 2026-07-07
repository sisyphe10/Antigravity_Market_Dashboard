---
id: "src-nps-fund"
name: "국민연금 적립금 (fetch_nps_fund.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "17:30 평일 (gha-daily-kofia)"
status: "active"
code:
  - "execution/fetch_nps_fund.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# 국민연금 적립금 (fetch_nps_fund.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 17:30 평일 (gha-daily-kofia) · **Status:** active · **Project:** antigravity

국민연금 적립금(data.go.kr odcloud 15106894, kofia와 같은 키)을 수집해 dataset.csv(MACRO KOREA)에 적재. gha-daily-kofia가 kofia 직후 실행.

- 저빈도(연간+최신월 누적). 함정: 피벗+uddi 해석+활용신청. 내부 graceful skip.

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_nps_fund.py`
