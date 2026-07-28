---
id: "cmd-chart"
name: "/차트 — 발표용 차트 호출"
domain: "claude-tooling"
project: "antigravity"
type: "skill"
runs_on: "laptop"
schedule_kst: "호출 시"
status: "active"
code:
  - "~/.claude/commands/차트.md"
reads: []
writes: []
depends_on:
  - "skill-seminar-chart"
alerts: ""
---

# /차트 — 발표용 차트 호출

**Domain:** Claude 스킬 · 커맨드 · **Type:** Skill · **Runs on:** laptop · **Schedule (KST):** 호출 시 · **Status:** active · **Project:** antigravity

발표·PPT용 차트를 그릴 때 부르는 얇은 진입점. 실제 규칙은 [[skill-seminar-chart]] 가 갖고 있고 이 커맨드는 그 스킬을 호출한다.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[skill-seminar-chart]] — seminar-chart 스킬 (발표·PPT 정적 차트)

## Code
- `~/.claude/commands/차트.md`
