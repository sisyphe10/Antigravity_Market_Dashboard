---
id: "page-architecture"
name: "architecture.html (아키텍처)"
domain: "ops-infra"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: "수동 관리"
status: "active"
code:
  - "architecture.html"
  - "architecture/registry.json"
reads:
  - "architecture/registry.json"
writes: []
depends_on: []
alerts: ""
---

# architecture.html (아키텍처)

**Domain:** 운영 · 인프라 · **Type:** Page · **Runs on:** github · **Schedule (KST):** 수동 관리 · **Status:** active · **Project:** antigravity

생태계 아키텍처를 보여주는 페이지. **자동 생성이 아니라 수동 관리** — 이 레지스트리(`architecture/registry.json`)를 소비하는 렌더러가 향후 대체 예정.

- 현재는 `TOP_NAV_CSS`/`top_nav_html()` 결과를 정적으로 박아넣은 상태라, create_dashboard.py의 탭바 헬퍼를 고칠 때마다 수동 동기화가 필요(안 하면 탭바 어긋남).
- 본 레지스트리 기반 위키(`architecture/wiki/`)로 이관되면 이 수동 동기화 부담이 해소된다.

## Reads
- `architecture/registry.json`

## Writes
- (none)

## Depends on
- (none)

## Code
- `architecture.html`
- `architecture/registry.json`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/architecture.html)
