---
id: "store-portfolio-data"
name: "portfolio_data.json"
domain: "portfolio-wrap"
project: "antigravity"
type: "dataset"
runs_on: "github"
schedule_kst: "체인 재생성"
status: "active"
code: []
reads: []
writes: []
depends_on:
  - "src-create-portfolio-tables"
alerts: ""
---

# portfolio_data.json

**Domain:** 포트폴리오 · WRAP · **Type:** Dataset · **Runs on:** github · **Schedule (KST):** 체인 재생성 · **Status:** active · **Project:** antigravity

wrap.html PORTFOLIO/Order 탭이 런타임 fetch하는 포트폴리오 표 데이터. `create_portfolio_tables.py`가 Wrap_NAV로 생성.

- 당일 finalize 주문 D-1 지연 반영 정보 포함(_order_changes 등).
- safe_commit_push에서 nightly rebuild는 OURS(최신) 유지.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-create-portfolio-tables]] — 포트폴리오 표 생성 (create_portfolio_tables.py)

## Code
- (none)
