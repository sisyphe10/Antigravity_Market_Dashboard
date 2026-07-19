---
id: "page-taiwan"
name: "taiwan.html (대만 월매출)"
domain: "market-global"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: "생성=23:20 (gha-daily-taiwan-revenue) — 스텁"
status: "retired"
code:
  - "execution/create_dashboard.py"
reads:
  - "store-taiwan-revenue-csv"
writes: []
depends_on:
  - "page-market"
  - "src-taiwan-revenue"
alerts: ""
---

# taiwan.html (대만 월매출)

**Domain:** 해외 · 매크로 · **Type:** Page · **Runs on:** github · **Schedule (KST):** 생성=23:20 (gha-daily-taiwan-revenue) — 스텁 · **Status:** retired · **Project:** antigravity

독립 대만 월매출 페이지는 은퇴 — `taiwan.html`은 이제 리다이렉트 스텁이다(2026-07-19, 3178add4). 대만 상장 반도체/기술 큐레이션 53종목 월매출은 `market.html` Data 페이지의 'Taiwan' 버튼 패널로 임베드된다.

- 콘텐츠 정본은 공유 빌더 `execution/taiwan_table.py`(2026-07-07 독립 `create_taiwan_page.py` 은퇴) → `create_dashboard.py`가 market.html에 삽입. 소스는 여전히 FinMind 월매출(`taiwan_revenue.csv`).
- `taiwan.html`은 `market.html#taiwan` 해시 딥링크로 리다이렉트하는 얇은 스텁만 남았다. 외부 즐겨찾기·구 링크 보존 목적.
- 데이터 갱신은 여전히 매일 23:20 KST GHA(gha-daily-taiwan-revenue)가 수집→market.html 재생성→push. 100일 롤링 재조회 자가치유.

## Reads
- [[store-taiwan-revenue-csv]] — taiwan_revenue.csv (대만 월매출)

## Writes
- (none)

## Depends on
- [[page-market]] — market.html (마켓 대시보드)
- [[src-taiwan-revenue]] — 대만 월매출 (fetch_taiwan_revenue.py)

## Code
- `execution/create_dashboard.py`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/taiwan.html)
