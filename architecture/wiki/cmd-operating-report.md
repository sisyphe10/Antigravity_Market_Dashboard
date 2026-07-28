---
id: "cmd-operating-report"
name: "/운용보고서 — 월간 운용보고서 4종"
domain: "claude-tooling"
project: "antigravity"
type: "skill"
runs_on: "laptop"
schedule_kst: "호출 시"
status: "active"
code:
  - "~/.claude/commands/운용보고서.md"
reads:
  - "store-wrap-nav-xlsx"
writes: []
depends_on:
  - "ext-notion"
  - "infra-laptop"
alerts: ""
---

# /운용보고서 — 월간 운용보고서 4종

**Domain:** Claude 스킬 · 커맨드 · **Type:** Skill · **Runs on:** laptop · **Schedule (KST):** 호출 시 · **Status:** active · **Project:** antigravity

라이프자산운용 월간운용보고서 docx 4종을 생성한다. 분기말에는 NH 분기운용보고서 xls 2종이 추가된다.

- 편입 종목 검증은 Wrap_NAV.xlsx 의 **NEW 시트** 기준.
- 수익률·기준가는 기존 산출물을 재사용하고, 문서 조판만 커맨드가 담당한다.

## Reads
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)

## Writes
- (none)

## Depends on
- [[ext-notion]] — Notion (실적·리서치 퍼블리시 대상)
- [[infra-laptop]] — 작업용 노트북 (ASUS Vivobook, Windows)

## Code
- `~/.claude/commands/운용보고서.md`
