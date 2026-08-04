---
id: "src-index-value"
name: "지수 거래대금·거래량 (build_index_value.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "23:00 (gha-daily-crawl)"
status: "active"
code:
  - "datalake/build_index_value.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "infra-datalake"
alerts: ""
---

# 지수 거래대금·거래량 (build_index_value.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 23:00 (gha-daily-crawl) · **Status:** active · **Project:** antigravity

2026-08-04 신설. 지수 **거래대금·거래량**을 데이터레이크에서 뽑아 `dataset.csv` 에 싣는 빌더 (DATA 통합차트 INDEX 그룹 6종). 백필과 일일 갱신이 같은 원천이라 계단·불연속이 없다.

- **KOSPI/KOSDAQ 거래대금(원)** ← `kr_index_ohlcv.value` = 시장 전 종목 거래대금 합. ★KRX OpenAPI `idx/*_dd_trd` 의 `ACC_TRDVAL` 은 **지수 구성종목 기준**이라 시장 전체보다 작다(코스닥 평균 -0.81%·최대 -10.4% 실측, 코스피는 -0.01%) — 통상 보도되는 거래대금과 달라 미채택.
- **S&P500/나스닥 거래량(주)** ← `global_markets` `^GSPC`/`^IXIC` volume(구성종목 거래주식수 합). 미국은 지수 단위 '거래대금(달러)' 공개 원천이 없다.
- **SPY/QQQ 거래대금(달러)** ← `global_markets` close×volume(종가 기준 근사). 두 ETF는 이 목적으로 [[infra-datalake]] BENCHMARKS 에 2026-08-04 추가.
- 업서트는 텍스트 수준(제품명 6종 행만 제거 후 재적재, 타 행 바이트 불변), 2022-01-01 기점 **매일 전 구간 재계산(멱등)**. 실행 위치 = [[gha-daily-crawl]] wrapper 에서 [[src-create-dashboard]] **앞** 단계(비치명).

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[infra-datalake]] — 맥미니 데이터레이크 (~/datalake + 문답 위키)

## Code
- `datalake/build_index_value.py`
