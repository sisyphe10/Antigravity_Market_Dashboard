---
id: "src-create-portfolio-tables"
name: "포트폴리오 표 생성 (create_portfolio_tables.py)"
domain: "portfolio-wrap"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "체인 (finalize/recalc/crawl)"
status: "active"
code:
  - "execution/create_portfolio_tables.py"
reads:
  - "store-wrap-nav-xlsx"
writes:
  - "store-portfolio-data"
depends_on:
  - "src-calculate-returns"
alerts: ""
---

# 포트폴리오 표 생성 (create_portfolio_tables.py)

**Domain:** 포트폴리오 · WRAP · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 체인 (finalize/recalc/crawl) · **Status:** active · **Project:** antigravity

Wrap_NAV 시트를 읽어 wrap.html PORTFOLIO/Order 탭이 런타임 fetch하는 `portfolio_data.json`을 생성.

- PORTFOLIO_GROUPS로 동일 포트 묶음 표시(개방형 3종 등), EXCLUDED_PORTFOLIOS로 청산 상품 제외.
- /update·PORTFOLIO 표는 당일 finalize 주문을 D-1 지연 반영(today/disp_date, weight/weight_prev, _order_changes).

## Reads
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)

## Writes
- [[store-portfolio-data]] — portfolio_data.json

## Depends on
- [[src-calculate-returns]] — 수익률 계산 (calculate_returns.py)

## Code
- `execution/create_portfolio_tables.py`
