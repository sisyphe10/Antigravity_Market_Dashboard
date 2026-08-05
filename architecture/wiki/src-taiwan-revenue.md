---
id: "src-taiwan-revenue"
name: "대만 월매출 (fetch_taiwan_revenue.py)"
domain: "market-global"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "23:20 (gha-daily-taiwan-revenue)"
status: "active"
code:
  - "execution/fetch_taiwan_revenue.py"
  - "execution/taiwan_table.py"
  - "execution/taiwan_revenue_alert.py"
reads: []
writes:
  - "store-taiwan-revenue-csv"
  - "page-market"
depends_on:
  - "ext-data-apis"
  - "infra-telegram"
alerts: ""
---

# 대만 월매출 (fetch_taiwan_revenue.py)

**Domain:** 해외 · 매크로 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 23:20 (gha-daily-taiwan-revenue) · **Status:** active · **Project:** antigravity

FinMind로 대만 상장 큐레이션 53종목 월매출을 수집해 `taiwan_revenue.csv` 생성. 공유 빌더 `taiwan_table.py`가 이를 `market.html` Data 페이지 'Taiwan' 패널로 렌더(독립 `create_taiwan_page.py`·taiwan.html은 은퇴 — [[page-taiwan]]).

- `--crosscheck`로 공식 TWSE/TPEx 스냅샷 대조(로그만). 100일 롤링 재조회 자가치유.
- 시크릿: FINMIND_TOKEN/USER/PASSWORD.
- **월매출 텔레그램 알림(2026-08-05, `taiwan_revenue_alert.py`)**: 맥미니 launchd `gha-taiwan-revenue` 잡이 수집·빌드 뒤 마지막 단계로 발송(발송 실패는 tolerate — 로그만). 한국 PEER 조인을 붙이고, 처음엔 QTD vs 분기 컨센서스를 넣었으나 최종적으로 **컨센서스는 빼고 부티크 ETF 알림과 같은 불릿 스타일(PEER만)**로 정리했다.

## Reads
- (none)

## Writes
- [[store-taiwan-revenue-csv]] — taiwan_revenue.csv (대만 월매출)
- [[page-market]] — market.html (마켓 대시보드)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `execution/fetch_taiwan_revenue.py`
- `execution/taiwan_table.py`
- `execution/taiwan_revenue_alert.py`
