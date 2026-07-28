---
id: "skill-design"
name: "/설계 스킬 (착수 브리프 + codex 병렬설계)"
domain: "claude-tooling"
project: "antigravity"
type: "skill"
runs_on: "laptop"
schedule_kst: "호출 시"
status: "active"
code:
  - "~/.claude/skills/설계/SKILL.md"
reads: []
writes: []
depends_on:
  - "infra-laptop"
alerts: ""
---

# /설계 스킬 (착수 브리프 + codex 병렬설계)

**Domain:** Claude 스킬 · 커맨드 · **Type:** Skill · **Runs on:** laptop · **Schedule (KST):** 호출 시 · **Status:** active · **Project:** antigravity

새 기능·페이지·파이프라인·구조 변경을 **착수**할 때 부르는 스킬. Claude 혼자 판단하지 않게 만드는 것이 목적이다.

- 1단계 **4칸 브리프**를 빈칸 없이 확정: 완료 기준 · 레퍼런스 · 데이터 출처 · 되돌리기 위험.
- 2단계 codex(gpt-5.6-sol)와 **병렬 설계** — brief.md 를 stdin 으로 넘긴다(codex 는 세션 맥락이 없으므로 코드를 브리프에 붙여넣어야 한다).
- 3단계 두 설계의 **차이만** 취합해 추천안 1개로 좁힌다.
- 단순 수정·버그픽스·값 갱신에는 쓰지 않는다.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[infra-laptop]] — 작업용 노트북 (ASUS Vivobook, Windows)

## Code
- `~/.claude/skills/설계/SKILL.md`
