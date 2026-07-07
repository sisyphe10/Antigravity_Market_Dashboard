---
id: "gha-disabled"
name: "비활성 워크플로 (weather · calendar · portfolio-report)"
domain: "ops-infra"
project: "antigravity"
type: "gha_workflow"
runs_on: "gha"
schedule_kst: ""
status: "retired"
code:
  - ".github/workflows/daily_weather.yml.disabled"
  - ".github/workflows/daily_calendar.yml.disabled"
  - ".github/workflows/daily_portfolio_report.yml.disabled"
reads: []
writes: []
depends_on: []
alerts: ""
---

# 비활성 워크플로 (weather · calendar · portfolio-report)

**Domain:** 운영 · 인프라 · **Type:** GHA · **Runs on:** gha · **Status:** retired · **Project:** antigravity

`.yml.disabled` 확장자로 꺼둔 워크플로 3종. 기능이 봇 내부 잡으로 흡수돼 은퇴.

- `daily_weather.yml.disabled`(05:00 날씨) → Sisyphe-Bot 05:00 날씨 잡으로 대체.
- `daily_calendar.yml.disabled`(05:10 캘린더) → Sisyphe-Bot 05:05 캘린더 잡으로 대체.
- `daily_portfolio_report.yml.disabled`(평일 16:00 리포트) → Sisyphe-Bot 17:00 리포트 잡으로 대체.
- 확장자만 되돌리면 부활 가능하나 현재 중복이라 비활성 유지.

## Reads
- (none)

## Writes
- (none)

## Depends on
- (none)

## Code
- `.github/workflows/daily_weather.yml.disabled`
- `.github/workflows/daily_calendar.yml.disabled`
- `.github/workflows/daily_portfolio_report.yml.disabled`
