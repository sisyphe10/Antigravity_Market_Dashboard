---
id: "page-universe"
name: "universe.html (Universe)"
domain: "market-global"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: "생성=여러 잡"
status: "active"
code:
  - "execution/create_dashboard.py"
reads:
  - "store-universe-json"
writes: []
depends_on:
  - "src-create-dashboard"
  - "src-universe"
alerts: ""
---

# universe.html (Universe)

**Domain:** 해외 · 매크로 · **Type:** Page · **Runs on:** github · **Schedule (KST):** 생성=여러 잡 · **Status:** active · **Project:** antigravity

관심 유니버스 종목 스크리닝 페이지(시세·52주 낙폭 DD·RSI 1M·외국인 보유비중 등).

- 소스: `universe.json`/`universe_history.json`(하루 2회 yfinance) + 외국인 보유비중(INDEX_KR).
- `create_dashboard.py` 생성. 종목 추가는 `universe_tickers.csv`로.
- **관심종목 별표 컬럼(2026-07-31)**: 종목 리스트 1열에 별표(★) 토글 — 상태는 [[daemon-watchlist-quoteboard]]의 `/watchlist/prefs`(`universe_stars_v1 = {"tickers":[순수심볼,…]}`)에 서버 공유(+localStorage 폴백). 헤더 ★ = 관심종목만 보기 필터. Download PNG에선 별표 컬럼 숨김. 정렬 헤더 화살표는 `#tab0`로 한정(기간 탭 헤더 오염 방지).
- **nav 위치(2026-07-31)**: 상단 네비에서 Market → **Watchlist 드롭다운 하위**로 이동([[src-nav-style]] `NAV_ITEMS`).
- **표 캡처·가독성(2026-08-09)**: 종목 리스트·섹터·기간 3탭 모두 Download 왼쪽에 Copy 버튼(클립보드 PNG, 상위 30행만 — Download와 동일 규칙, [[src-create-dashboard]] 캡처 헬퍼 공용). 스파크라인 선색을 검정 → 에메랄드 `#10b981`(다크 배경에서 검정은 보이지 않음). 정렬 컬럼 하이라이트 `.col-hl` 배경을 `#14171b` → `#262b32`로 상향하고, 종목 리스트에만 있던 하이라이트를 **섹터 표에도 적용**(섹터명 + 현재 정렬 컬럼).

## Reads
- [[store-universe-json]] — universe.json / universe_history.json

## Writes
- (none)

## Depends on
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)
- [[src-universe]] — 유니버스 수집 (fetch_universe.py)

## Code
- `execution/create_dashboard.py`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/universe.html)
