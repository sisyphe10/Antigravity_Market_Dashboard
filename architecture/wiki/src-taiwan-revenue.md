---
id: "src-taiwan-revenue"
name: "대만 월매출 (fetch_taiwan_revenue.py)"
domain: "market-global"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "23:20 (gha-daily-taiwan-revenue)"
status: "active"
code:
  - "execution/fetch_taiwan_revenue.py"
  - "execution/create_taiwan_page.py"
reads: []
writes:
  - "store-taiwan-revenue-csv"
  - "page-taiwan"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# 대만 월매출 (fetch_taiwan_revenue.py)

**Domain:** 해외 · 매크로 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 23:20 (gha-daily-taiwan-revenue) · **Status:** active · **Project:** antigravity

FinMind로 대만 상장 큐레이션 53종목 월매출을 수집해 `taiwan_revenue.csv` 생성. `create_taiwan_page.py`가 이를 taiwan.html로 렌더.

- `--crosscheck`로 공식 TWSE/TPEx 스냅샷 대조(로그만). 100일 롤링 재조회 자가치유.
- 시크릿: FINMIND_TOKEN/USER/PASSWORD.

## Reads
- (none)

## Writes
- [[store-taiwan-revenue-csv]] — taiwan_revenue.csv (대만 월매출)
- [[page-taiwan]] — taiwan.html (대만 월매출)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_taiwan_revenue.py`
- `execution/create_taiwan_page.py`
