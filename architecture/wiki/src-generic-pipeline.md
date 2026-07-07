---
id: "src-generic-pipeline"
name: "Generic Source Pipeline (execution/sources/)"
domain: "news-research"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "상시 (ra-sisyphe 등록)"
status: "active"
code:
  - "execution/sources/__init__.py"
  - "execution/sources/base.py"
  - "execution/sources/_translator.py"
  - "sources.json"
reads:
  - "sources.json"
writes:
  - "store-sources-state"
depends_on:
  - "bot-ra-sisyphe"
alerts: ""
---

# Generic Source Pipeline (execution/sources/)

**Domain:** 뉴스 · 리서치 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 상시 (ra-sisyphe 등록) · **Status:** active · **Project:** antigravity

뉴스/리서치 소스를 플러그인처럼 등록·폴링하는 공용 프레임워크. `sources.json`의 enabled 항목을 RA_Sisyphe_bot 부팅 시 자동 스케줄 등록.

- 공통: base fetcher + retry + translate(Haiku) + staleness + `split_for_telegram`(헤더 고아 방지) + `sources_state/` 상태.
- 신규 소스 = `execution/sources/<name>.py` + sources.json 엔트리 + deploy.
- 현재 소스: semianalysis/trendforce/foreign_ir/kna.

## Reads
- `sources.json`

## Writes
- [[store-sources-state]] — sources_state/ + kna_state.json

## Depends on
- [[bot-ra-sisyphe]] — RA_Sisyphe_bot (리서치 알림 봇)

## Code
- `execution/sources/__init__.py`
- `execution/sources/base.py`
- `execution/sources/_translator.py`
- `sources.json`
