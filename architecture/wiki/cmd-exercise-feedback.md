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

선유듀오 운동봇의 피드백 팁을 `seonyuduo_feedback_tips.json` 에 정규화·검증해 추가하고 push로 맥미니에 반영한다.

- 봇 상주처=맥미니 launchd(`com.antigravity.seonyuduo-exercise-bot`). JSON은 매 호출 재로딩이라 push+git-pull(~5분)만으로 반영.
- 코드 수정 시에만 `sudo launchctl kickstart -k system/...` 재시작(**16:00~17:00 KST 회피**).
- (구 VM deploy.sh 절차는 2026-08-03 VM 은퇴로 폐기 — `scripts/vm_legacy/`)

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[bot-seonyuduo-exercise]] — 선유듀오 운동봇 (@SeonyuDuo_bot)

## Code
- `.claude/commands/운동피드백.md`
