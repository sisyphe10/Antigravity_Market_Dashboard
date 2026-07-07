---
id: "gha-finalize-orders"
name: "Finalize Pending Orders + AUM (16:00)"
domain: "portfolio-wrap"
project: "antigravity"
type: "gha_workflow"
runs_on: "gha"
schedule_kst: "16:00 매일"
status: "active"
code:
  - ".github/workflows/finalize_orders.yml"
reads:
  - "store-orders-pending"
writes:
  - "store-wrap-nav-xlsx"
  - "store-portfolio-data"
  - "page-index"
  - "page-market"
  - "page-wrap"
  - "page-universe"
  - "page-seibro"
  - "page-featured"
depends_on:
  - "store-orders-pending"
  - "src-calculate-wrap-nav"
  - "src-calculate-returns"
  - "src-create-portfolio-tables"
  - "src-create-dashboard"
alerts: "실패 자체 알림 없음 (repo 밖 dated 산출 없음) → Phase 2 heartbeat 감시"
---

# Finalize Pending Orders + AUM (16:00)

**Domain:** 포트폴리오 · WRAP · **Type:** GHA · **Runs on:** gha · **Schedule (KST):** 16:00 매일 · **Status:** active · **Project:** antigravity

사용자가 브라우저에서 임시저장한 주문/AUM을 16:00 KST(07:00 UTC) 장 마감 후 Wrap_NAV.xlsx의 NEW/AUM 시트에 확정 반영하는 워크플로.

- 순서: finalize_pending_orders → finalize_pending_aum → calc_wrap_nav → calc_returns → create_portfolio_tables → create_dashboard → safe_push(`--xlsx-conflict fail`).
- xlsx conflict를 fail로 둔 것은 의도적 — dropped commit이 확정 편집을 조용히 잃지 않도록 수동 재실행을 유도.
- Order 최종저장은 이 워크플로를 workflow_dispatch로 즉시 트리거하기도 함.

## Reads
- [[store-orders-pending]] — orders/ (pending_orders · aum_pending)

## Writes
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)
- [[store-portfolio-data]] — portfolio_data.json
- [[page-index]] — index.html (랜딩)
- [[page-market]] — market.html (마켓 대시보드)
- [[page-wrap]] — wrap.html (WRAP 대시보드)
- [[page-universe]] — universe.html (Universe)
- [[page-seibro]] — seibro.html (SEIBro)
- [[page-featured]] — featured.html (Featured TOP)

## Depends on
- [[store-orders-pending]] — orders/ (pending_orders · aum_pending)
- [[src-calculate-wrap-nav]] — 기준가 엔진 (calculate_wrap_nav.py)
- [[src-calculate-returns]] — 수익률 계산 (calculate_returns.py)
- [[src-create-portfolio-tables]] — 포트폴리오 표 생성 (create_portfolio_tables.py)
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)

## Code
- `.github/workflows/finalize_orders.yml`

## Alerts
⚠ 실패 자체 알림 없음 (repo 밖 dated 산출 없음) → Phase 2 heartbeat 감시
