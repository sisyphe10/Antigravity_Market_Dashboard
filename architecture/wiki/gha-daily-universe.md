---
id: "gha-daily-universe"
name: "Daily Universe yfinance (18:30 + 07:00)"
domain: "market-global"
project: "antigravity"
type: "gha_workflow"
runs_on: "gha"
schedule_kst: "18:30 / 07:00 매일"
status: "active"
code:
  - ".github/workflows/daily_universe.yml"
reads:
  - "universe_tickers.csv"
writes:
  - "store-universe-json"
depends_on:
  - "src-universe"
alerts: "실패 자체 알림 없음 → gha-daily-health-check"
---

# Daily Universe yfinance (18:30 + 07:00)

**Domain:** 해외 · 매크로 · **Type:** GHA · **Runs on:** gha · **Schedule (KST):** 18:30 / 07:00 매일 · **Status:** active · **Project:** antigravity

관심 유니버스 종목 시세/지표를 하루 2회 yfinance로 수집해 `universe.json`+`universe_history.json` 갱신. 18:30 KST(아시아 장종료 후) + 07:00 KST(미국·유럽 장종료 후).

- 종목 추가 = `universe_tickers.csv` 행 + 타겟 주입(전체 2회 실행 금지). 멀티인스턴스는 별도 worktree.
- Universe DD 열(52주 낙폭), RSI(1M)는 `fetch_index_returns` 산출을 소비.
- `wrap-nav-pipeline` 그룹으로 push 직렬화.

## Reads
- `universe_tickers.csv`

## Writes
- [[store-universe-json]] — universe.json / universe_history.json

## Depends on
- [[src-universe]] — 유니버스 수집 (fetch_universe.py)

## Code
- `.github/workflows/daily_universe.yml`

## Alerts
⚠ 실패 자체 알림 없음 → gha-daily-health-check
