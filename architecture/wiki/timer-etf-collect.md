---
id: "timer-etf-collect"
name: "ETF 구성종목 수집 타이머 (etf-collect 16:30)"
domain: "market-kr"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "16:30 매일"
status: "active"
code:
  - "scripts/etf-collect.timer"
  - "scripts/etf-collect.service"
  - "scripts/run_etf_collect.sh"
  - "launchd/timers/com.antigravity.etf-collect.plist"
reads: []
writes:
  - "store-etf-db"
depends_on:
  - "src-etf-collect"
alerts: "OnFailure → sisyphe-bot-notify@etf-collect → 텔레그램"
---

# ETF 구성종목 수집 타이머 (etf-collect 16:30)

**Domain:** 국내 시장 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 16:30 매일 · **Status:** active · **Project:** antigravity

매일 16:30 KST 전체 ETF 목록 + 구성종목/비중을 수집해 `etf_data.db`에 적재하는 타이머(`run_etf_collect.sh` → `execution/etf_collector/collect_etf_daily.py`).

- 원래 봇 apscheduler 잡이었으나 봇 재시작/배포가 진행 중인 수집을 죽이는 문제로 systemd 타이머로 분리(2026-06-25).
- 성공(collection_log ok>=1000)이면 즉시 스킵하는 idempotent 설계 → 18:00 재시도와 겹쳐도 안전.
- TimeoutStartSec=30min. 실패 시 `sisyphe-bot-notify@etf-collect`.

## Reads
- (none)

## Writes
- [[store-etf-db]] — etf_data.db (ETF 구성종목 SQLite)

## Depends on
- [[src-etf-collect]] — ETF 구성종목 수집 (collect_etf_daily.py)

## Code
- `scripts/etf-collect.timer`
- `scripts/etf-collect.service`
- `scripts/run_etf_collect.sh`
- `launchd/timers/com.antigravity.etf-collect.plist`

## Alerts
⚠ OnFailure → sisyphe-bot-notify@etf-collect → 텔레그램
