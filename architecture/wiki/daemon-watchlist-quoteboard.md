---
id: "daemon-watchlist-quoteboard"
name: "관심종목 시세판 데몬 (Watchlist, 127.0.0.1:8778)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "vm_macmini"
schedule_kst: "상시 (스윕 장중 2s · 장외 60s)"
status: "active"
code:
  - "launchd/web/com.antigravity.watchlist.plist"
  - "quoteboard/server.py"
  - "quoteboard/index.html"
reads:
  - "store-portfolio-data"
  - "universe_tickers.csv"
  - "kis_universe_master.json"
writes:
  - "quoteboard/watchlists.json"
  - "quoteboard/shares_cache.json"
  - "quoteboard/market_stars.json"
  - "quoteboard/prefs.json"
depends_on:
  - "infra-vm-macmini"
  - "ext-data-apis"
  - "store-portfolio-data"
alerts: "KeepAlive=true (launchd 자동 재기동, ThrottleInterval=10)"
---

# 관심종목 시세판 데몬 (Watchlist, 127.0.0.1:8778)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** vm_macmini · **Schedule (KST):** 상시 (스윕 장중 2s · 장외 60s) · **Status:** active · **Project:** antigravity

2026-07-15 신설. POP HTS 상시실행을 대체하는 KIS 실시간 시세판을 **상시 데몬**으로 띄우는 launchd 서비스(`com.antigravity.watchlist`, RunAtLoad + KeepAlive, `run_bot.sh watchlist` wrapper 경유). 신설 당일엔 ts.net 첫 화면이었고(루트 302 대상), 2026-07-16 잠시 Memento로 넘어갔다가 **2026-07-18 다시 첫 화면으로 복귀** — 루트(`/`)·`/index.html`이 `/watchlist/`로 302된다([[web-caddy]]). nav 탭(좌측 선두)으로도 진입한다.

- 바인딩: stdlib `ThreadingHTTPServer`(`server.py`)가 `127.0.0.1:8778` 루프백 고정 — 직접 공개 노출 없음. Caddy가 `/watchlist/*`를 이 포트로 리버스 프록시(`no-store`). 라우트는 `/`(index.html) · `/data`(시세 JSON, 프런트 폴링) · `/wl`(관심그룹 GET/POST) · **`/stars`(market DATA 차트 별표, GET/POST)** · **`/prefs`(AoE 화면 뷰 설정 KV, GET/POST=키 단위 병합)** 5종, 쿼리스트링은 무시.
- **서버 저장 상태(2026-07-20 확장)**: 관심그룹(`watchlists.json`) 외에 market.html DATA 차트 별표(`market_stars.json`, [[page-market]]가 fetch)와 기기 공통 뷰 설정(`prefs.json`, 관심종목 뷰의 섹터 선택+정렬 등)을 서버에 둔다 — 브라우저 localStorage를 서버 저장으로 승격해 기기 간 공유. POST는 최대 100KB, `/prefs`는 다른 페이지 키를 보존하는 키 단위 병합.
- 종목: `universe_tickers.csv`의 KRX/KOSDAQ 전 종목(~587, 알파뉴메릭 코드 `0126Z0` 등 허용). 별도 큐레이션 ETF 그룹(`etf_tickers.csv`, `sector='ETF'` 첫 탭 고정, 2026-07-20). 시세는 KIS multprice(`FHKST11300006`) **30종목/콜 배치** 스윕 — 장중(평일 08:50~15:45) 2초(2026-07-20 1s→2s, 20콜/스윕에 KIS 쿼터 50% 헤드룸 확보), 장외 60초, 배치 실패 시 최대 10초 지수 백오프.
- 시총 = 현재가 × 상장주식수. 상장주식수는 KIS `inquire-price`로 매일 1회 갱신하고 `shares_cache.json`에 캐시 — 기동 시 오늘자 캐시 > 이전 캐시 > `kis_universe_master.json` 순으로 seed해 즉시 시작하고, 오늘자 캐시라도 누락 종목만 별도 보충(2026-07-15).
- 관심그룹 3종은 **서버 저장**(`watchlists.json`, 기기 공통 — 브라우저 로컬 아님). 그룹 1·2는 `portfolio_data.json`에서 10분 주기 **키워드 매칭 자동 동기화**(1=일반형/개방형/지속형, 2=목표전환형/성과모집형)라 회차 교체에 자동 추종한다. 수동 추가분은 직전 `auto` 목록과의 차집합으로 식별해 보존, 포트에서 빠진 auto 종목만 제거. 그룹 3은 수동 전용.
- 프런트(`quoteboard/index.html`): AoE topnav 동형 · 섹터 탭 멀티선택 · 정렬 · 전역 검색창에서 그룹 추가. 로그는 `logs/launchd/watchlist.{out,err}`. 계산 잡 아님(catch-up 대상 아님).
- ★**nav는 손으로 맞춰야 하는 사본**: 이 페이지는 스냅숏이 아니라 데몬에서 직접 서빙되므로 [[web-publish-snapshot]]의 `compose_personal_view.py` nav 주입이 **닿지 않는다**. 2026-07-16 nav 개편(Sisyphe 드롭다운 해체 → Watchlist·Memento·Weekly 승격, 좌/우 2그룹) 때도 [[daemon-datalake-webui]]의 Wiki 페이지와 함께 이 파일의 마크업을 따로 고쳐 통일했다 — nav를 바꾸면 여기도 같이 고쳐야 어긋나지 않는다.

## Reads
- [[store-portfolio-data]] — portfolio_data.json
- `universe_tickers.csv`
- `kis_universe_master.json`

## Writes
- `quoteboard/watchlists.json`
- `quoteboard/shares_cache.json`
- `quoteboard/market_stars.json`
- `quoteboard/prefs.json`

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)
- [[ext-data-apis]] — 외부 데이터 API/소스 집합
- [[store-portfolio-data]] — portfolio_data.json

## Code
- `launchd/web/com.antigravity.watchlist.plist`
- `quoteboard/server.py`
- `quoteboard/index.html`

## Alerts
⚠ KeepAlive=true (launchd 자동 재기동, ThrottleInterval=10)
