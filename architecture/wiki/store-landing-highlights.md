---
id: "store-landing-highlights"
name: "landing_highlights.json"
domain: "ops-infra"
project: "antigravity"
type: "dataset"
runs_on: "github"
schedule_kst: "18:35 갱신"
status: "active"
code: []
reads: []
writes: []
depends_on:
  - "src-landing-highlights"
alerts: ""
---

# landing_highlights.json

**Domain:** 운영 · 인프라 · **Type:** Dataset · **Runs on:** github · **Schedule (KST):** 18:35 갱신 · **Status:** active · **Project:** antigravity

index.html 회전 위젯(sparkline+코멘트, 50슬롯) 데이터. landing-highlights 타이머가 생성.

- 여러 산출물에서 하이라이트를 종합. index.html이 런타임 소비.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-landing-highlights]] — 랜딩 하이라이트 생성 (create_landing_highlights.py)

## Code
- (none)
