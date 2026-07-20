---
id: "src-fred"
name: "FRED 미국 매크로 36종 (fetch_fred_data.py)"
domain: "market-global"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "07:50 화~토 (gha-daily-fred)"
status: "active"
code:
  - "execution/fetch_fred_data.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# FRED 미국 매크로 36종 (fetch_fred_data.py)

**Domain:** 해외 · 매크로 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 07:50 화~토 (gha-daily-fred) · **Status:** active · **Project:** antigravity

미국 FRED 시계열 36종(금리/매크로/신용·부동산)을 수집해 dataset.csv DATA 섹션에 통합. 매 run 전체 재조회.

- 함정: 주간 시리즈에 5년창 금지.
- 파생 계열(2026-07-20): 원계열 36종 외에 **미 3-2-1 크랙스프레드**(NY Harbor)를 계산해 DATA COMMODITIES에 등재 — (2×휘발유 + 증류유)×42 − 3×WTI, ÷3 = $/bbl. 계산용 원계열(WTI/휘발유/증류유 스팟)은 fetch만 하고 dataset.csv엔 미등재. `--crack-only` 플래그로 원계열 재조회 churn 없이 파생만 백필.

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_fred_data.py`
