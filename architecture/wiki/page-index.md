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

팀원용 게시본(GitHub Pages)의 진입점 랜딩 페이지. sparkline 회전 위젯(50슬롯)+인용구 카드, 상단 탭바 네비게이션(WRAP/Market/Architecture).

- 위젯 데이터는 `landing_highlights.json`(18:45 타이머)+`landing_quotes.json`, 예탁금/신용 차트는 `kofia_stats.json`.
- `create_dashboard.py`가 생성, kofia/finalize/recalc/crawl 등 여러 잡이 재생성.
- 좌측 'Age of Emergence' 브랜드 클릭=index로.
- ★**개인 ts.net에서는 2026-07-16부로 폐지** — Caddy가 루트(`/`)와 `/index.html`을 **모두** `/sisyphe/memento.html`로 302 리다이렉트해 접근 경로가 없다([[web-caddy]]). 파일은 잡들이 계속 생성하고 스냅숏에도 실리지만 개인 화면에서는 도달 불가. 하루 전(07-15) 루트가 `/watchlist/`로 옮겨가며 '직접 접근으로만 열림'이던 것이 한 세대 만에 완전 폐지로 굳었다.
- **GitHub Pages(팀원용) 게시본은 종전대로 랜딩** — 이 페이지가 살아 있는 이유. 개인 뷰의 nav 재구성은 `compose_personal_view.py`가 스냅숏 사본에서만 수행하므로 repo 원본·팀 게시본은 불변([[web-publish-snapshot]]).

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
