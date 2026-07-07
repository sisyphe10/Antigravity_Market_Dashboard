---
id: "page-universe"
name: "universe.html (Universe)"
domain: "market-global"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: "생성=여러 잡"
status: "active"
code:
  - "execution/create_dashboard.py"
reads:
  - "store-universe-json"
writes: []
depends_on:
  - "src-create-dashboard"
  - "src-universe"
alerts: ""
---

# universe.html (Universe)

**Domain:** 해외 · 매크로 · **Type:** Page · **Runs on:** github · **Schedule (KST):** 생성=여러 잡 · **Status:** active · **Project:** antigravity

관심 유니버스 종목 스크리닝 페이지(시세·52주 낙폭 DD·RSI 1M·외국인 보유비중 등).

- 소스: `universe.json`/`universe_history.json`(하루 2회 yfinance) + 외국인 보유비중(INDEX_KR).
- `create_dashboard.py` 생성. 종목 추가는 `universe_tickers.csv`로.

## Reads
- [[store-universe-json]] — universe.json / universe_history.json

## Writes
- (none)

## Depends on
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)
- [[src-universe]] — 유니버스 수집 (fetch_universe.py)

## Code
- `execution/create_dashboard.py`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/universe.html)
