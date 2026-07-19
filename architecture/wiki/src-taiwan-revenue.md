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
  - "execution/taiwan_table.py"
reads: []
writes:
  - "store-taiwan-revenue-csv"
  - "page-market"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# 대만 월매출 (fetch_taiwan_revenue.py)

**Domain:** 해외 · 매크로 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 23:20 (gha-daily-taiwan-revenue) · **Status:** active · **Project:** antigravity

FinMind로 대만 상장 큐레이션 53종목 월매출을 수집해 `taiwan_revenue.csv` 생성. 공유 빌더 `taiwan_table.py`가 이를 `market.html` Data 페이지 'Taiwan' 패널로 렌더(독립 `create_taiwan_page.py`·taiwan.html은 은퇴 — [[page-taiwan]]).

- `--crosscheck`로 공식 TWSE/TPEx 스냅샷 대조(로그만). 100일 롤링 재조회 자가치유.
- 시크릿: FINMIND_TOKEN/USER/PASSWORD.

## Reads
- (none)

## Writes
- [[store-taiwan-revenue-csv]] — taiwan_revenue.csv (대만 월매출)
- [[page-market]] — market.html (마켓 대시보드)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_taiwan_revenue.py`
- `execution/taiwan_table.py`
