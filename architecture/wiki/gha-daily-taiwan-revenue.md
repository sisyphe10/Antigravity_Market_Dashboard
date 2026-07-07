---
id: "gha-daily-taiwan-revenue"
name: "Daily Taiwan Monthly Revenue (23:20)"
domain: "market-global"
project: "antigravity"
type: "gha_workflow"
runs_on: "gha"
schedule_kst: "23:20 매일"
status: "active"
code:
  - ".github/workflows/daily_taiwan_revenue.yml"
reads: []
writes:
  - "store-taiwan-revenue-csv"
  - "page-taiwan"
depends_on:
  - "src-taiwan-revenue"
  - "page-taiwan"
alerts: "실패 자체 알림 없음 → gha-daily-health-check"
---

# Daily Taiwan Monthly Revenue (23:20)

**Domain:** 해외 · 매크로 · **Type:** GHA · **Runs on:** gha · **Schedule (KST):** 23:20 매일 · **Status:** active · **Project:** antigravity

대만 상장·상궤 큐레이션 53종목의 월매출(FinMind)을 23:20 KST(14:20 UTC) 수집해 `taiwan_revenue.csv`→`taiwan.html` 생성. daily_crawl 23:00과 +20분 시차로 동시각 기동 회피.

- 순서: `fetch_taiwan_revenue.py` → `--crosscheck`(공식 TWSE/TPEx 대조, 로그만) → `create_taiwan_page.py` → safe_push.
- GHA cron 지연(3~5h) 감안해도 다음 실행 전 자가치유(100일 롤링 재조회).
- 시크릿: FINMIND_TOKEN/USER/PASSWORD.

## Reads
- (none)

## Writes
- [[store-taiwan-revenue-csv]] — taiwan_revenue.csv (대만 월매출)
- [[page-taiwan]] — taiwan.html (대만 월매출)

## Depends on
- [[src-taiwan-revenue]] — 대만 월매출 (fetch_taiwan_revenue.py)
- [[page-taiwan]] — taiwan.html (대만 월매출)

## Code
- `.github/workflows/daily_taiwan_revenue.yml`

## Alerts
⚠ 실패 자체 알림 없음 → gha-daily-health-check
