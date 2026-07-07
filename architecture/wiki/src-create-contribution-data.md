---
id: "src-create-contribution-data"
name: "기여도 데이터 (create_contribution_data.py)"
domain: "portfolio-wrap"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "23:00 (daily_crawl)"
status: "active"
code:
  - "execution/create_contribution_data.py"
reads:
  - "store-wrap-nav-xlsx"
writes:
  - "store-contribution-data"
depends_on:
  - "src-calculate-returns"
alerts: ""
---

# 기여도 데이터 (create_contribution_data.py)

**Domain:** 포트폴리오 · WRAP · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 23:00 (daily_crawl) · **Status:** active · **Project:** antigravity

종목/섹터 기여도(bp)를 Cariño 방식 NAV 정합으로 계산해 `contribution_data.json` 생성(wrap.html 기여도 탭이 런타임 fetch).

- 표준 체인(calc→returns→tables→dashboard)에 **없음** → daily_crawl이 매일 별도 실행. 즉시 반영은 직접 실행 필요.
- 상품 config는 calculate_wrap_nav와 동일 유지(청산=주석→탭 자동 제외).

## Reads
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)

## Writes
- [[store-contribution-data]] — contribution_data.json

## Depends on
- [[src-calculate-returns]] — 수익률 계산 (calculate_returns.py)

## Code
- `execution/create_contribution_data.py`
