---
id: "store-taiwan-revenue-csv"
name: "taiwan_revenue.csv (대만 월매출)"
domain: "market-global"
project: "antigravity"
type: "dataset"
runs_on: "github"
schedule_kst: "23:20 갱신"
status: "active"
code: []
reads: []
writes: []
depends_on:
  - "src-taiwan-revenue"
alerts: ""
---

# taiwan_revenue.csv (대만 월매출)

**Domain:** 해외 · 매크로 · **Type:** Dataset · **Runs on:** github · **Schedule (KST):** 23:20 갱신 · **Status:** active · **Project:** antigravity

대만 큐레이션 53종목의 월매출 시계열(FinMind). gha-daily-taiwan-revenue가 생성, create_taiwan_page가 taiwan.html로 렌더.

- 100일 롤링 재조회로 개정 자가치유.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-taiwan-revenue]] — 대만 월매출 (fetch_taiwan_revenue.py)

## Code
- (none)
