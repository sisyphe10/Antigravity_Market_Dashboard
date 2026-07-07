---
id: "src-japan-capex"
name: "일본 CAPEX 지표 (fetch_japan_capex.py)"
domain: "market-global"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "23:30 (kodex 타이머 편승)"
status: "active"
code:
  - "execution/fetch_japan_capex.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# 일본 CAPEX 지표 (fetch_japan_capex.py)

**Domain:** 해외 · 매크로 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 23:30 (kodex 타이머 편승) · **Status:** active · **Project:** antigravity

일본 설비투자 3종(월간)을 수집해 dataset.csv(JP_CAPEX / CAPEX 그룹)에 적재. VM kodex 타이머 편승(GHA 해외IP 차단 회피).

- SEAJ 반도체장비 판매고(Shift-JIS xls, 파일명 매월 랜덤→라벨 파싱, 전체 upsert self-heal) + JMTBA 공작기계 수주 총액/외수(속보 PDF+확보 PDF).
- 의존성 pandas+xlrd(xls)+pypdf. 소스 단위 실패 격리, exit 0. JP_CAPEX는 신선도 감시 제외(월간 지연).
- ★비교적 신규 시리즈 — REGISTRY_NOTES 참조(전용 스케줄 문서 부재).

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_japan_capex.py`
