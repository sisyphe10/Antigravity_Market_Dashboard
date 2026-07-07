---
id: "page-seibro"
name: "seibro.html (SEIBro)"
domain: "market-kr"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: "생성=여러 잡"
status: "active"
code:
  - "execution/create_dashboard.py"
reads:
  - "seibro_tickers.json"
writes: []
depends_on:
  - "src-create-dashboard"
  - "src-seibro"
alerts: ""
---

# seibro.html (SEIBro)

**Domain:** 국내 시장 · **Type:** Page · **Runs on:** github · **Schedule (KST):** 생성=여러 잡 · **Status:** active · **Project:** antigravity

SEIBro 결제(예탁결제) TOP 50 관련 데이터 페이지.

- 소스: `fetch_seibro_data.py`(daily_crawl 내 selenium 수집) 산출 `seibro_tickers.json`.
- `create_dashboard.py` 생성. Chrome selenium 필요라 GHA에 setup-chrome 스텝.

## Reads
- `seibro_tickers.json`

## Writes
- (none)

## Depends on
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)
- [[src-seibro]] — SEIBro TOP50 (fetch_seibro_data.py)

## Code
- `execution/create_dashboard.py`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/seibro.html)
