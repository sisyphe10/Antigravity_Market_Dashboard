---
id: "store-orders-pending"
name: "orders/ (pending_orders · aum_pending)"
domain: "portfolio-wrap"
project: "antigravity"
type: "store"
runs_on: "github"
schedule_kst: "사용자 입력 + 16:00 finalize"
status: "active"
code:
  - "execution/finalize_pending_orders.py"
  - "execution/finalize_pending_aum.py"
reads: []
writes: []
depends_on: []
alerts: ""
---

# orders/ (pending_orders · aum_pending)

**Domain:** 포트폴리오 · WRAP · **Type:** Store · **Runs on:** github · **Schedule (KST):** 사용자 입력 + 16:00 finalize · **Status:** active · **Project:** antigravity

사용자가 브라우저 Order/AUM 탭에서 임시저장한 주문/AUM 누적본(GitHub Contents API로 write).

- 16:00 finalize 워크플로가 이를 Wrap_NAV.xlsx NEW/AUM 시트에 확정 반영 후 비운다.
- 최종저장 후 새로고침 입력소실 방지: pending을 Pages(빌드지연) 대신 Contents API 우선 read.

## Reads
- (none)

## Writes
- (none)

## Depends on
- (none)

## Code
- `execution/finalize_pending_orders.py`
- `execution/finalize_pending_aum.py`
