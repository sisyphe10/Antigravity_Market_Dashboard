---
id: "gha-daily-ecos"
name: "Daily ECOS BOK (17:40 평일)"
domain: "market-global"
project: "antigravity"
type: "gha_workflow"
runs_on: "gha"
schedule_kst: "17:40 평일"
status: "active"
code:
  - ".github/workflows/daily_ecos.yml"
reads: []
writes:
  - "store-dataset-csv"
  - "page-market"
depends_on:
  - "src-ecos"
  - "src-create-dashboard"
alerts: "실패 자체 알림 없음 → gha-daily-health-check"
---

# Daily ECOS BOK (17:40 평일)

**Domain:** 해외 · 매크로 · **Type:** GHA · **Runs on:** gha · **Schedule (KST):** 17:40 평일 · **Status:** active · **Project:** antigravity

한국은행 ECOS 시계열 33종(금리/매크로/신용·부동산)을 평일 17:40 KST(08:40 UTC) 수집해 dataset.csv→market.html DATA 섹션 재생성.

- 시장금리 T+1 + 당일 오전 발표 월간지표를 하루 1회로 완결 수집. kofia(2026-07-23 21:30으로 이동)와 `wrap-nav-pipeline` 그룹으로 직렬화.
- `ECOS_API_KEY` 미설정 시 graceful skip(실패 알림 없음).
- 함정: M2=161Y006, 분기전망=첫달 말일.

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)
- [[page-market]] — market.html (마켓 대시보드)

## Depends on
- [[src-ecos]] — ECOS 한국 매크로 33종 (fetch_ecos_data.py)
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)

## Code
- `.github/workflows/daily_ecos.yml`

## Alerts
⚠ 실패 자체 알림 없음 → gha-daily-health-check
