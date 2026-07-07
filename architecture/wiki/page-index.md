---
id: "page-index"
name: "index.html (랜딩)"
domain: "ops-infra"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: "생성=여러 잡"
status: "active"
code:
  - "execution/create_dashboard.py"
reads:
  - "store-landing-highlights"
  - "landing_quotes.json"
  - "kofia_stats.json"
writes: []
depends_on:
  - "src-create-dashboard"
  - "src-landing-highlights"
alerts: ""
---

# index.html (랜딩)

**Domain:** 운영 · 인프라 · **Type:** Page · **Runs on:** github · **Schedule (KST):** 생성=여러 잡 · **Status:** active · **Project:** antigravity

생태계 진입점 랜딩 페이지. sparkline 회전 위젯(50슬롯)+인용구 카드, 상단 탭바 네비게이션(WRAP/Market/Architecture).

- 위젯 데이터는 `landing_highlights.json`(18:35 타이머)+`landing_quotes.json`, 예탁금/신용 차트는 `kofia_stats.json`.
- `create_dashboard.py`가 생성, kofia/finalize/recalc/crawl 등 여러 잡이 재생성.
- 좌측 'Age of Emergence' 브랜드 클릭=index로.

## Reads
- [[store-landing-highlights]] — landing_highlights.json
- `landing_quotes.json`
- `kofia_stats.json`

## Writes
- (none)

## Depends on
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)
- [[src-landing-highlights]] — 랜딩 하이라이트 생성 (create_landing_highlights.py)

## Code
- `execution/create_dashboard.py`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/index.html)
