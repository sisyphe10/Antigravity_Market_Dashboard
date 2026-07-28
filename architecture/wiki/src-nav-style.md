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
