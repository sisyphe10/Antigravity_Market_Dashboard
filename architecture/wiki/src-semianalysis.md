---
id: "src-semianalysis"
name: "SemiAnalysis 소스 (sources/semianalysis.py)"
domain: "tech-semis"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "09:00 / 21:00 (ra-sisyphe)"
status: "active"
code:
  - "execution/sources/semianalysis.py"
reads:
  - "sources.json"
writes:
  - "store-sources-state"
depends_on:
  - "src-generic-pipeline"
  - "infra-telegram"
alerts: ""
---

# SemiAnalysis 소스 (sources/semianalysis.py)

**Domain:** 반도체 · 테크 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 09:00 / 21:00 (ra-sisyphe) · **Status:** active · **Project:** antigravity

SemiAnalysis 뉴스레터 신규 글을 폴링해 텔레그램 다이제스트로 발송(09:00/21:00 KST).

- 소스=wp-json REST(RSS는 캐시 동결이라 금지). staleness 21일.
- Generic Source Pipeline 위에서 동작.

## Reads
- `sources.json`

## Writes
- [[store-sources-state]] — sources_state/ + kna_state.json

## Depends on
- [[src-generic-pipeline]] — Generic Source Pipeline (execution/sources/)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `execution/sources/semianalysis.py`
