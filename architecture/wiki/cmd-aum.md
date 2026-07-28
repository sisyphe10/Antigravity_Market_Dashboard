---
id: "cmd-aum"
name: "/aum — WRAP 일일 AUM 입력"
domain: "claude-tooling"
project: "antigravity"
type: "skill"
runs_on: "laptop"
schedule_kst: "호출 시"
status: "active"
code:
  - "~/.claude/commands/aum.md"
  - "add_aum.py"
reads: []
writes:
  - "store-wrap-nav-xlsx"
depends_on:
  - "watcher-wrap-nav"
  - "gha-recalc-wrap-nav"
  - "infra-laptop"
alerts: ""
---

# /aum — WRAP 일일 AUM 입력

**Domain:** Claude 스킬 · 커맨드 · **Type:** Skill · **Runs on:** laptop · **Schedule (KST):** 호출 시 · **Status:** active · **Project:** antigravity

WRAP 일일 AUM 입력을 끝까지 자동 처리하는 커맨드. `add_aum.py` 로 Wrap_NAV.xlsx AUM 시트에 기록 → 워처가 push → recalc GHA 가 기준가 재계산 → **라이브 URL 로 검증**까지가 1회분.

- 상품 목록은 `execution/wrap_config.py` 레지스트리에서 파생 — 청산된 목표전환형에 입력하면 에러가 정상이다.
- HOLD 엣지케이스(양쪽 xlsx 수정)는 워처가 push 를 보류하고 `Wrap_NAV_push.HOLD` 를 남긴다.

## Reads
- (none)

## Writes
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)

## Depends on
- [[watcher-wrap-nav]] — Wrap_NAV 워처 (watch_wrap_nav.py)
- [[gha-recalc-wrap-nav]] — Recalculate Wrap NAV (xlsx push 트리거)
- [[infra-laptop]] — 작업용 노트북 (ASUS Vivobook, Windows)

## Code
- `~/.claude/commands/aum.md`
- `add_aum.py`
