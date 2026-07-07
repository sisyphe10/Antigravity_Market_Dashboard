---
id: "src-universe"
name: "유니버스 수집 (fetch_universe.py)"
domain: "market-global"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "18:30 / 07:00 (gha-daily-universe)"
status: "active"
code:
  - "execution/fetch_universe.py"
  - "execution/fetch_index_returns.py"
reads:
  - "universe_tickers.csv"
writes:
  - "store-universe-json"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# 유니버스 수집 (fetch_universe.py)

**Domain:** 해외 · 매크로 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 18:30 / 07:00 (gha-daily-universe) · **Status:** active · **Project:** antigravity

관심 유니버스 종목 시세/지표를 yfinance로 수집해 `universe.json`+`universe_history.json` 생성.

- 52주 낙폭(DD), RSI(1M)는 fetch_index_returns 산출을 소비.
- 종목 추가=universe_tickers.csv 행+타겟 주입(전체 2회 실행 금지). 멀티인스턴스는 별도 경로.

## Reads
- `universe_tickers.csv`

## Writes
- [[store-universe-json]] — universe.json / universe_history.json

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_universe.py`
- `execution/fetch_index_returns.py`
