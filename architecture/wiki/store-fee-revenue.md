---
id: "store-fee-revenue"
name: "fee_revenue.json (수수료 매출)"
domain: "portfolio-wrap"
project: "antigravity"
type: "dataset"
runs_on: "github"
schedule_kst: "수동 입력"
status: "active"
code:
  - "add_fee_revenue.py"
reads: []
writes: []
depends_on: []
alerts: ""
---

# fee_revenue.json (수수료 매출)

**Domain:** 포트폴리오 · WRAP · **Type:** Dataset · **Runs on:** github · **Schedule (KST):** 수동 입력 · **Status:** active · **Project:** antigravity

WRAP 수수료 탭 '매출' 서브탭 데이터(자문사 몫 실제 정산 수수료). 수동 입력 + `add_fee_revenue.py`로 관리.

- 청산 기준 분기 귀속(DB'차'/NH'호' 정규화). 사용자가 데이터 보내면 자동 처리→create_dashboard 재생성.
- 2026-06-17 구축·검증(미배포 상태였음).

## Reads
- (none)

## Writes
- (none)

## Depends on
- (none)

## Code
- `add_fee_revenue.py`
