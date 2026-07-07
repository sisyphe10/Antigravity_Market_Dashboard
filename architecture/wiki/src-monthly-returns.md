---
id: "src-monthly-returns"
name: "월별 수익률 11지수 (fetch_monthly_returns.py)"
domain: "market-global"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "23:00 (daily_crawl)"
status: "active"
code:
  - "execution/fetch_monthly_returns.py"
reads: []
writes:
  - "monthly_returns.json"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# 월별 수익률 11지수 (fetch_monthly_returns.py)

**Domain:** 해외 · 매크로 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 23:00 (daily_crawl) · **Status:** active · **Project:** antigravity

11개 주요 지수의 월별 수익률을 수집해 `monthly_returns.json` 생성(market.html MONTHLY RETURNS 표).

- daily_crawl 초반 스텝. 표는 market.html 상단에 렌더.

## Reads
- (none)

## Writes
- `monthly_returns.json`

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_monthly_returns.py`
