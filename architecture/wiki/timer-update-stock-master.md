---
id: "timer-update-stock-master"
name: "종목마스터 주간 갱신 타이머 (토 09:00)"
domain: "market-kr"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "토 09:00"
status: "active"
code:
  - "scripts/update-stock-master.timer"
  - "scripts/update-stock-master.service"
  - "scripts/run_update_stock_master.sh"
  - "launchd/timers/com.antigravity.update-stock-master.plist"
reads: []
writes:
  - "store-stock-master"
depends_on:
  - "src-stock-master"
alerts: "OnFailure → sisyphe-bot-notify@update-stock-master → 텔레그램"
---

# 종목마스터 주간 갱신 타이머 (토 09:00)

**Domain:** 국내 시장 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 토 09:00 · **Status:** active · **Project:** antigravity

매주 토요일 09:00 KST 신규상장/사명변경을 KRX에서 점검해 Code 시트→`stock_master.json`을 갱신하는 타이머(`run_update_stock_master.sh` → `update_stock_master.py`).

- Order 탭 자동완성이 이 마스터를 소비 → 사명변경 미반영 시 자동완성 실패(리가켐 사고 교훈).
- 함정: 코드 있는 행만 저장(이름만 입력=조용히 누락).
- TimeoutStartSec=15min.

## Reads
- (none)

## Writes
- [[store-stock-master]] — stock_master.json (종목마스터)

## Depends on
- [[src-stock-master]] — 종목마스터 갱신 (update_stock_master.py)

## Code
- `scripts/update-stock-master.timer`
- `scripts/update-stock-master.service`
- `scripts/run_update_stock_master.sh`
- `launchd/timers/com.antigravity.update-stock-master.plist`

## Alerts
⚠ OnFailure → sisyphe-bot-notify@update-stock-master → 텔레그램
