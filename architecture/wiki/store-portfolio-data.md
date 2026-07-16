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
- ★**스키마 계약 — 최상위 `_` prefix 키는 메타, 나머지는 `상품명 → 보유종목 list`**: 메타 3종 `_order_changes`(당일 주문 변경)·`_portfolio_meta`(상품별 D-1 NAV YTD/누적)·`_price_asof`(가격 기준시각). **소비자는 `_` 시작 키와 비-list 값을 걸러야 한다** — 이 규약이 문서화돼 있지 않아, 신설 당일의 [[timer-wrap-principle-check]]가 메타 키를 상품으로 오인해 터졌다(`a832b91e`로 소비자 측 수정). 생산자는 그대로다. 현 소비자 4곳: `create_portfolio_tables.py`(생산) / [[page-wrap]]·[[bot-sisyphe]]·[[timer-wrap-principle-check]](소비).
- 종목 dict 필드: `name`·`weight`/`weight_prev`(D-1)·`today_return`·`cumulative_return` + **`ytd_return`(2026-07-16 추가**, 전년 말 종가 대비. 올해 상장 등 전년 데이터가 없으면 올해 첫 종가로 폴백) — 리포트 PNG의 종목별 YTD 컬럼이 이 필드를 쓴다.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-create-portfolio-tables]] — 포트폴리오 표 생성 (create_portfolio_tables.py)

## Code
- (none)
