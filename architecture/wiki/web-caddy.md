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
  - "daemon-plan-api"
writes: []
depends_on:
  - "infra-vm-macmini"
  - "web-publish-snapshot"
  - "daemon-sisyphe-pull"
  - "daemon-datalake-webui"
  - "daemon-watchlist-quoteboard"
  - "daemon-plan-api"
alerts: "KeepAlive=true (launchd 자동 재기동)"
---

# 웹 서빙 (Caddy · com.antigravity.web)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** vm_macmini · **Schedule (KST):** 상시 · **Status:** active · **Project:** antigravity

2026-07-11 신설된 맥미니 자체 서빙 계층. Caddy(`com.antigravity.web`, homebrew, KeepAlive)가 게시 스냅숏을 tailscale(ts.net)로 내보내는 개인 대시보드의 웹서버.

- 입구는 `tailscale serve` 프록시뿐 — Caddy는 `http://:8377` + `bind 127.0.0.1` 루프백 고정(공개 노출 없음). 127.0.0.1:8377 직접 바인딩은 프록시 Host 불일치로 빈 200이 나던 실측 함정 회피.
- **루트(`/`)는 2026-07-18부터 다시 `/watchlist/`로 302 리다이렉트** — 사용자 확정으로 AoE 기본 화면이 Watchlist로 되돌아왔다([[daemon-watchlist-quoteboard]]). **구 랜딩(`/index.html`)도 같은 곳으로 302** → 랜딩 페이지는 개인 ts.net에서 폐지(파일은 잡들이 계속 생성하나 접근 불가, [[page-index]]). 기본 화면은 세 세대에 걸쳐 흔들렸다: 2026-07-15 `/watchlist/` → 07-16 `/sisyphe/memento.html`(Memento) → 07-18 다시 `/watchlist/`. Memento는 이제 nav 'Memento' 탭(`/sisyphe/memento.html`)으로만 진입한다.
- 게시 스냅숏(`~/srv/dashboard/current`, `publish_snapshot.sh` 산출)은 맨 아래 fallback handle이 정적 서빙 — **스냅숏 디렉토리 직접 수정 금지**. Sisyphe 개인 페이지(`/sisyphe/*`)도 이 스냅숏의 `current/sisyphe/`(2026-07-13 평문 전환, [[web-publish-snapshot]]의 `compose_personal_view.py`가 합성 — staticrypt 암호화 직서빙 폐기)에서 서빙된다. 기본 화면인 `memento.html`이 이 경로에 있으므로 **compose 실패로 세대가 폐기되면 루트 진입 자체가 깨진다**.
- `/journal/*`(2026-07-13): 개인 투자일지 차트("Escape Velocity") — 테일넷 + basic_auth 이중 게이트, `~/Journal/web` 정적 서빙(`no-store`). **데이터·자격증명·페이지 전부 `~/Journal` 로컬 전용으로 git/게시 파이프라인과 격리**(전역 규칙 Journal 섹션). `~/Journal/caddy_auth.snippet` import — 없으면 caddy 기동 실패하니 Journal 폴더 이동 시 이 라우트 먼저 수정.
- `/wiki/*`는 `127.0.0.1:8787`([[daemon-datalake-webui]])로 리버스 프록시 — 데이터레이크 문답 UI를 AoE 'Wiki' 탭으로 통합(2026-07-12, `redir /wiki /wiki/ 301`).
- `/watchlist/*`(2026-07-15): 관심종목 시세판 데몬 `127.0.0.1:8778`([[daemon-watchlist-quoteboard]]) 리버스 프록시(`no-store`, `redir /watchlist /watchlist/ 301`).
- `/charts/*`(2026-07-20): 삼성·하이닉스 현선물/공매도/레버리지ETF + 건설 수주잔고 차트 뷰어. **repo 밖 정적 서빙** — `root=~/work/charts/260715_현선물공매도`(대시보드 repo와 분리), 기본 진입 `/charts`·`/charts/`는 `chart_viewer2.html`로 302. `no-cache`. 산출물은 spot 분석 폴더라 게시 스냅숏/git 파이프라인 밖.
- `/plan-api/*`(2026-07-15): Sisyphe Ledger 'Plan' 자금계획 JSON(`~/Journal/plan_web.json`, 계좌번호 포함) API — `plan_api.py` 백엔드(`127.0.0.1:8790`, [[daemon-plan-api]])로 프록시. **게이트는 테일넷 단독**(basic_auth는 당일 `plan_auth.snippet` import 도입 → 별도 realm 전환 → 제거로 정리). ★소스의 라우트 주석은 'basic_auth 이중'이라 적혀 있으나 실제 설정엔 auth import가 없다 — 주석이 stale.
- HTML/JSON/CSV·인덱스는 `Cache-Control: no-cache`. 접근 로그는 `~/srv/dashboard/logs/access.log`(20MiB 롤).

## Reads
- [[web-publish-snapshot]] — 개인 스냅숏 게시 (publish_snapshot.sh)
- [[daemon-sisyphe-pull]] — Sisyphe repo 클론 서빙 (시간당 pull)
- [[daemon-datalake-webui]] — 데이터레이크 문답 웹 UI 데몬 (AoE Wiki, 127.0.0.1:8787)
- [[daemon-watchlist-quoteboard]] — 관심종목 시세판 데몬 (Watchlist, 127.0.0.1:8778)
- [[daemon-plan-api]] — Plan API 데몬 (Sisyphe Ledger 자금계획, 127.0.0.1:8790)

## Writes
- (none)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)
- [[web-publish-snapshot]] — 개인 스냅숏 게시 (publish_snapshot.sh)
- [[daemon-sisyphe-pull]] — Sisyphe repo 클론 서빙 (시간당 pull)
- [[daemon-datalake-webui]] — 데이터레이크 문답 웹 UI 데몬 (AoE Wiki, 127.0.0.1:8787)
- [[daemon-watchlist-quoteboard]] — 관심종목 시세판 데몬 (Watchlist, 127.0.0.1:8778)
- [[daemon-plan-api]] — Plan API 데몬 (Sisyphe Ledger 자금계획, 127.0.0.1:8790)

## Code
- `launchd/web/Caddyfile`
- `launchd/web/com.antigravity.web.plist`

## Alerts
⚠ KeepAlive=true (launchd 자동 재기동)
