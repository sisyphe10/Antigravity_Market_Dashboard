---
id: "store-etf-db"
name: "etf_data.db (ETF 구성종목 SQLite)"
domain: "market-kr"
project: "antigravity"
type: "store"
runs_on: "vm_macmini"
schedule_kst: "16:30 / 18:00 갱신 (paused 2026-07-29)"
status: "frozen"
code: []
reads: []
writes: []
depends_on:
  - "src-etf-collect"
alerts: ""
---

# etf_data.db (ETF 구성종목 SQLite)

**Domain:** 국내 시장 · **Type:** Store · **Runs on:** vm_macmini · **Schedule (KST):** 16:30 / 18:00 갱신 (paused 2026-07-29) · **Status:** frozen · **Project:** antigravity

전체 ETF 목록 + 구성종목/비중을 담는 SQLite DB(~625MB, VM 로컬). etf-collect 타이머가 채운다.

- ★**2026-07-29 국내 ETF 수집 중단(사용자 결정)으로 DB는 마지막 수집분에 동결** — [[timer-etf-collect]]·[[timer-etf-collect-retry]] 정지. 신규 쓰기는 없고, 아래 소비처는 동결 스냅숏을 계속 읽는다. 재개 절차는 [[timer-etf-collect]] 참조.
- etf.html 구성종목 탭 + 액티브 ETF 변동 탭 + 19:00 알림의 원천.
- re-clone 시 백업 대상(deploy.sh BACKUP_FILES). 대용량이라 git 추적하되 주의.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-etf-collect]] — ETF 구성종목 수집 (collect_etf_daily.py)

## Code
- (none)
