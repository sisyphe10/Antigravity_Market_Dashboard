---
id: "src-investor-trading"
name: "투자자별 수급 (fetch_investor_trading.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "장 마감 후 (sisyphe-bot)"
status: "active"
code:
  - "execution/fetch_investor_trading.py"
reads: []
writes:
  - "investor_trading.json"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# 투자자별 수급 (fetch_investor_trading.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 장 마감 후 (sisyphe-bot) · **Status:** active · **Project:** antigravity

코스피 투자자별 순매수(개인/외국인/기관 등)를 수집해 `investor_trading.json` 생성(market.html 수급). Sisyphe-Bot 잡이 subprocess로 호출.

- data.krx LOGOUT 차단 이력 → 네이버 investorDealTrendDay 경로 병용.

## Reads
- (none)

## Writes
- `investor_trading.json`

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_investor_trading.py`
