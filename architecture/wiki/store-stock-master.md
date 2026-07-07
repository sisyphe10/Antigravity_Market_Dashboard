---
id: "store-stock-master"
name: "stock_master.json (종목마스터)"
domain: "market-kr"
project: "antigravity"
type: "dataset"
runs_on: "github"
schedule_kst: "토 09:00 갱신"
status: "active"
code: []
reads: []
writes: []
depends_on:
  - "src-stock-master"
alerts: ""
---

# stock_master.json (종목마스터)

**Domain:** 국내 시장 · **Type:** Dataset · **Runs on:** github · **Schedule (KST):** 토 09:00 갱신 · **Status:** active · **Project:** antigravity

종목코드↔종목명 마스터. Order 탭 자동완성의 소스. update_stock_master 타이머가 주간 갱신.

- 코드 있는 행만 저장(이름만 입력=누락). 사명변경 미반영 시 자동완성 실패.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-stock-master]] — 종목마스터 갱신 (update_stock_master.py)

## Code
- (none)
