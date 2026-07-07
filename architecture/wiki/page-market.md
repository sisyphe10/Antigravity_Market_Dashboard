---
id: "page-market"
name: "market.html (마켓 대시보드)"
domain: "market-global"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: "생성=여러 잡"
status: "active"
code:
  - "execution/create_dashboard.py"
reads:
  - "store-dataset-csv"
  - "monthly_returns.json"
writes: []
depends_on:
  - "src-create-dashboard"
alerts: ""
---

# market.html (마켓 대시보드)

**Domain:** 해외 · 매크로 · **Type:** Page · **Runs on:** github · **Schedule (KST):** 생성=여러 잡 · **Status:** active · **Project:** antigravity

시장 데이터 허브. Monthly Returns 표 + Indices/MARKET 동적 차트 + DATA 섹션(ECOS/FRED/KRX/원자재/capex 등 시계열 사이드바).

- DATA 탭 사이드바 3칼럼(Update/Group/Data) 정렬+엑셀필터, 주기 자동판정, 행배경 틴트.
- 소스: `dataset.csv`(대부분 시계열), `monthly_returns.json`.
- `create_dashboard.py` 생성. dataset.csv를 쓰는 거의 모든 잡이 재생성.

## Reads
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)
- `monthly_returns.json`

## Writes
- (none)

## Depends on
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)

## Code
- `execution/create_dashboard.py`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/market.html)
