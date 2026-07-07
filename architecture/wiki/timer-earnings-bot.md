---
id: "timer-earnings-bot"
name: "실적봇 타이머 (earnings-bot)"
domain: "news-research"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "08:00 매일"
status: "active"
code:
  - "scripts/earnings-bot.timer"
  - "scripts/earnings-bot.service"
  - "launchd/timers/com.antigravity.earnings-bot.plist"
reads: []
writes:
  - "store-earnings-db"
depends_on:
  - "src-earnings-pipeline"
alerts: "OnFailure → earnings-bot-notify.service → notify_sisyphe_failure.sh earnings-bot → 텔레그램"
---

# 실적봇 타이머 (earnings-bot)

**Domain:** 뉴스 · 리서치 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 08:00 매일 · **Status:** active · **Project:** antigravity

매일 08:00 KST 1회 미국 실적/IR Day 파이프라인 전체를 돌리는 oneshot 타이머(`earnings-bot.timer` → `earnings-bot.service` → `python -m execution.earnings_bot.runner`).

- 한 번 호출로 캘린더 sync + EDGAR/트랜스크립트 폴링 + 번역·요약(Claude) + 노션 퍼블리시 + 아침 다이제스트를 모두 수행.
- 실행 파이프라인 상세는 `src-earnings-pipeline` 참조.
- TimeoutStartSec=45min. 실패 시 `earnings-bot-notify.service`(OnFailure)로 텔레그램.
- 함정: 2026-07-02 GHA calendar sync SA키 stale로 한 달 무성공 → 로컬 키 검증 후 secret 교체 복구.

## Reads
- (none)

## Writes
- [[store-earnings-db]] — earnings.db (실적봇 상태)

## Depends on
- [[src-earnings-pipeline]] — 실적봇 파이프라인 (execution/earnings_bot/)

## Code
- `scripts/earnings-bot.timer`
- `scripts/earnings-bot.service`
- `launchd/timers/com.antigravity.earnings-bot.plist`

## Alerts
⚠ OnFailure → earnings-bot-notify.service → notify_sisyphe_failure.sh earnings-bot → 텔레그램
