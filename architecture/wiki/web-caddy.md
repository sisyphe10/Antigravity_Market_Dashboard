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
  - "daemon-watchlist-quoteboard"
writes: []
depends_on:
  - "infra-vm-macmini"
  - "web-publish-snapshot"
  - "daemon-sisyphe-pull"
  - "daemon-datalake-webui"
  - "daemon-watchlist-quoteboard"
alerts: "KeepAlive=true (launchd 자동 재기동)"
---

# 웹 서빙 (Caddy · com.antigravity.web)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** vm_macmini · **Schedule (KST):** 상시 · **Status:** active · **Project:** antigravity

2026-07-11 신설된 맥미니 자체 서빙 계층. Caddy(`com.antigravity.web`, homebrew, KeepAlive)가 게시 스냅숏을 tailscale(ts.net)로 내보내는 개인 대시보드의 웹서버.

- 입구는 `tailscale serve` 프록시뿐 — Caddy는 `http://:8377` + `bind 127.0.0.1` 루프백 고정(공개 노출 없음). 127.0.0.1:8377 직접 바인딩은 프록시 Host 불일치로 빈 200이 나던 실측 함정 회피.
- **루트(`/`)는 2026-07-15부터 `/watchlist/`로 302 리다이렉트** — 첫 화면이 관심종목 시세판([[daemon-watchlist-quoteboard]])으로 바뀌었고, 기존 랜딩([[page-index]])은 `/index.html` 직접 접근으로만 열린다. 게시 스냅숏(`~/srv/dashboard/current`, `publish_snapshot.sh` 산출)은 그 아래 fallback handle이 정적 서빙 — **스냅숏 디렉토리 직접 수정 금지**. Sisyphe 개인 페이지(`/sisyphe/*`)도 이제 이 스냅숏의 `current/sisyphe/`(2026-07-13 평문 전환, [[web-publish-snapshot]]의 `compose_personal_view.py`가 합성 — staticrypt 암호화 직서빙 폐기)에서 fallback handle로 서빙된다.
- `/journal/*`(2026-07-13): 개인 투자일지 차트("Escape Velocity") — 테일넷 + basic_auth 이중 게이트, `~/Journal/web` 정적 서빙(`no-store`). **데이터·자격증명·페이지 전부 `~/Journal` 로컬 전용으로 git/게시 파이프라인과 격리**(전역 규칙 Journal 섹션). `~/Journal/caddy_auth.snippet` import — 없으면 caddy 기동 실패하니 Journal 폴더 이동 시 이 라우트 먼저 수정.
- `/wiki/*`는 `127.0.0.1:8787`([[daemon-datalake-webui]])로 리버스 프록시 — 데이터레이크 문답 UI를 AoE 'Wiki' 탭으로 통합(2026-07-12, `redir /wiki /wiki/ 301`).
- `/watchlist/*`(2026-07-15): 관심종목 시세판 데몬 `127.0.0.1:8778`([[daemon-watchlist-quoteboard]]) 리버스 프록시(`no-store`, `redir /watchlist /watchlist/ 301`). 위 루트 302와 짝 — ts.net 첫 화면.
- `/plan-api/*`(2026-07-15): Sisyphe Ledger 'Plan' 자금계획 JSON(`~/Journal/plan_web.json`, 계좌번호 포함) API — `~/Journal/scripts/plan_api.py` 백엔드(`127.0.0.1:8790`, launchd `com.antigravity.plan-api`, 레포 밖)로 프록시. **게이트는 테일넷 단독**(basic_auth는 당일 `plan_auth.snippet` import 도입 → 별도 realm 전환 → 제거로 정리). ★소스의 라우트 주석은 'basic_auth 이중'이라 적혀 있으나 실제 설정엔 auth import가 없다 — 주석이 stale.
- HTML/JSON/CSV·인덱스는 `Cache-Control: no-cache`. 접근 로그는 `~/srv/dashboard/logs/access.log`(20MiB 롤).

## Reads
- [[web-publish-snapshot]] — 개인 스냅숏 게시 (publish_snapshot.sh)
- [[daemon-sisyphe-pull]] — Sisyphe repo 클론 서빙 (시간당 pull)
- [[daemon-datalake-webui]] — 데이터레이크 문답 웹 UI 데몬 (AoE Wiki, 127.0.0.1:8787)
- [[daemon-watchlist-quoteboard]] — 관심종목 시세판 데몬 (Watchlist, 127.0.0.1:8778)

## Writes
- (none)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)
- [[web-publish-snapshot]] — 개인 스냅숏 게시 (publish_snapshot.sh)
- [[daemon-sisyphe-pull]] — Sisyphe repo 클론 서빙 (시간당 pull)
- [[daemon-datalake-webui]] — 데이터레이크 문답 웹 UI 데몬 (AoE Wiki, 127.0.0.1:8787)
- [[daemon-watchlist-quoteboard]] — 관심종목 시세판 데몬 (Watchlist, 127.0.0.1:8778)

## Code
- `launchd/web/Caddyfile`
- `launchd/web/com.antigravity.web.plist`

## Alerts
⚠ KeepAlive=true (launchd 자동 재기동)
