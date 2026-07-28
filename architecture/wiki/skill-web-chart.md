---
id: "skill-web-chart"
name: "web-chart 스킬 (웹 인터랙티브 차트 표준)"
domain: "claude-tooling"
project: "antigravity"
type: "skill"
runs_on: "laptop"
schedule_kst: "호출 시"
status: "active"
code:
  - "~/.claude/skills/web-chart/SKILL.md"
reads: []
writes: []
depends_on:
  - "infra-laptop"
  - "page-wrap"
alerts: ""
---

# web-chart 스킬 (웹 인터랙티브 차트 표준)

**Domain:** Claude 스킬 · 커맨드 · **Type:** Skill · **Runs on:** laptop · **Schedule (KST):** 호출 시 · **Status:** active · **Project:** antigravity

대시보드 양식의 웹 인터랙티브 차트(Chart.js) 통일 표준. WRAP CHART 탭·Market DATA 차트·단독 뷰어에서 확립된 규칙을 한 곳에 모았다.

- 사이드바 계열 토글 · 트레이딩뷰식 크로스헤어+데이터 카드 · 기간 버튼 · 정규화/YTD/Log · Y축 5~95% 커버 · 끝값 라벨(겹침 회피) · **DPR 4 고해상 Download**.
- 정적 PNG(발표용)는 [[skill-seminar-chart]] 담당 — 별개 스킬이다.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[infra-laptop]] — 작업용 노트북 (ASUS Vivobook, Windows)
- [[page-wrap]] — wrap.html (WRAP 대시보드)

## Code
- `~/.claude/skills/web-chart/SKILL.md`
