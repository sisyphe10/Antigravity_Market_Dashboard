---
id: "page-universe-lab"
name: "universe_lab.html (Universe Lab)"
domain: "market-global"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: ""
status: "active"
code:
  - "universe_lab.html"
reads:
  - "store-universe-json"
writes: []
depends_on:
  - "src-universe"
alerts: ""
---

# universe_lab.html (Universe Lab)

**Domain:** 해외 · 매크로 · **Type:** Page · **Runs on:** github · **Status:** active · **Project:** antigravity

Universe의 실험(lab) 변형 페이지. 사이드바/스타일을 Universe와 통일해 관리.

- ★**손으로 유지하는 정적 HTML(2026-08-17 정정)**: 종전 이 문서는 `create_dashboard.py`의 PAGES 목록으로 생성된다고 적었으나, 실측하면 생성기 소스에 `universe_lab` 문자열이 없다([[src-create-dashboard]]가 쓰는 것은 market/index/wrap/universe/seibro/featured_legacy/etf). 커밋 이력도 `universe_lab.html`을 직접 고쳐 왔다 — **양식·nav 통일은 재생성이 아니라 사람이 옮겨 심는 방식**이라, [[page-market]]·[[page-universe]] 규격이 바뀌면 이 페이지만 뒤처진다.
- 소스는 Universe와 공유(universe.json 계열).
- **nav 위치(2026-07-31)**: Universe와 함께 상단 네비 Market → **Watchlist 드롭다운 하위**로 이동([[src-nav-style]] `NAV_ITEMS`).
- **Copy 버튼(2026-08-09)**: 히트맵·섹터 로테이션·순위 변화 3패널 모두 Download 왼쪽에 Copy(클립보드 PNG) 병설 — [[page-universe]]·[[page-market]]과 동일 규격(`_copyBlobP`, ClipboardItem에 Promise Blob 전달).
- **버튼 외형 통일(2026-08-17)**: Copy 버튼의 위치·색, 이어서 Download 버튼 스타일을 [[page-market]] DATA 탭 규격에 맞췄다. 위 정정대로 이 페이지는 생성물이 아니라서 `universe_lab.html`을 직접 수정하는 커밋 2건으로 처리됐다 — 생성기 쪽 규격 변경이 자동 전파되지 않는다는 사실이 그대로 드러난 사례.

## Reads
- [[store-universe-json]] — universe.json / universe_history.json

## Writes
- (none)

## Depends on
- [[src-universe]] — 유니버스 수집 (fetch_universe.py)

## Code
- `universe_lab.html`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/universe_lab.html)
