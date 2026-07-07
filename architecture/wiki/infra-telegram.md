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
reads: []
writes: []
depends_on: []
alerts: ""
---

# 텔레그램 (알림·상호작용 채널)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** external · **Schedule (KST):** 상시 · **Status:** active · **Project:** antigravity

모든 봇 알림과 실패 경보가 나가는 메신저 채널. 봇별 전용 토큰(Sisyphe/RA_Sisyphe/Research Notes/선유듀오)으로 분리 운용.

- 다이제스트·리서치 알림·투자유의 요약·공시·실적·운동 기록 대화가 여기로 흐른다.
- 잡 실패는 `scripts/notify_sisyphe_failure.sh`가 텔레그램으로 발송(systemd OnFailure / launchd wrapper 공통).
- 맥미니 self-check(08:50)는 정상이어도 매일 1회 발송 → 침묵 자체가 dead-man's switch.

## Reads
- (none)

## Writes
- (none)

## Depends on
- (none)

## Code
- `scripts/notify_sisyphe_failure.sh`
