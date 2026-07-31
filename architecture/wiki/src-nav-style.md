---
id: "src-nav-style"
name: "AoE 스타일 정본 (nav_style.py)"
domain: "ops-infra"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "import 시 (상시)"
status: "active"
code:
  - "execution/nav_style.py"
reads: []
writes: []
depends_on: []
alerts: ""
---

# AoE 스타일 정본 (nav_style.py)

**Domain:** 운영 · 인프라 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** import 시 (상시) · **Status:** active · **Project:** antigravity

AoE 전 페이지 공통 스타일의 유일한 출처 (2026-07-26 네비 드리프트 근본해결).

- 상단 네비 정본: NAV_CSS(+scoped)·nav_html(active)·materialize(마커 치환).
- **하위 스트립(sidebar) 정본화(2026-07-31)**: 드롭다운 하위 탭을 가로로 펼치는 서브 스트립도 `NAV_ITEMS` 단일 출처로 — `sidebar_html(active)`·`SIDEBAR_CSS`·`SIDEBAR_MARK_BEGIN/END` 마커. 게시 단계에서 `compose_personal_view.py`가 소비 페이지의 `aside.sidebar`까지 이 정본으로 치환(구본 하드코딩 스트립 제거, Market 스트립에서 Universe 계열 제외)해 외형(스트립 42px·링크 41px·중앙정렬·sticky top=nav 54px·앰버 밑줄·800px 이하 숨김)을 게시본과 통일. 마커 소비 앱=[[daemon-watchlist-quoteboard]]·[[daemon-datalake-webui]](자식 없으면 무동작). create_dashboard는 자체 레이아웃 CSS 별도 보유.
- **Universe·Universe Lab → Watchlist 하위 이동(2026-07-31)**: `NAV_ITEMS`에서 두 페이지를 Market 드롭다운에서 Watchlist 드롭다운으로 옮겼다. `compose_personal_view.py`는 두 페이지의 nav active 키를 watchlist로 재매핑([[page-universe]]·[[page-universe-lab]]).
- 다크 PALETTE·라이트 WRAP_PALETTE: compose 주입 CSS 와 앱 3종(var(--aoe-*))·WRAP(var(--wrap-*)) 이 파생.
- H2C_FREEZE_JS: html2canvas 캡처 색고정 (틴트 셀 #333 굳음 버그 차단).
- **벤더 자산 셀프호스팅(2026-07-27)**: ts.net AoE 페이지의 Pretendard·Chart.js(v4.5.1 고정)·html2canvas(1.4.1)를 CDN 대신 로컬 `assets/vendor/`에서 서빙 — 상수 `VENDOR_PRETENDARD_CSS`/`VENDOR_CHART_JS`/`VENDOR_HTML2CANVAS_JS`(절대경로 `/assets/vendor/…`). `publish_snapshot.sh`가 `assets/**`를 스냅숏에 포함, webui 등 앱도 로컬 경로 사용. ★**WRAP만 CDN 유지** — gh-pages 프로젝트 사이트(`/repo/` 하위)에선 절대경로가 깨지므로 wrap 코드는 이 상수를 쓰지 않는다.
- 소비자: create_dashboard·create_architecture(재생성 시) / webui·quoteboard 서버(기동 시 치환) / compose(publish 시 교체).
- ★수정 규칙: 네비·색 변경은 반드시 이 파일에서만. 다크 주입 CSS 에 nav !important 재단언 금지.

## Reads
- (none)

## Writes
- (none)

## Depends on
- (none)

## Code
- `execution/nav_style.py`
