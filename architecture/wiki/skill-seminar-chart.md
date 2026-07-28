---
id: "skill-seminar-chart"
name: "seminar-chart 스킬 (발표·PPT 정적 차트)"
domain: "claude-tooling"
project: "antigravity"
type: "skill"
runs_on: "laptop"
schedule_kst: "호출 시"
status: "active"
code:
  - "~/.claude/skills/seminar-chart/SKILL.md"
  - "~/.claude/skills/seminar-chart/chart_styles.py"
reads: []
writes: []
depends_on:
  - "infra-laptop"
alerts: ""
---

# seminar-chart 스킬 (발표·PPT 정적 차트)

**Domain:** Claude 스킬 · 커맨드 · **Type:** Skill · **Runs on:** laptop · **Schedule (KST):** 호출 시 · **Status:** active · **Project:** antigravity

발표·PPT·세미나용 matplotlib 차트를 'Market 대시보드' 양식으로 그리는 규칙 모음.

- 확정 규칙: 점선 그리드 · 위/오른쪽 테두리 제거 · **끝값만 라벨(동그라미)** · 하단 범례 · 제목/Y축 라벨 없음 · Pretendard · 좌우 2패널 비교.
- 재사용 헬퍼 `chart_styles.py` 가 위 룩을 자동 적용한다.
- 데이터 수집은 범위 밖 — '룩과 규칙'만 담당한다.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[infra-laptop]] — 작업용 노트북 (ASUS Vivobook, Windows)

## Code
- `~/.claude/skills/seminar-chart/SKILL.md`
- `~/.claude/skills/seminar-chart/chart_styles.py`
