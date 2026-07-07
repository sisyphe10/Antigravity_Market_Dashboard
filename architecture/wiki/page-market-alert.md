---
id: "page-market-alert"
name: "market_alert.html (투자유의종목)"
domain: "market-kr"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: "생성=16:05 / 23:00 (sisyphe-bot)"
status: "active"
code:
  - "execution/create_market_alert.py"
reads: []
writes: []
depends_on:
  - "src-create-market-alert"
alerts: ""
---

# market_alert.html (투자유의종목)

**Domain:** 국내 시장 · **Type:** Page · **Runs on:** github · **Schedule (KST):** 생성=16:05 / 23:00 (sisyphe-bot) · **Status:** active · **Project:** antigravity

투자유의/투자경고/투자위험 지정 종목 추적 페이지.

- `create_market_alert.py`(별도 생성기)가 만들며 Sisyphe-Bot 16:05/23:00 잡이 재생성. KIS marcap 사용.
- 텔레그램 4블록 요약(신규/진입임박/탈출임박/전체현황)은 RA_Sisyphe_bot 05:15 잡.
- 함정: 지정예고는 투자주의 fetch에 들어옴(경고 아님).

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-create-market-alert]] — 투자유의 생성기 (create_market_alert.py)

## Code
- `execution/create_market_alert.py`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/market_alert.html)
