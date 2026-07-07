---
id: "src-krx-valuation"
name: "KRX 지수 밸류에이션 (fetch_krx_valuation.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "18:30 평일 (gha-daily-krx-valuation)"
status: "active"
code:
  - "execution/fetch_krx_valuation.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# KRX 지수 밸류에이션 (fetch_krx_valuation.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 18:30 평일 (gha-daily-krx-valuation) · **Status:** active · **Project:** antigravity

코스피/코스닥 지수 후행 PER/PBR/배당수익률(pykrx data.krx 로그인)을 수집해 dataset.csv(INDEX_KOREA)에 적재.

- 클라우드 IP서도 로그인됨. forward PER은 미제공(Quantiwise 영역).

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_krx_valuation.py`
