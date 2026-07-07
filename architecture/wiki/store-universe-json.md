---
id: "store-universe-json"
name: "universe.json / universe_history.json"
domain: "market-global"
project: "antigravity"
type: "dataset"
runs_on: "github"
schedule_kst: "18:30 / 07:00 갱신"
status: "active"
code: []
reads: []
writes: []
depends_on:
  - "src-universe"
alerts: ""
---

# universe.json / universe_history.json

**Domain:** 해외 · 매크로 · **Type:** Dataset · **Runs on:** github · **Schedule (KST):** 18:30 / 07:00 갱신 · **Status:** active · **Project:** antigravity

유니버스 종목 시세/지표(현재값 + 히스토리). fetch_universe(하루 2회)가 생성, universe.html/universe_lab.html이 소비.

- universe_history.json은 시계열(~1.2MB). 종목 추가는 universe_tickers.csv로.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-universe]] — 유니버스 수집 (fetch_universe.py)

## Code
- (none)
