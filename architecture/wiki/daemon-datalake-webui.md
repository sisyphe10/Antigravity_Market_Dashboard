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
writes: []
depends_on:
  - "infra-vm-macmini"
  - "infra-datalake"
alerts: "KeepAlive=true (launchd 자동 재기동, ThrottleInterval=15)"
---

# 데이터레이크 문답 웹 UI 데몬 (AoE Wiki, 127.0.0.1:8787)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** vm_macmini · **Schedule (KST):** 상시 · **Status:** active · **Project:** antigravity

2026-07-12 신설. 데이터레이크의 DuckDB+Claude API 자연어 문답 UI를 **상시 데몬**으로 띄우는 launchd 서비스(`com.antigravity.datalake-webui`, RunAtLoad + KeepAlive). 기존 수동 기동(`run_webui.sh`)을 데몬화해, ts.net 대시보드의 'Wiki' 탭 백엔드로 상주시킨다.

- 바인딩: FastAPI 서버(`server.py`)가 `127.0.0.1:8787` 루프백 고정 — 직접 공개 노출 없음. Caddy가 `/wiki/*`를 이 포트로 리버스 프록시([[web-caddy]]) → AoE 'Wiki' 탭.
- 질의 대상 = 데이터레이크 md 코퍼스 + duckdb 샌드박스(allowed→잠금). 소스·설계 상세는 [[infra-datalake]] / `datalake/DESIGN.md`.
- ★**nav는 손으로 맞춰야 하는 사본**(`datalake/webui/static/index.html`): 이 페이지는 스냅숏이 아니라 데몬에서 직접 서빙되므로 [[web-publish-snapshot]]의 `compose_personal_view.py` nav 주입이 **닿지 않는다**. 2026-07-16 nav 개편 때 [[daemon-watchlist-quoteboard]]와 함께 이 파일의 topnav 마크업을 따로 고쳐 통일했다(`Wiki` 탭에 `margin-left:auto`를 줘 Wiki·Architecture를 우측 그룹으로 미는 것도 여기 사본에 직접 박혀 있다). 2026-07-18 브랜드 라벨을 `AoE` → `AGE OF EMERGENCE`로 확장할 때도 이 사본을 손으로 맞췄다([[web-publish-snapshot]]).
- launchd 관리: `ThrottleInterval=15`로 크래시 루프 억제, 로그는 `logs/launchd/datalake-webui.{out,err}`. 계산 잡 아님(catch-up 대상 아님).

## Reads
- [[infra-datalake]] — 맥미니 데이터레이크 (~/datalake + 문답 위키)

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
