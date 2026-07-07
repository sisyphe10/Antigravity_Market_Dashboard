---
id: "store-contribution-data"
name: "contribution_data.json"
domain: "portfolio-wrap"
project: "antigravity"
type: "dataset"
runs_on: "github"
schedule_kst: "23:00 재생성"
status: "active"
code: []
reads: []
writes: []
depends_on:
  - "src-create-contribution-data"
alerts: ""
---

# contribution_data.json

**Domain:** 포트폴리오 · WRAP · **Type:** Dataset · **Runs on:** github · **Schedule (KST):** 23:00 재생성 · **Status:** active · **Project:** antigravity

wrap.html 기여도 탭이 런타임 fetch하는 종목/섹터 기여도(bp) 데이터. `create_contribution_data.py`(daily_crawl)가 생성.

- Cariño NAV 정합. VE 01-02 글리치는 미해결 알려진 이슈.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-create-contribution-data]] — 기여도 데이터 (create_contribution_data.py)

## Code
- (none)
