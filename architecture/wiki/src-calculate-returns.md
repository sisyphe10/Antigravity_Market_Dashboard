---
id: "src-calculate-returns"
name: "수익률 계산 (calculate_returns.py)"
domain: "portfolio-wrap"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "체인 (finalize/recalc/crawl)"
status: "active"
code:
  - "calculate_returns.py"
reads:
  - "store-wrap-nav-xlsx"
writes:
  - "store-wrap-nav-xlsx"
depends_on:
  - "src-calculate-wrap-nav"
alerts: ""
---

# 수익률 계산 (calculate_returns.py)

**Domain:** 포트폴리오 · WRAP · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 체인 (finalize/recalc/crawl) · **Status:** active · **Project:** antigravity

기준가 시트를 받아 상품별 기간수익률(YTD 등)을 계산해 수익률 시트에 채우는 체인 단계.

- YTD 기준일(`ytd_base_dates`)은 상품 개시일. 목표전환형은 개시일=YTD 기준.
- calculate_wrap_nav 직후 실행되어 create_portfolio_tables/create_dashboard로 이어진다.

## Reads
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)

## Writes
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)

## Depends on
- [[src-calculate-wrap-nav]] — 기준가 엔진 (calculate_wrap_nav.py)

## Code
- `calculate_returns.py`
