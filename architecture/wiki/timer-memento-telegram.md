---
id: "timer-memento-telegram"
name: "Memento 점심 텔레그램 타이머 (12:00)"
domain: "personal"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "12:00 매일"
status: "active"
code:
  - "launchd/timers/com.antigravity.memento-telegram.plist"
  - "launchd/timers/run_timer_job.sh"
reads: []
writes: []
depends_on:
  - "infra-vm-macmini"
  - "infra-telegram"
  - "ext-sisyphe"
alerts: "FAIL → notify_sisyphe_failure.sh memento-telegram → 텔레그램"
---

# Memento 점심 텔레그램 타이머 (12:00)

**Domain:** 개인 · 가족 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 12:00 매일 · **Status:** active · **Project:** antigravity

2026-07-16 신설. 매일 12:00 KST '오늘의 따끔어'(Memento)를 텔레그램으로 1통 보내는 타이머(`com.antigravity.memento-telegram`). 같은 문구를 화면으로 보는 경로가 AoE 'Memento' 탭([[web-caddy]]의 기본 화면).

- **실행 스크립트는 repo 밖** — `run_timer_job.sh memento-telegram`이 `~/Journal/scripts/memento_telegram.py`를 repo venv 파이썬으로 호출한다. Journal 자산은 맥미니 로컬 전용이라 git·게시 파이프라인과 격리(전역 규칙 Journal 섹션) → 이 위키가 기술할 수 있는 실체는 타이머 배선까지다.
- wrapper 타임아웃 120초(텔레그램 1통), 설치는 `install_timers.sh` NAMES 목록. `RunAtLoad=false`.
- 계산 잡이 아니라 알림 잡 — 놓친 실행을 뒤늦게 보내면 '점심 따끔어'의 의미가 없다.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)
- [[ext-sisyphe]] — Sisyphe 가계부/운동 대시보드 + 투자일지 시트

## Code
- `launchd/timers/com.antigravity.memento-telegram.plist`
- `launchd/timers/run_timer_job.sh`

## Alerts
⚠ FAIL → notify_sisyphe_failure.sh memento-telegram → 텔레그램
