---
id: "src-seibro"
name: "SEIBro TOP50 (fetch_seibro_data.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "23:00 (daily_crawl)"
status: "active"
code:
  - "execution/fetch_seibro_data.py"
reads: []
writes:
  - "seibro_tickers.json"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# SEIBro TOP50 (fetch_seibro_data.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 23:00 (daily_crawl) · **Status:** active · **Project:** antigravity

SEIBro 결제 TOP 50 데이터를 Chrome selenium으로 수집해 `seibro_tickers.json` 생성(seibro.html).

- selenium 필요라 GHA에 setup-chrome 스텝, 맥미니는 부트스트랩 Chrome 전제. 실패는 tolerated.

## Reads
- (none)

## Writes
- `seibro_tickers.json`

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_seibro_data.py`
