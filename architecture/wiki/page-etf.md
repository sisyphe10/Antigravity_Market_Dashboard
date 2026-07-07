---
id: "page-etf"
name: "etf.html (ETF 구성종목)"
domain: "market-kr"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: "생성=18:30 Featured 2차"
status: "active"
code:
  - "execution/create_dashboard.py"
  - "execution/etf_collector/active_etf_changes.py"
reads:
  - "store-etf-db"
writes: []
depends_on:
  - "src-create-dashboard"
  - "src-active-etf"
  - "timer-etf-collect"
alerts: ""
---

# etf.html (ETF 구성종목)

**Domain:** 국내 시장 · **Type:** Page · **Runs on:** github · **Schedule (KST):** 생성=18:30 Featured 2차 · **Status:** active · **Project:** antigravity

ETF 구성종목/비중 + 액티브 ETF 변동 탭 페이지(대용량 ~18MB, 조건부 생성 — `etf_data.db` 있을 때만).

- 소스: `etf_data.db`(16:30/18:00 수집 타이머). 액티브 ETF 탭은 `active_etf_changes.py` 단일 출처(19:00 알림과 숫자 일치).
- `create_dashboard.py`가 생성하되 VM 18:30 Featured 2차 잡이 실제 재생성.
- MMF/채권 제외(주식형만), 급변/편입/편출 필터.

## Reads
- [[store-etf-db]] — etf_data.db (ETF 구성종목 SQLite)

## Writes
- (none)

## Depends on
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)
- [[src-active-etf]] — 액티브 ETF 변동 (active_etf_changes.py)
- [[timer-etf-collect]] — ETF 구성종목 수집 타이머 (etf-collect 16:30)

## Code
- `execution/create_dashboard.py`
- `execution/etf_collector/active_etf_changes.py`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/etf.html)
