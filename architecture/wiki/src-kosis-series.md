---
id: "src-kosis-series"
name: "KOSIS 시계열 레지스트리 (fetch_kosis_series.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "23:30 (kodex 타이머 편승)"
status: "active"
code:
  - "execution/fetch_kosis_series.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# KOSIS 시계열 레지스트리 (fetch_kosis_series.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 23:30 (kodex 타이머 편승) · **Status:** active · **Project:** antigravity

KOSIS 통계(유통·소비·고용·미분양·퇴직연금 등)를 레지스트리 방식으로 수집해 dataset.csv(MACRO KOREA/CREDIT & HOUSING)에 적재.

- GHA IP가 KOSIS에 막혀 VM kodex 타이머에 편승. 백화점 매출은 신표 DT_115023_200(구표 11523은 2024.12 동결).
- 실패해도 계속(|| true).

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_kosis_series.py`
