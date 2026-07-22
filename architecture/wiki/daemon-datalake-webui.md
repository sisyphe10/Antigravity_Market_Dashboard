---
id: "daemon-datalake-webui"
name: "데이터레이크 문답 웹 UI 데몬 (AoE Wiki, 127.0.0.1:8787)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "vm_macmini"
schedule_kst: "상시"
status: "active"
code:
  - "datalake/launchd/com.antigravity.datalake-webui.plist"
  - "datalake/webui/run_webui.sh"
  - "datalake/webui/server.py"
reads:
  - "infra-datalake"
  - "store-transcripts-md"
  - "store-analyses-md"
writes: []
depends_on:
  - "infra-vm-macmini"
  - "infra-datalake"
alerts: "KeepAlive=true (launchd 자동 재기동, ThrottleInterval=15)"
---

# 데이터레이크 문답 웹 UI 데몬 (AoE Wiki, 127.0.0.1:8787)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** vm_macmini · **Schedule (KST):** 상시 · **Status:** active · **Project:** antigravity

2026-07-12 신설. 데이터레이크의 DuckDB+Claude API 자연어 문답 UI를 **상시 데몬**으로 띄우는 launchd 서비스(`com.antigravity.datalake-webui`, RunAtLoad + KeepAlive). 기존 수동 기동(`run_webui.sh`)을 데몬화해, ts.net 대시보드의 'Wiki' 탭 백엔드로 상주시킨다.

- 바인딩: FastAPI 서버(`server.py`)가 `127.0.0.1:8787` 루프백 고정 — 직접 공개 노출 없음. Caddy가 `/wiki/*`를 이 포트로 리버스 프록시([[web-caddy]]) → AoE 'Wiki'·'Earnings' 탭.
- 질의 대상 = 데이터레이크 md 코퍼스 + duckdb 샌드박스(allowed→잠금). 소스·설계 상세는 [[infra-datalake]] / `datalake/DESIGN.md`.
- **코퍼스 확장(2026-07-21)**: SEARCH_ROOTS에 `transcripts`(어닝콜 한국어 번역 전문, [[store-transcripts-md]])를 추가하고 시스템 프롬프트에 어닝콜 전문 소스를 명시. 긴 전문 대응으로 `read_file`에 offset 페이징(1회 최대 20000자, `(truncated ... offset=)` 안내)을 도입.
- **Earnings Library + analyses 코퍼스(2026-07-22)**: SEARCH_ROOTS에 `analyses`(실적 분석 1-page, [[store-analyses-md]])를 추가하고, 별도 열람 UI 엔드포인트 `/library`(+`/library/list`·`/library/doc`)를 신설. transcripts+analyses md를 필터·프론트매터·md 렌더로 보여주는 'Earnings Library' 페이지(터미널 블랙+앰버)로, ts.net `/wiki/library`에 리버스 프록시되고 nav 'Earnings' 탭이 여기를 가리킨다. 실적봇의 Notion 분석 퍼블리시가 md 발행으로 대체되며([[src-earnings-pipeline]]) 이 UI가 Notion 열람을 대신한다.
- ★**nav는 손으로 맞춰야 하는 사본**(`datalake/webui/static/index.html`): 이 페이지는 스냅숏이 아니라 데몬에서 직접 서빙되므로 [[web-publish-snapshot]]의 `compose_personal_view.py` nav 주입이 **닿지 않는다**. 2026-07-16 nav 개편 때 [[daemon-watchlist-quoteboard]]와 함께 이 파일의 topnav 마크업을 따로 고쳐 통일했다(`Wiki` 탭에 `margin-left:auto`를 줘 Wiki·Architecture를 우측 그룹으로 미는 것도 여기 사본에 직접 박혀 있다). 2026-07-18 브랜드 라벨을 `AoE` → `AGE OF EMERGENCE`로 확장할 때도 이 사본을 손으로 맞췄다([[web-publish-snapshot]]). 2026-07-22 nav 재편(좌 Watchlist·Market·Journal·Weekly·Earnings·Wiki / 우 Memento·Ledger·Architecture)과 'Earnings'(`/wiki/library`) 탭 추가도 이 사본에 직접 반영했다.
- launchd 관리: `ThrottleInterval=15`로 크래시 루프 억제, 로그는 `logs/launchd/datalake-webui.{out,err}`. 계산 잡 아님(catch-up 대상 아님).

## Reads
- [[infra-datalake]] — 맥미니 데이터레이크 (~/datalake + 문답 위키)
- [[store-transcripts-md]] — 어닝콜 번역 전문 md (~/datalake/transcripts/)
- [[store-analyses-md]] — 실적 분석 1-page md (~/datalake/analyses/)

## Writes
- (none)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)
- [[infra-datalake]] — 맥미니 데이터레이크 (~/datalake + 문답 위키)

## Code
- `datalake/launchd/com.antigravity.datalake-webui.plist`
- `datalake/webui/run_webui.sh`
- `datalake/webui/server.py`

## Alerts
⚠ KeepAlive=true (launchd 자동 재기동, ThrottleInterval=15)
