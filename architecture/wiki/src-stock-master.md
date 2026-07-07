---
id: "src-stock-master"
name: "종목마스터 갱신 (update_stock_master.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "토 09:00 (update-stock-master 타이머)"
status: "active"
code:
  - "execution/update_stock_master.py"
reads: []
writes:
  - "store-stock-master"
depends_on:
  - "ext-data-apis"
alerts: "OnFailure(update-stock-master) → 텔레그램"
---

# 종목마스터 갱신 (update_stock_master.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 토 09:00 (update-stock-master 타이머) · **Status:** active · **Project:** antigravity

KRX 신규상장/사명변경을 점검해 Code 시트→`stock_master.json` 갱신(Order 자동완성 소스).

- 코드 있는 행만 저장(이름만=조용히 누락). 사명변경 미반영=자동완성 실패(리가켐 사고).

## Reads
- (none)

## Writes
- [[store-stock-master]] — stock_master.json (종목마스터)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/update_stock_master.py`

## Alerts
⚠ OnFailure(update-stock-master) → 텔레그램
