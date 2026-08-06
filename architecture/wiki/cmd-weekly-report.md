---
id: "cmd-weekly-report"
name: "/주간보고 — 금요일 WRAP 주간 보고"
domain: "claude-tooling"
project: "antigravity"
type: "skill"
runs_on: "laptop"
schedule_kst: "호출 시"
status: "active"
code:
  - "~/.claude/commands/주간보고.md"
  - "generate_weekly_report.py"
reads:
  - "store-wrap-nav-xlsx"
writes: []
depends_on:
  - "src-report-context"
  - "infra-laptop"
alerts: ""
---

# /주간보고 — 금요일 WRAP 주간 보고

**Domain:** Claude 스킬 · 커맨드 · **Type:** Skill · **Runs on:** laptop · **Schedule (KST):** 호출 시 · **Status:** active · **Project:** antigravity

매주 금요일 대표 보고용 주간 WRAP 보고 docx 와 채팅 게시용 요약 메시지를 만든다.

- 기준은 **목요일 종가**(1W 구간), 상품별 수익률·기여 종목을 표로 싣는다.
- 요약은 문서와 별도로 채팅에 그대로 붙일 수 있는 형태로 출력한다.

## Reads
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)

## Writes
- (none)

## Depends on
- [[src-report-context]] — 보고서 컨텍스트 빌더 (build_report_context.py)
- [[infra-laptop]] — 작업용 노트북 (ASUS Vivobook, Windows)

## Code
- `~/.claude/commands/주간보고.md`
- `generate_weekly_report.py`
