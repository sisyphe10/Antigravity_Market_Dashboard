---
id: "store-sources-state"
name: "sources_state/ + kna_state.json"
domain: "news-research"
project: "antigravity"
type: "store"
runs_on: "vm_macmini"
schedule_kst: "소스 폴링 시"
status: "active"
code: []
reads: []
writes: []
depends_on:
  - "src-generic-pipeline"
alerts: ""
---

# sources_state/ + kna_state.json

**Domain:** 뉴스 · 리서치 · **Type:** Store · **Runs on:** vm_macmini · **Schedule (KST):** 소스 폴링 시 · **Status:** active · **Project:** antigravity

Generic Source Pipeline이 소스별 '마지막으로 본 항목'을 기록하는 상태 저장소(중복 발송 방지).

- foreign_ir/semianalysis/trendforce/kna 각 소스의 dedup 상태. id체계 바뀌면 state 시딩 필수.
- kna_state.json은 KNA/KNEISS 마지막 글 ID.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-generic-pipeline]] — Generic Source Pipeline (execution/sources/)

## Code
- (none)
