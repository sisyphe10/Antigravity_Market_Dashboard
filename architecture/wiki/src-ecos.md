---
id: "src-ecos"
name: "ECOS 한국 매크로 33종 (fetch_ecos_data.py)"
domain: "market-global"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "17:40 평일 (gha-daily-ecos)"
status: "active"
code:
  - "execution/fetch_ecos_data.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# ECOS 한국 매크로 33종 (fetch_ecos_data.py)

**Domain:** 해외 · 매크로 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 17:40 평일 (gha-daily-ecos) · **Status:** active · **Project:** antigravity

한국은행 ECOS 시계열 33종(금리/매크로/신용·부동산)을 수집해 dataset.csv DATA 섹션에 통합.

- 인자 순서 함정(ERROR-301) 주의. M2=161Y006, 분기전망=첫달 말일.
- 시장금리 817Y002·CPI·M2 등 투자용 STAT_CODE 큐레이션.

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_ecos_data.py`
