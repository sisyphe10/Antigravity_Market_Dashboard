---
id: "src-report-context"
name: "보고서 컨텍스트 빌더 (build_report_context.py)"
domain: "news-research"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "보고서 커맨드 호출 시 (SSH 1회)"
status: "active"
code:
  - "datalake/build_report_context.py"
reads:
  - "store-research-notes-db"
  - "store-tag-index"
writes: []
depends_on:
  - "src-research-tagging"
alerts: ""
---

# 보고서 컨텍스트 빌더 (build_report_context.py)

**Domain:** 뉴스 · 리서치 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 보고서 커맨드 호출 시 (SSH 1회) · **Status:** active · **Project:** antigravity

2026-08-06 신설. 보고서 커맨드([[cmd-operating-report]]·[[cmd-weekly-report]]·[[cmd-urgent-comment]])가 SSH 1회로 호출하는 **freshness preflight + 구조화 컨텍스트** 빌더. "레이크가 완전한가"를 원천 DB와 실시간 대조로 판정하고, 불완전하면 `exit 2`로 끝나 커맨드가 폴백(Notion 리서치노트·로컬 보고서 폴더)으로 넘어가게 한다.

- 호출: `--kind monthly --period YYYY-MM` / `--kind weekly --date YYYY-MM-DD` / `--kind comment --date YYYY-MM-DD`. stdout에 JSON 1개(섹션별 status/count), exit 0=complete · 2=incomplete(폴백) · 1=사용 오류.
- **freshness 게이트**: 레이크 research_notes md를 원천 [[store-research-notes-db]]와 실시간 대조(누락 시 hint로 `export_research_notes.py --from/--to` 재수출 안내), [[store-tag-index]]가 대상 기간 md보다 오래되면 `stale` 경고(23:20 [[src-research-tagging]] 잡이 자동 갱신).
- **구조화 컨텍스트**: `datalake/reports/{monthly,weekly,comments}/`의 직전 보고서를 종류·날짜 조건으로 선별(월간=직전월 5건·주간=전주 2건·코멘트=전일 2건), 테마 빈도 집계, comment kind는 전일 리서치 메시지도 첨부.
- **as-of 원칙**: 과거 월 재생성 시 period 말일 이후 자료는 테마 집계·직전 보고서 선정에서 제외해 look-ahead를 차단.

## Reads
- [[store-research-notes-db]] — research_notes.db + media/ (리서치봇)
- [[store-tag-index]] — 통합 태그 인덱스 (tag_index.sqlite + doc_tag_state.sqlite)

## Writes
- (none)

## Depends on
- [[src-research-tagging]] — Research Notes 태깅 파이프라인 (datalake/tagging/)

## Code
- `datalake/build_report_context.py`
