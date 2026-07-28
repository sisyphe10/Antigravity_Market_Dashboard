---
id: "cmd-urgent-comment"
name: "/긴급코멘트 — 급락일 시장 코멘트"
domain: "claude-tooling"
project: "antigravity"
type: "skill"
runs_on: "laptop"
schedule_kst: "호출 시"
status: "active"
code:
  - "~/.claude/commands/긴급코멘트.md"
reads: []
writes: []
depends_on:
  - "infra-laptop"
alerts: ""
---

# /긴급코멘트 — 급락일 시장 코멘트

**Domain:** Claude 스킬 · 커맨드 · **Type:** Skill · **Runs on:** laptop · **Schedule (KST):** 호출 시 · **Status:** active · **Project:** antigravity

급락일에 WRAP 고객 송부용 긴급 시장 코멘트 docx 를 만든다(260707 확정 양식).

- 파일명 규약 `YYMMDD_라이프자산_WRAP…` — 요약본과 본문 2종.
- 지수·업종·수급 숫자는 대시보드 산출물에서 가져와 사람이 쓴 코멘트에 얹는다.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[infra-laptop]] — 작업용 노트북 (ASUS Vivobook, Windows)

## Code
- `~/.claude/commands/긴급코멘트.md`
