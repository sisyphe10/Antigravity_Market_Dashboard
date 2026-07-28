---
id: "cmd-target-transform"
name: "/목표전환형 — 랩 생성·청산 일괄"
domain: "claude-tooling"
project: "antigravity"
type: "skill"
runs_on: "laptop"
schedule_kst: "호출 시"
status: "active"
code:
  - "~/.claude/commands/목표전환형.md (노트북 로컬 · main 미추적)"
  - ".claude/rules/target-transform.md"
reads: []
writes:
  - "store-wrap-nav-xlsx"
depends_on:
  - "src-create-dashboard"
  - "src-create-portfolio-tables"
  - "infra-laptop"
alerts: ""
---

# /목표전환형 — 랩 생성·청산 일괄

**Domain:** Claude 스킬 · 커맨드 · **Type:** Skill · **Runs on:** laptop · **Schedule (KST):** 호출 시 · **Status:** active · **Project:** antigravity

목표전환형 랩의 **운용 개시 / 목표달성·청산**을 7개 파일 13곳에 걸쳐 일괄 처리하고 검증·푸시까지 수행한다.

- 정본은 `execution/wrap_config.py` 단일 레지스트리 — 엔트리 1건 추가/수정이면 8개 스크립트가 나머지를 파생한다.
- 청산은 **장 마감 후 최종 NAV 산출 뒤**에만. `portfolio_config` 는 주석 처리 대신 `end_date` 를 부여한다(주석 시 마지막 1~2일 NAV 누락).
- 실행 체인: calculate_wrap_nav → calculate_returns → create_portfolio_tables → create_dashboard.

## Reads
- (none)

## Writes
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)

## Depends on
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)
- [[src-create-portfolio-tables]] — 포트폴리오 표 생성 (create_portfolio_tables.py)
- [[infra-laptop]] — 작업용 노트북 (ASUS Vivobook, Windows)

## Code
- `~/.claude/commands/목표전환형.md (노트북 로컬 · main 미추적)`
- `.claude/rules/target-transform.md`
