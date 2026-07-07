---
id: "timer-etf-collect-retry"
name: "ETF 수집 재시도 타이머 (etf-collect-retry 18:00)"
domain: "market-kr"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "18:00 매일"
status: "active"
code:
  - "scripts/etf-collect-retry.timer"
  - "launchd/timers/com.antigravity.etf-collect-retry.plist"
reads: []
writes:
  - "store-etf-db"
depends_on:
  - "src-etf-collect"
  - "timer-etf-collect"
alerts: "OnFailure → sisyphe-bot-notify@etf-collect → 텔레그램"
---

# ETF 수집 재시도 타이머 (etf-collect-retry 18:00)

**Domain:** 국내 시장 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 18:00 매일 · **Status:** active · **Project:** antigravity

16:30 수집의 실패/부분수집을 보충하는 재시도 타이머. 같은 `etf-collect.service`를 18:00 KST에 한 번 더 발화한다.

- 16:30이 성공했으면 `collect_etf_daily.py`가 즉시 스킵(idempotent no-op), 부분수집이면 already_done을 건너뛰고 나머지를 마저 수집.
- 18:30 Featured 2차(`etf.html` 재생성) 전에 끝나도록 18:00에 배치.

## Reads
- (none)

## Writes
- [[store-etf-db]] — etf_data.db (ETF 구성종목 SQLite)

## Depends on
- [[src-etf-collect]] — ETF 구성종목 수집 (collect_etf_daily.py)
- [[timer-etf-collect]] — ETF 구성종목 수집 타이머 (etf-collect 16:30)

## Code
- `scripts/etf-collect-retry.timer`
- `launchd/timers/com.antigravity.etf-collect-retry.plist`

## Alerts
⚠ OnFailure → sisyphe-bot-notify@etf-collect → 텔레그램
