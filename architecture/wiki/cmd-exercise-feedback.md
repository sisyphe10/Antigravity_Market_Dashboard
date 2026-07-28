---
id: "cmd-exercise-feedback"
name: "/운동피드백 — 선유듀오 피드백 팁 추가"
domain: "claude-tooling"
project: "antigravity"
type: "skill"
runs_on: "laptop"
schedule_kst: "호출 시"
status: "active"
code:
  - ".claude/commands/운동피드백.md"
reads: []
writes: []
depends_on:
  - "bot-seonyuduo-exercise"
alerts: ""
---

# /운동피드백 — 선유듀오 피드백 팁 추가

**Domain:** Claude 스킬 · 커맨드 · **Type:** Skill · **Runs on:** laptop · **Schedule (KST):** 호출 시 · **Status:** active · **Project:** antigravity

선유듀오 운동봇의 피드백 팁을 `seonyuduo_feedback_tips.json` 에 정규화·검증해 추가하고 VM 에 배포한다.

- 배포는 반드시 `scripts/deploy.sh` — 수동 python 실행은 파일 락으로 차단된다.
- **16:00~17:00 KST 배포 금지**(진행 중 잡 강제 종료).

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[bot-seonyuduo-exercise]] — 선유듀오 운동봇 (@SeonyuDuo_bot)

## Code
- `.claude/commands/운동피드백.md`
