---
id: "timer-etf-collect"
name: "ETF 구성종목 수집 타이머 (etf-collect 16:30)"
domain: "market-kr"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "16:30 매일 (paused 2026-07-29)"
status: "frozen"
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

**Domain:** 국내 시장 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 16:30 매일 (paused 2026-07-29) · **Status:** frozen · **Project:** antigravity

**★ 2026-07-29 국내 ETF 수집 중단(사용자 결정)** — `schedule.tsv`의 두 타이머 행(etf-collect·etf-collect-retry) 주석 처리 + `install_timers.sh` NAMES에서 제외, `/Library/LaunchDaemons` plist는 부팅 해제·삭제했다. plist **소스는 보존** → 재개 시 NAMES에 두 이름 복원 + schedule.tsv 주석 해제 후 `sudo ./install_timers.sh`. 매실패 텔레그램 notify와 [[daemon-daily-selfcheck]] STALE 라인도 함께 멎는다. [[store-etf-db]]는 마지막 수집분으로 동결.

매일 16:30 KST 전체 ETF 목록 + 구성종목/비중을 수집해 `etf_data.db`에 적재하던 타이머(`run_etf_collect.sh` → `execution/etf_collector/collect_etf_daily.py`).

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
