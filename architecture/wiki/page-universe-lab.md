---
id: "page-universe-lab"
name: "universe_lab.html (Universe Lab)"
domain: "market-global"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: "생성=여러 잡"
status: "active"
code:
  - "execution/create_dashboard.py"
reads:
  - "store-universe-json"
writes: []
depends_on:
  - "src-create-dashboard"
alerts: ""
---

# universe_lab.html (Universe Lab)

**Domain:** 해외 · 매크로 · **Type:** Page · **Runs on:** github · **Schedule (KST):** 생성=여러 잡 · **Status:** active · **Project:** antigravity

Universe의 실험(lab) 변형 페이지. 사이드바/스타일을 Universe와 통일해 관리.

- `create_dashboard.py`의 PAGES 목록에 `('universe_lab','universe_lab.html','Universe Lab')`로 등록돼 함께 생성.
- 소스는 Universe와 공유(universe.json 계열).
- **nav 위치(2026-07-31)**: Universe와 함께 상단 네비 Market → **Watchlist 드롭다운 하위**로 이동([[src-nav-style]] `NAV_ITEMS`).
- **Copy 버튼(2026-08-09)**: 히트맵·섹터 로테이션·순위 변화 3패널 모두 Download 왼쪽에 Copy(클립보드 PNG) 병설 — [[page-universe]]·[[page-market]]과 동일 규격(`_copyBlobP`, ClipboardItem에 Promise Blob 전달).

## Reads
- [[store-universe-json]] — universe.json / universe_history.json

## Writes
- (none)

## Depends on
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)

## Code
- `execution/create_dashboard.py`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/universe_lab.html)
