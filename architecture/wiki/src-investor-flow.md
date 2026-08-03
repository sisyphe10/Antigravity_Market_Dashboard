---
id: "src-investor-flow"
name: "투자주체별 누적 순매수 (build_investor_flow.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "23:00 (gha-daily-crawl)"
status: "active"
code:
  - "datalake/build_investor_flow.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "infra-datalake"
alerts: ""
---

# 투자주체별 누적 순매수 (build_investor_flow.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 23:00 (gha-daily-crawl) · **Status:** active · **Project:** antigravity

2026-08-03 신설. 데이터레이크 일별 순매수(원)를 투자주체별로 2022-01-01 기점 누적(조원)해 `dataset.csv`의 `INVESTOR_FLOW` 타입 시리즈로 싣는 빌더. DATA 통합차트의 **INVESTOR FLOW 서브패널**(4개 시장 × 투자주체 분해)이 이를 소비([[src-create-dashboard]]의 `INVFLOW_*` 키와 합의).

- 입력 = 데이터레이크 parquet 2종: `kr_investor_value`(코스피/코스닥 현물)·`kr_deriv_investor`(K200·KQ150 선물, metric=value/side=net). [[src-investor-trading]]가 만드는 런타임 json과 별개로, 정정까지 반영된 데이터레이크 시계열을 원천으로 삼는다.
- 주체 = 개인·**외국인**(등록+기타 합계, 2026-08-03 사용자 확정 명명 — 종전 `foreigner_total`·등록/기타분리 폐기)·금융투자·기관(금투제외)·연기금·투신·사모·보험·은행·기타금융·기타법인.
- **매일 전 구간 결정론 재계산(멱등)** — 과거 정정이 자동 소급된다. 업서트는 텍스트 수준: 기존 `INVESTOR_FLOW` 행만 제거 후 재적재, 타 행은 바이트 불변.
- 실행 위치 = [[gha-daily-crawl]] wrapper(`run_gha_job.sh`)에서 [[src-create-dashboard]] **앞** 단계(비치명 — 실패해도 크롤 계속).

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[infra-datalake]] — 맥미니 데이터레이크 (~/datalake + 문답 위키)

## Code
- `datalake/build_investor_flow.py`
