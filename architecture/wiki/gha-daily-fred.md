---
id: "gha-daily-fred"
name: "Daily FRED US Macro (07:50 화~토)"
domain: "market-global"
project: "antigravity"
type: "gha_workflow"
runs_on: "gha"
schedule_kst: "07:50 화~토"
status: "active"
code:
  - ".github/workflows/daily_fred.yml"
reads: []
writes:
  - "store-dataset-csv"
  - "page-market"
depends_on:
  - "src-fred"
  - "src-create-dashboard"
alerts: "실패 자체 알림 없음 → gha-daily-health-check"
---

# Daily FRED US Macro (07:50 화~토)

**Domain:** 해외 · 매크로 · **Type:** GHA · **Runs on:** gha · **Schedule (KST):** 07:50 화~토 · **Status:** active · **Project:** antigravity

미국 FRED 시계열 36종(금리/매크로/신용·부동산)을 화~토 07:50 KST(=월~금 22:50 UTC) 수집해 dataset.csv→market.html DATA 재생성.

- 토요일 run이 금요일 밤 미국 고용보고서 등을 다음날 아침 포착. 매 run 전체 재조회.
- `FRED_API_KEY` 미설정 시 graceful skip.
- 함정: 주간 시리즈에 5년창 금지.

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)
- [[page-market]] — market.html (마켓 대시보드)

## Depends on
- [[src-fred]] — FRED 미국 매크로 36종 (fetch_fred_data.py)
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)

## Code
- `.github/workflows/daily_fred.yml`

## Alerts
⚠ 실패 자체 알림 없음 → gha-daily-health-check
