---
id: "src-krx-foreign"
name: "외국인 보유비중 (fetch_krx_foreign.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "23:00 (daily_crawl)"
status: "active"
code:
  - "execution/fetch_krx_foreign.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# 외국인 보유비중 (fetch_krx_foreign.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 23:00 (daily_crawl) · **Status:** active · **Project:** antigravity

코스피/코스닥 + 주요 6종목 외국인 보유비중(pykrx 로그인)을 수집해 dataset.csv(INDEX_KR)에 적재. universe/차트에서 소비.

- 항상 레벨%(누적 아님). 휴장일 조용히 skip, push는 [skip ci].
- GHA IP 로그인 차단 시 VM 이전 대상.

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_krx_foreign.py`
