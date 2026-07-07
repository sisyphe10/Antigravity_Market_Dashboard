---
id: "daemon-catchup"
name: "catch-up 러너 (부팅 시 놓친 잡 복구)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "vm_macmini"
schedule_kst: "부팅 시 1회"
status: "planned"
code:
  - "launchd/system/catchup_runner.sh"
  - "launchd/system/cron_prev.py"
  - "launchd/system/com.antigravity.catchup.plist"
reads:
  - "launchd/timers/schedule.tsv"
writes: []
depends_on:
  - "infra-vm-macmini"
alerts: ""
---

# catch-up 러너 (부팅 시 놓친 잡 복구)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** vm_macmini · **Schedule (KST):** 부팅 시 1회 · **Status:** planned · **Project:** antigravity

맥미니 이전에서 systemd `Persistent=true`를 대체하는 launchd 데몬(`com.antigravity.catchup`, RunAtLoad=true). 부팅 시 1회, 맥이 꺼진 동안 마지막 스케줄 발화를 놓친 타이머 잡을 판정해 순차 재실행한다.

- 판정: 각 `schedule.tsv` 행의 cron 직전 발화(`cron_prev.py`) vs 성공 stamp 비교 → stamp<직전발화면 재실행 큐잉.
- 재실행은 잡 wrapper(`run_timer_job.sh`/`run_gha_job.sh`)를 통과 → 잡별 락·stamp·notify를 그대로 태움(이중실행 방어).
- 정전/재부팅이 잦은 가정 호스팅(UPS 부재) 가용성의 핵심. **초안·검증 완료, 맥미니 컷오버 시 활성(planned).**

## Reads
- `launchd/timers/schedule.tsv`

## Writes
- (none)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)

## Code
- `launchd/system/catchup_runner.sh`
- `launchd/system/cron_prev.py`
- `launchd/system/com.antigravity.catchup.plist`
