---
id: "gha-daily-crawl"
name: "Daily Market Crawl (23:00)"
domain: "market-global"
project: "antigravity"
type: "gha_workflow"
runs_on: "gha"
schedule_kst: "23:00 매일 (+ execution/** push 트리거)"
status: "active"
code:
  - ".github/workflows/daily_crawl.yml"
reads:
  - "store-wrap-nav-xlsx"
writes:
  - "store-dataset-csv"
  - "store-portfolio-data"
  - "store-contribution-data"
  - "page-featured"
  - "page-market"
  - "page-wrap"
  - "page-universe"
  - "page-seibro"
  - "page-index"
depends_on:
  - "src-market-crawler"
  - "src-monthly-returns"
  - "src-danawa"
  - "src-krx-foreign"
  - "src-seibro"
  - "src-calculate-wrap-nav"
  - "src-calculate-returns"
  - "src-create-portfolio-tables"
  - "src-create-contribution-data"
  - "src-draw-charts"
  - "src-create-dashboard"
alerts: "실패 자체 알림 없음 → gha-daily-health-check가 산출물 신선도로 포착"
---

# Daily Market Crawl (23:00)

**Domain:** 해외 · 매크로 · **Type:** GHA · **Runs on:** gha · **Schedule (KST):** 23:00 매일 (+ execution/** push 트리거) · **Status:** active · **Project:** antigravity

생태계 최대 야간 파이프라인. 23:00 KST(14:00 UTC) 또는 `execution/**`·dataset.csv push 시 기동.

- 순서: yfinance 백필 → 월별수익률 → 지수1M → 메모리엑셀 → **market_crawler**(DRAM/NAND/원자재/크립토/FX/지수/리튬/폴리실리콘/해상운임/SMP/SiliconData) → NAV·수익률 계산 → 다나와 → 차트 → KRX 금/ETS → 외국인 보유 → 예탁금 → wrap차트 → 포트폴리오표 → 기여도 → SEIBro TOP50 → create_dashboard → safe_push.
- `concurrency: wrap-nav-pipeline`으로 xlsx 쓰기 직렬화. push는 `--xlsx-conflict bail`.
- 장중 오작동 방지: push-트리거 run은 KRX 장시간 밖으로 게이트(2026-07 추가).
- Featured/stock_price_history는 GHA IP 차단으로 VM 잡이 담당.

## Reads
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)
- [[store-portfolio-data]] — portfolio_data.json
- [[store-contribution-data]] — contribution_data.json
- [[page-featured]] — featured.html (Featured TOP)
- [[page-market]] — market.html (마켓 대시보드)
- [[page-wrap]] — wrap.html (WRAP 대시보드)
- [[page-universe]] — universe.html (Universe)
- [[page-seibro]] — seibro.html (SEIBro)
- [[page-index]] — index.html (랜딩)

## Depends on
- [[src-market-crawler]] — 마스터 시장 크롤러 (market_crawler.py)
- [[src-monthly-returns]] — 월별 수익률 11지수 (fetch_monthly_returns.py)
- [[src-danawa]] — 다나와 DRAM 최저가 (fetch_danawa_price.py)
- [[src-krx-foreign]] — 외국인 보유비중 (fetch_krx_foreign.py)
- [[src-seibro]] — SEIBro TOP50 (fetch_seibro_data.py)
- [[src-calculate-wrap-nav]] — 기준가 엔진 (calculate_wrap_nav.py)
- [[src-calculate-returns]] — 수익률 계산 (calculate_returns.py)
- [[src-create-portfolio-tables]] — 포트폴리오 표 생성 (create_portfolio_tables.py)
- [[src-create-contribution-data]] — 기여도 데이터 (create_contribution_data.py)
- [[src-draw-charts]] — 차트 렌더러 (draw_charts + draw_wrap_charts)
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)

## Code
- `.github/workflows/daily_crawl.yml`

## Alerts
⚠ 실패 자체 알림 없음 → gha-daily-health-check가 산출물 신선도로 포착
