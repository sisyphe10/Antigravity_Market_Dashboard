---
id: "infra-telegram"
name: "텔레그램 (알림·상호작용 채널)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "external"
schedule_kst: "상시"
status: "active"
code:
  - "scripts/notify_sisyphe_failure.sh"
  - "scripts/diagnose_failure.sh"
reads: []
writes: []
depends_on: []
alerts: ""
---

# 텔레그램 (알림·상호작용 채널)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** external · **Schedule (KST):** 상시 · **Status:** active · **Project:** antigravity

모든 봇 알림과 실패 경보가 나가는 메신저 채널. 봇별 전용 토큰(Sisyphe/RA_Sisyphe/Research Notes/선유듀오)으로 분리 운용.

- 다이제스트·리서치 알림·투자유의 요약·공시·실적·운동 기록 대화가 여기로 흐른다.
- 잡 실패는 `scripts/notify_sisyphe_failure.sh`가 텔레그램으로 발송(systemd OnFailure / launchd wrapper 공통). 잡별 문구가 case로 분기하되, 모르는 잡 이름도 기본 문구로 반드시 알린다(누락 방지).
- **자가치료 2단계 — 실패 자가진단(2026-07-16, `scripts/diagnose_failure.sh`)**: 기본 실패 알림을 보낸 뒤 `nohup` 백그라운드로 headless claude를 띄워 실패 잡의 로그와 repo 코드를 읽히고, 원인 진단·복구 명령·수리 제안을 🩺 후속 메시지로 보낸다.
  - **어떤 파일도 수정하지 않는다 — 진단 전용**. allowedTools = Read/Glob/Grep + `git log/show/diff`(전부 읽기 전용).
  - 가드레일: 잡당 **60분 쿨다운**(`DIAG_COOLDOWN_SEC`) — 크래시 루프가 claude 세션을 연쇄 생성하지 못하게. `--max-turns` 25(`DIAG_MAX_TURNS`), 월클럭 600초(`DIAG_WALL_SEC`). claude 미설치·토큰 부재 시 조용히 종료(기본 알림은 이미 나갔으므로 무해).
- 맥미니 self-check(08:50)는 정상이어도 매일 1회 발송 → 침묵 자체가 dead-man's switch.

## Reads
- (none)

## Writes
- (none)

## Depends on
- (none)

## Code
- `scripts/notify_sisyphe_failure.sh`
- `scripts/diagnose_failure.sh`
