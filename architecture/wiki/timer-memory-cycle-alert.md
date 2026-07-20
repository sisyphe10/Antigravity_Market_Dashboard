---
id: "timer-memory-cycle-alert"
name: "메모리 사이클 플랜 알림 타이머 (07:45)"
domain: "tech-semis"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "07:45 매일"
status: "active"
code:
  - "launchd/timers/com.antigravity.memory-cycle-alert.plist"
  - "launchd/timers/run_timer_job.sh"
  - "execution/memory_cycle_plan_alert.py"
reads:
  - "ext-data-apis"
writes: []
depends_on:
  - "infra-vm-macmini"
  - "infra-telegram"
  - "ext-data-apis"
alerts: "FAIL → notify_sisyphe_failure.sh memory-cycle-alert → 텔레그램"
---

# 메모리 사이클 플랜 알림 타이머 (07:45)

**Domain:** 반도체 · 테크 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 07:45 매일 · **Status:** active · **Project:** antigravity

2026-07-19 신설. 매일 07:45 KST 메모리 3사(삼성전자·SK하이닉스·마이크론) 사이클 액션플랜 레벨을 점검해 텔레그램 1통을 보내는 타이머(`com.antigravity.memory-cycle-alert` → `run_timer_job.sh memory-cycle-alert` → `execution/memory_cycle_plan_alert.py`). MU 새벽 종가 + KR 전일 종가가 모이는 아침 시간대에 실행.

- 판정 기준은 repo 밖 `work/analysis/260719_메모리3사_주가실적PER/메모리3사_사이클_리포트.md`(85% 기준). 반등고점(‘−20% 앵커 이후 최저점’이 나온 뒤의 최고 종가) vs 전고점의 84~88% ‘무인지대’ 통과를 판별해 통상형(기저율 80%, 반등 93~100%)/약세장형(20%, 천장 79~84%) 시나리오와 단계·트리거를 표시. 마이크론 84%/88%가 선행 신호.
- DRAM 현물/고정가 감시 라인(백워데이션 전조) 동반 — 현물 이력은 `logs/dram_spot_log.csv`에 누적, 고정거래가는 트렌드포스/DRAMeXchange 발표 감지 시 수동 상수 갱신.
- 데이터=yfinance 종가([[ext-data-apis]]). 발송은 `TELEGRAM_SISYPHE_BOT_TOKEN` + `TELEGRAM_CHAT_ID`로 사용자 개인 chat 1통(구독자 브로드캐스트 아님).
- 계산·적재 잡이 아니라 알림 잡 — `run_timer_job.sh` 타임아웃 300초, `RunAtLoad=false`, 설치는 `install_timers.sh` NAMES 목록. 놓친 실행을 뒤늦게 보내면 아침 점검의 의미가 없다(catch-up 성격 아님).

## Reads
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Writes
- (none)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `launchd/timers/com.antigravity.memory-cycle-alert.plist`
- `launchd/timers/run_timer_job.sh`
- `execution/memory_cycle_plan_alert.py`

## Alerts
⚠ FAIL → notify_sisyphe_failure.sh memory-cycle-alert → 텔레그램
