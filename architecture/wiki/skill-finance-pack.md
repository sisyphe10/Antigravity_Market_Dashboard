---
id: "skill-finance-pack"
name: "금융 분석 스킬 팩 (설치형 8종)"
domain: "claude-tooling"
project: "antigravity"
type: "skill"
runs_on: "laptop"
schedule_kst: "호출 시"
status: "active"
code:
  - "~/.claude/skills/ (competitive-analysis · corporate-network-analysis · earnings-analysis · finance-super-skill · growth-stock-analysis · investment-report-reader · supply-chain-pass-through · thematic-investment-research)"
reads: []
writes: []
depends_on:
  - "infra-laptop"
alerts: ""
---

# 금융 분석 스킬 팩 (설치형 8종)

**Domain:** Claude 스킬 · 커맨드 · **Type:** Skill · **Runs on:** laptop · **Schedule (KST):** 호출 시 · **Status:** active · **Project:** antigravity

직접 만든 것이 아니라 **설치해 둔** 범용 금융·리서치 분석 스킬 8종. dart/sec-edgar MCP 와 함께 도입했다.

- 기업 경쟁력 11차원(competitive-analysis) · 지배구조/네트워크(corporate-network-analysis) · 실적 업데이트 리포트(earnings-analysis) · 성장주 프레임(growth-stock-analysis).
- PDF 셀사이드 리포트 판독(investment-report-reader) · 공급망 전가 분석(supply-chain-pass-through) · 테마 리서치(thematic-investment-research) · 회계/재무 종합(finance-super-skill).
- 이 시스템의 파이프라인과 직접 연결되지는 않는다(분석 작업용 도구).

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[infra-laptop]] — 작업용 노트북 (ASUS Vivobook, Windows)

## Code
- `~/.claude/skills/ (competitive-analysis · corporate-network-analysis · earnings-analysis · finance-super-skill · growth-stock-analysis · investment-report-reader · supply-chain-pass-through · thematic-investment-research)`
