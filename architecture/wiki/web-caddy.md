---
id: "web-caddy"
name: "웹 서빙 (Caddy · com.antigravity.web)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "vm_macmini"
schedule_kst: "상시"
status: "active"
code:
  - "launchd/web/Caddyfile"
  - "launchd/web/com.antigravity.web.plist"
reads:
  - "web-publish-snapshot"
  - "daemon-sisyphe-pull"
  - "daemon-datalake-webui"
writes: []
depends_on:
  - "infra-vm-macmini"
  - "web-publish-snapshot"
  - "daemon-sisyphe-pull"
  - "daemon-datalake-webui"
alerts: "KeepAlive=true (launchd 자동 재기동)"
---

# 웹 서빙 (Caddy · com.antigravity.web)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** vm_macmini · **Schedule (KST):** 상시 · **Status:** active · **Project:** antigravity

2026-07-11 신설된 맥미니 자체 서빙 계층. Caddy(`com.antigravity.web`, homebrew, KeepAlive)가 게시 스냅숏을 tailscale(ts.net)로 내보내는 개인 대시보드의 웹서버.

- 입구는 `tailscale serve` 프록시뿐 — Caddy는 `http://:8377` + `bind 127.0.0.1` 루프백 고정(공개 노출 없음). 127.0.0.1:8377 직접 바인딩은 프록시 Host 불일치로 빈 200이 나던 실측 함정 회피.
- 루트(`/`)는 `~/srv/dashboard/current`(게시 스냅숏, `publish_snapshot.sh` 산출) 정적 서빙 — **스냅숏 디렉토리 직접 수정 금지**.
- `/sisyphe/*`는 별도 root(`~/srv/sisyphe_repo`, 시간당 pull 클론)로 매핑 — `.git`/`scripts` 등은 404 차단.
- `/wiki/*`는 `127.0.0.1:8787`([[daemon-datalake-webui]])로 리버스 프록시 — 데이터레이크 문답 UI를 AoE 'Wiki' 탭으로 통합(2026-07-12, `redir /wiki /wiki/ 301`).
- HTML/JSON/CSV·인덱스는 `Cache-Control: no-cache`. 접근 로그는 `~/srv/dashboard/logs/access.log`(20MiB 롤).

## Reads
- [[web-publish-snapshot]] — 개인 스냅숏 게시 (publish_snapshot.sh)
- [[daemon-sisyphe-pull]] — Sisyphe repo 클론 서빙 (시간당 pull)
- [[daemon-datalake-webui]] — 데이터레이크 문답 웹 UI 데몬 (AoE Wiki, 127.0.0.1:8787)

## Writes
- (none)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)
- [[web-publish-snapshot]] — 개인 스냅숏 게시 (publish_snapshot.sh)
- [[daemon-sisyphe-pull]] — Sisyphe repo 클론 서빙 (시간당 pull)
- [[daemon-datalake-webui]] — 데이터레이크 문답 웹 UI 데몬 (AoE Wiki, 127.0.0.1:8787)

## Code
- `launchd/web/Caddyfile`
- `launchd/web/com.antigravity.web.plist`

## Alerts
⚠ KeepAlive=true (launchd 자동 재기동)
