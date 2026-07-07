---
id: "timer-etf-active-alert"
name: "액티브 ETF 변동 알림 타이머 (19:00)"
domain: "market-kr"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "19:00 매일"
status: "active"
code:
  - "scripts/etf-active-alert.timer"
  - "scripts/etf-active-alert.service"
  - "scripts/run_etf_active_alert.sh"
  - "execution/etf_active_alert.py"
  - "launchd/timers/com.antigravity.etf-active-alert.plist"
reads:
  - "store-etf-db"
writes:
  - ".etf_active_alert_sent.json"
depends_on:
  - "src-active-etf"
  - "timer-etf-collect"
  - "infra-telegram"
alerts: "OnFailure → sisyphe-bot-notify@etf-active-alert → 텔레그램"
---

# 액티브 ETF 변동 알림 타이머 (19:00)

**Domain:** 국내 시장 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 19:00 매일 · **Status:** active · **Project:** antigravity

매일 19:00 KST 전 액티브 ETF의 전일 대비 신규편입/편출/비중급변을 계산해 구독자에게 브로드캐스트하는 타이머(`run_etf_active_alert.sh` → `execution/etf_active_alert.py`).

- 대시보드 `etf.html` '액티브 ETF' 탭과 동일한 단일 출처 모듈(`active_etf_changes.py`)로 계산 → 숫자 일치.
- MMF/채권 제외(주식형만, 액티브 ~313개). dedup=`.etf_active_alert_sent.json`(키=latest 날짜→휴장일 무발송).
- 수집 16:30/재시도 18:00/etf.html 18:30 이후라 19:00 배치.

## Reads
- [[store-etf-db]] — etf_data.db (ETF 구성종목 SQLite)

## Writes
- `.etf_active_alert_sent.json`

## Depends on
- [[src-active-etf]] — 액티브 ETF 변동 (active_etf_changes.py)
- [[timer-etf-collect]] — ETF 구성종목 수집 타이머 (etf-collect 16:30)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `scripts/etf-active-alert.timer`
- `scripts/etf-active-alert.service`
- `scripts/run_etf_active_alert.sh`
- `execution/etf_active_alert.py`
- `launchd/timers/com.antigravity.etf-active-alert.plist`

## Alerts
⚠ OnFailure → sisyphe-bot-notify@etf-active-alert → 텔레그램
