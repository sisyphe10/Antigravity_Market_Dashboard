---
id: "src-danawa"
name: "다나와 DRAM 최저가 (fetch_danawa_price.py)"
domain: "tech-semis"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "23:00 (daily_crawl)"
status: "active"
code:
  - "execution/fetch_danawa_price.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# 다나와 DRAM 최저가 (fetch_danawa_price.py)

**Domain:** 반도체 · 테크 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 23:00 (daily_crawl) · **Status:** active · **Project:** antigravity

다나와 DRAM 소매 최저가를 수집해 dataset.csv(DRAM_RETAIL)에 적재. daily_crawl 내 tolerated 스텝.

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_danawa_price.py`
