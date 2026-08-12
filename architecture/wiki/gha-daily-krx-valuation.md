---
id: "gha-daily-krx-valuation"
name: "Daily KRX Index Valuation (18:30 + 08:20 평일)"
domain: "market-kr"
project: "antigravity"
type: "gha_workflow"
runs_on: "gha"
schedule_kst: "18:30 평일 + 08:20 평일(D-1 ETF AUM 확정 백필)"
status: "active"
code:
  - ".github/workflows/daily_krx_valuation.yml"
  - "launchd/gha/com.antigravity.gha-krx-valuation.plist"
reads: []
writes:
  - "store-dataset-csv"
  - "page-market"
depends_on:
  - "src-krx-valuation"
  - "src-kosdaq-lev-etf-aum"
  - "src-create-dashboard"
alerts: "실패 자체 알림 없음 → gha-daily-health-check"
---

# Daily KRX Index Valuation (18:30 + 08:20 평일)

**Domain:** 국내 시장 · **Type:** GHA · **Runs on:** gha · **Schedule (KST):** 18:30 평일 + 08:20 평일(D-1 ETF AUM 확정 백필) · **Status:** active · **Project:** antigravity

코스피/코스닥 지수 후행 PER/PBR/배당수익률(pykrx data.krx 로그인)을 평일 18:30 KST(09:30 UTC) 수집해 dataset.csv→market.html DATA(INDEX_KOREA) 재생성.

- 장 마감 후 KRX 저녁 발표 반영. `KRX_ID`/`KRX_PW` 미설정 시 graceful skip.
- 클라우드 IP에서도 로그인 됨(외국인 보유는 daily_crawl에서 같은 자격 사용). forward PER은 미제공(Quantiwise 영역).
- **코스닥 레버리지 ETF AUM 합승(2026-08-10)**: 같은 KRX 자격을 쓰는 [[src-kosdaq-lev-etf-aum]]을 밸류에이션 수집과 create_dashboard 사이에 한 스텝 끼워 넣었다. 이 스텝만 **비치명(`|| 계속 진행`)** — 실패해도 밸류에이션 갱신·대시보드 재생성은 그대로 간다. 워크플로(`daily_krx_valuation.yml`)와 맥미니 트리거(`launchd/gha/run_gha_job.sh` `gha-krx-valuation` 케이스) 양쪽에 같은 순서로 넣어 패리티를 맞췄다.
- ★**아침 08:20 평일 2회차(2026-08-12 추가, `067084a7`)**: 합승한 ETF AUM 때문에 생긴 실행이다 — KRX ETF 순자산총액은 **당일 18:30엔 미확정**이라 그 실행이 AUM을 못 넣고(0/`-` → 결측 처리, [[src-kosdaq-lev-etf-aum]]), 전일 확정치가 밤사이 공표되므로 아침 실행이 D-1을 채운다. 밸류에이션 쪽은 이미 채워져 있어 lookback 재조회의 멱등 upsert로 무해.
  - 스케줄은 **`launchd/gha/com.antigravity.gha-krx-valuation.plist`에만** 추가했다(`StartCalendarInterval` 배열에 월~금 08:20 5개 dict 추가). `daily_krx_valuation.yml`의 트리거는 `workflow_dispatch` 뿐이라 GitHub 쪽 cron은 존재하지 않는다 — **발화 시각의 정본은 언제나 맥미니 plist**([[launchd-gha-phase2]]).
  - 08:10 [[timer-kodex-sectors]]과 **10분 간격으로 KRX 로그인을 직렬화**한다(동시 로그인 회피 — KRX는 로그인 5회 실패 시 계정 잠금).

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)
- [[page-market]] — market.html (마켓 대시보드)

## Depends on
- [[src-krx-valuation]] — KRX 지수 밸류에이션 (fetch_krx_valuation.py)
- [[src-kosdaq-lev-etf-aum]] — 코스닥 레버리지 ETF AUM (fetch_kosdaq_lev_etf_aum.py)
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)

## Code
- `.github/workflows/daily_krx_valuation.yml`
- `launchd/gha/com.antigravity.gha-krx-valuation.plist`

## Alerts
⚠ 실패 자체 알림 없음 → gha-daily-health-check
