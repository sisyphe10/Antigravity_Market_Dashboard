---
id: "src-trendforce"
name: "TrendForce 소스 (sources/trendforce.py)"
domain: "tech-semis"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "08:00 (ra-sisyphe)"
status: "active"
code:
  - "execution/sources/trendforce.py"
reads:
  - "sources.json"
writes:
  - "store-sources-state"
depends_on:
  - "src-generic-pipeline"
  - "infra-telegram"
alerts: ""
---

# TrendForce 소스 (sources/trendforce.py)

**Domain:** 반도체 · 테크 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 08:00 (ra-sisyphe) · **Status:** active · **Project:** antigravity

TrendForce 뉴스를 폴링해 Haiku 한글요약 1메시지로 발송(08:00 KST).

- 소스=wp-json REST(RSS는 캐시 동결 금지). staleness 5일. translate 활성(Haiku).

## Reads
- `sources.json`

## Writes
- [[store-sources-state]] — sources_state/ + kna_state.json

## Depends on
- [[src-generic-pipeline]] — Generic Source Pipeline (execution/sources/)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `execution/sources/trendforce.py`
