---
id: "src-active-etf"
name: "액티브 ETF 변동 (active_etf_changes.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "19:00 (etf-active-alert) / 18:30 (etf.html)"
status: "active"
code:
  - "execution/etf_collector/active_etf_changes.py"
  - "execution/etf_active_alert.py"
reads:
  - "store-etf-db"
writes: []
depends_on:
  - "src-etf-collect"
alerts: ""
---

# 액티브 ETF 변동 (active_etf_changes.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 19:00 (etf-active-alert) / 18:30 (etf.html) · **Status:** active · **Project:** antigravity

etf_data.db에서 전 액티브 ETF의 전일 대비 신규편입/편출/비중급변을 계산하는 단일 출처 모듈.

- etf.html '액티브 ETF' 탭 임베드 JSON과 19:00 텔레그램 알림(`etf_active_alert.py`)이 모두 이 모듈을 써 숫자가 일치.
- MMF/채권 제외(주식형만, ~313개).

## Reads
- [[store-etf-db]] — etf_data.db (ETF 구성종목 SQLite)

## Writes
- (none)

## Depends on
- [[src-etf-collect]] — ETF 구성종목 수집 (collect_etf_daily.py)

## Code
- `execution/etf_collector/active_etf_changes.py`
- `execution/etf_active_alert.py`
