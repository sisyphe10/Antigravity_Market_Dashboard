---
id: "gha-daily-kofia"
name: "Daily KOFIA Stats + NPS (17:30 평일)"
domain: "market-kr"
project: "antigravity"
type: "gha_workflow"
runs_on: "gha"
schedule_kst: "17:30 평일"
status: "active"
code:
  - ".github/workflows/daily_kofia.yml"
reads: []
writes:
  - "kofia_stats.json"
  - "page-index"
  - "store-dataset-csv"
  - "page-market"
depends_on:
  - "src-kofia"
  - "src-nps-fund"
  - "src-create-dashboard"
alerts: "실패 자체 알림 없음 → gha-daily-health-check"
---

# Daily KOFIA Stats + NPS (17:30 평일)

**Domain:** 국내 시장 · **Type:** GHA · **Runs on:** gha · **Schedule (KST):** 17:30 평일 · **Status:** active · **Project:** antigravity

고객예탁금/신용잔고(data.go.kr 금투협 종합통계)를 평일 17:30 KST(08:30 UTC) 수집해 `kofia_stats.json`→index.html 랜딩 차트 재생성. 같은 키로 국민연금 적립금(`fetch_nps_fund.py`)도 이어 수집.

- `DATA_GO_KR_API_KEY` 미설정 시 graceful skip. `wrap-nav-pipeline` 그룹.
- 예탁금=invrDpsgAmt·신용잔고=crdTrFingWhl.
- 국민연금 적립금은 odcloud 15106894(피벗+uddi 해석 함정).

## Reads
- (none)

## Writes
- `kofia_stats.json`
- [[page-index]] — index.html (랜딩)
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)
- [[page-market]] — market.html (마켓 대시보드)

## Depends on
- [[src-kofia]] — 금투협 예탁금/신용잔고 (fetch_kofia_stats.py)
- [[src-nps-fund]] — 국민연금 적립금 (fetch_nps_fund.py)
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)

## Code
- `.github/workflows/daily_kofia.yml`

## Alerts
⚠ 실패 자체 알림 없음 → gha-daily-health-check
