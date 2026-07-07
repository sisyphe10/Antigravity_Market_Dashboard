---
id: "src-silicondata"
name: "SiliconData 지수 3종 (fetch_silicondata_index.py)"
domain: "tech-semis"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "23:00 (crawler 내부)"
status: "active"
code:
  - "execution/fetch_silicondata_index.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# SiliconData 지수 3종 (fetch_silicondata_index.py)

**Domain:** 반도체 · 테크 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 23:00 (crawler 내부) · **Status:** active · **Project:** antigravity

SiliconData 포털의 LLM 토큰/H100 GPU 렌탈/RAM 지수 3종을 파싱해 dataset.csv에 적재(COMMODITIES). market_crawler가 `crawl_silicondata_indexes`로 호출.

- portal.silicondata.com RSC 파싱, 주말 포함 일별. 공개창 7일 롤링이라 백필 불가.
- 신선도 calendar 5일, 타입 3개(SDLLMTK/SDH100RT/SD_RAM) 분리.

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_silicondata_index.py`
