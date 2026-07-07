---
id: "gha-recalc-wrap-nav"
name: "Recalculate Wrap NAV (xlsx push 트리거)"
domain: "portfolio-wrap"
project: "antigravity"
type: "gha_workflow"
runs_on: "gha"
schedule_kst: "push 트리거 (Wrap_NAV.xlsx)"
status: "active"
code:
  - ".github/workflows/recalc_wrap_nav.yml"
reads:
  - "store-wrap-nav-xlsx"
writes:
  - "store-portfolio-data"
  - "page-wrap"
  - "page-market"
  - "page-index"
  - "page-universe"
  - "page-seibro"
  - "page-featured"
depends_on:
  - "store-wrap-nav-xlsx"
  - "src-calculate-wrap-nav"
  - "src-calculate-returns"
  - "src-create-portfolio-tables"
  - "src-create-dashboard"
alerts: ""
---

# Recalculate Wrap NAV (xlsx push 트리거)

**Domain:** 포트폴리오 · WRAP · **Type:** GHA · **Runs on:** gha · **Schedule (KST):** push 트리거 (Wrap_NAV.xlsx) · **Status:** active · **Project:** antigravity

`Wrap_NAV.xlsx`가 push될 때마다 기준가·수익률을 재계산하고 대시보드를 재생성하는 워크플로(스케줄 없음, 파일 트리거).

- 워처가 사용자의 xlsx 편집을 push하면 여기서 라이브 wrap.html/market.html이 갱신된다.
- `wrap-nav-pipeline` concurrency로 다른 GHA와 xlsx 쓰기를 직렬화 → xlsx 가드는 사람이 직접 xlsx push할 때만 발동.
- safe_push는 `--xlsx-conflict bail --prefer-remote-portfolio`.
- 라이브 재생성 수단: `gh workflow run recalc_wrap_nav.yml`.

## Reads
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)

## Writes
- [[store-portfolio-data]] — portfolio_data.json
- [[page-wrap]] — wrap.html (WRAP 대시보드)
- [[page-market]] — market.html (마켓 대시보드)
- [[page-index]] — index.html (랜딩)
- [[page-universe]] — universe.html (Universe)
- [[page-seibro]] — seibro.html (SEIBro)
- [[page-featured]] — featured.html (Featured TOP)

## Depends on
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)
- [[src-calculate-wrap-nav]] — 기준가 엔진 (calculate_wrap_nav.py)
- [[src-calculate-returns]] — 수익률 계산 (calculate_returns.py)
- [[src-create-portfolio-tables]] — 포트폴리오 표 생성 (create_portfolio_tables.py)
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)

## Code
- `.github/workflows/recalc_wrap_nav.yml`
