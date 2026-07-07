---
id: "daemon-crash-watcher"
name: "크래시 루프 워처 (*/5)"
domain: "ops-infra"
project: "antigravity"
type: "watcher"
runs_on: "vm_macmini"
schedule_kst: "*/5분"
status: "planned"
code:
  - "launchd/system/crash_watcher.sh"
  - "launchd/system/com.antigravity.crash-watcher.plist"
reads:
  - "logs/launchd/starts/"
writes: []
depends_on:
  - "infra-vm-macmini"
  - "infra-telegram"
alerts: "크래시 루프 감지 → notify_sisyphe_failure.sh <봇> → 텔레그램"
---

# 크래시 루프 워처 (*/5)

**Domain:** 운영 · 인프라 · **Type:** Watcher · **Runs on:** vm_macmini · **Schedule (KST):** */5분 · **Status:** planned · **Project:** antigravity

맥미니 이전에서 systemd `StartLimitBurst`를 대체하는 launchd 데몬(`com.antigravity.crash-watcher`, StartInterval=300). KeepAlive 봇이 크래시 루프에 빠지면 텔레그램 경보.

- 봇 wrapper가 매 기동 시 `logs/launchd/starts/<봇>.log`에 epoch 한 줄 append → 워처가 600초 창 내 5회+ 시작을 루프로 판정.
- 쿨다운 30분(중복 경보 억제), 성공 알림 시에만 쿨다운 stamp 기록.
- **초안·검증 완료, 맥미니 컷오버 시 활성(planned).** VM에선 systemd StartLimit이 대응.

## Reads
- `logs/launchd/starts/`

## Writes
- (none)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `launchd/system/crash_watcher.sh`
- `launchd/system/com.antigravity.crash-watcher.plist`

## Alerts
⚠ 크래시 루프 감지 → notify_sisyphe_failure.sh <봇> → 텔레그램
