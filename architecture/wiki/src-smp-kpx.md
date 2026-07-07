---
id: "src-smp-kpx"
name: "KPX 육지 SMP (fetch_smp_kpx.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "23:00 (crawler 내부)"
status: "active"
code:
  - "execution/fetch_smp_kpx.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# KPX 육지 SMP (fetch_smp_kpx.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 23:00 (crawler 내부) · **Status:** active · **Project:** antigravity

KPX 육지 SMP(한국 도매 전기 가중평균 원/kWh)를 HTML 파싱으로 수집해 dataset.csv에 통합. market_crawler가 `crawl_kpx_smp`로 호출.

- 기존 행 수정은 append 불가라 전체 재작성(self-heal 패턴).
- 단독 실행 시 1년치 backfill.

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_smp_kpx.py`
