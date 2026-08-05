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
- **알림 억제 게이트(2026-08-05, `notify_sisyphe_failure.sh` 내장)**: 곧 재실행되는 고빈도 잡은 **1차 실패를 침묵**하고 **연속 2회(=최종 실패)만 발송**해, 재시도로 풀리는 순단이 매번 알림을 때리던 노이즈를 없앴다. 6시간 버스트는 쿨다운으로 묶어 합산 통지. 정책 변경은 이 스크립트 한 곳만 고친다. 견고화(codex 리뷰): **발송이 ok:true로 확인된 뒤에만** 쿨다운을 기록(전송 실패 시 알림 영구 유실 차단), 상태 저장 실패는 fail-open으로 발송, `--dry-run`은 상태 불변, curl 타임아웃+3회 재시도, 원자적 상태 기록, 시계 역행 방어. 연속실패 카운터 리셋 창엔 **1시간 하한**을 둬 고빈도 잡의 지속 장애가 매번 1차로 리셋돼 침묵하는 구멍을 막았다.
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
