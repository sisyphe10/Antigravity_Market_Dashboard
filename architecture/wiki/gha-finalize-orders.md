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
  - "launchd/gha/run_gha_job.sh"
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

- 순서: finalize_pending_orders → finalize_pending_aum → calc_wrap_nav → calc_returns → create_portfolio_tables → create_dashboard → safe_push(`--xlsx-conflict fail --prefer-remote-pending`).
- xlsx conflict를 fail로 둔 것은 의도적 — dropped commit이 확정 편집을 조용히 잃지 않도록 수동 재실행을 유도.
- ★**사용자 저장 vs finalize 레이스(2026-08-12 사고 → `c499afda`)**: 잡이 도는 동안 사용자가 브라우저에서 pending을 저장하면, 잡이 시작 시점 스냅숏을 확정·비운 뒤 push하면서 그 저장을 덮어썼다(8/12 09:27 저장 유실 → `c761d6ab`로 수동 복구). 이제 safe_push `--prefer-remote-pending`이 merge 시 `orders/pending_orders.json`·`orders/aum_pending.json`이 merge-base 이후 **origin에서 전진했으면 원격(사용자 저장)을 정본으로 채택**한다. 우리 쪽 `finalizedAt` 스탬프도 함께 버려지므로 Order 탭 배지가 `(임시 저장됨)`으로 남아 **사용자가 재확정해야 함이 화면에 드러난다** — 조용한 유실 대신 눈에 보이는 미확정 상태로 바꾼 설계.
- 맥미니 트리거 경로(`launchd/gha/run_gha_job.sh` `gha-finalize-orders` 케이스)와 워크플로 YAML 양쪽에 같은 플래그를 넣어 패리티를 맞췄다.
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
- `launchd/gha/run_gha_job.sh`

## Alerts
⚠ 실패 자체 알림 없음 (repo 밖 dated 산출 없음) → Phase 2 heartbeat 감시
