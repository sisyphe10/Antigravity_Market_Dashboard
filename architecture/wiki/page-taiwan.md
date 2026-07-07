---
id: "page-taiwan"
name: "taiwan.html (대만 월매출)"
domain: "market-global"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: "생성=23:20 (gha-daily-taiwan-revenue)"
status: "active"
code:
  - "execution/create_taiwan_page.py"
reads:
  - "store-taiwan-revenue-csv"
writes: []
depends_on:
  - "src-taiwan-revenue"
alerts: ""
---

# taiwan.html (대만 월매출)

**Domain:** 해외 · 매크로 · **Type:** Page · **Runs on:** github · **Schedule (KST):** 생성=23:20 (gha-daily-taiwan-revenue) · **Status:** active · **Project:** antigravity

대만 상장 반도체/기술 큐레이션 53종목의 월매출 페이지. 최근 추가된 신규 페이지.

- 소스: FinMind 월매출(`taiwan_revenue.csv`). `create_taiwan_page.py`가 CSV를 읽어 단일 HTML로 렌더.
- 매일 23:20 KST GHA가 수집→생성→push. 100일 롤링 재조회로 자가치유.

## Reads
- [[store-taiwan-revenue-csv]] — taiwan_revenue.csv (대만 월매출)

## Writes
- (none)

## Depends on
- [[src-taiwan-revenue]] — 대만 월매출 (fetch_taiwan_revenue.py)

## Code
- `execution/create_taiwan_page.py`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/taiwan.html)
