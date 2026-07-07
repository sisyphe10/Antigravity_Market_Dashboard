---
id: "src-etf-collect"
name: "ETF 구성종목 수집 (collect_etf_daily.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "16:30 / 18:00 (etf-collect 타이머)"
status: "active"
code:
  - "execution/etf_collector/collect_etf_daily.py"
  - "execution/etf_collector/etf_db.py"
  - "execution/etf_collector/etfcheck_client.py"
reads: []
writes:
  - "store-etf-db"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# ETF 구성종목 수집 (collect_etf_daily.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 16:30 / 18:00 (etf-collect 타이머) · **Status:** active · **Project:** antigravity

전체 ETF 목록 + 구성종목/비중을 etfcheck 등에서 수집해 `etf_data.db`(SQLite)에 적재.

- idempotent(성공 시 재실행 스킵). 봇에서 분리된 systemd 타이머가 소유.
- etf.html 액티브 탭·19:00 알림의 원천 DB.

## Reads
- (none)

## Writes
- [[store-etf-db]] — etf_data.db (ETF 구성종목 SQLite)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/etf_collector/collect_etf_daily.py`
- `execution/etf_collector/etf_db.py`
- `execution/etf_collector/etfcheck_client.py`
