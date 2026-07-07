---
id: "page-featured"
name: "featured.html (Featured TOP)"
domain: "portfolio-wrap"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: "생성=Featured 잡(16:20/18:30/08:30)"
status: "active"
code:
  - "execution/create_dashboard.py"
  - "execution/fetch_featured_news.py"
reads:
  - "store-featured-data"
  - "featured_news.json"
writes: []
depends_on:
  - "src-create-dashboard"
  - "bot-sisyphe"
alerts: ""
---

# featured.html (Featured TOP)

**Domain:** 포트폴리오 · WRAP · **Type:** Page · **Runs on:** github · **Schedule (KST):** 생성=Featured 잡(16:20/18:30/08:30) · **Status:** active · **Project:** antigravity

KRX 거래대금/시총/상승률 TOP 종목 페이지(대용량 ~11MB, 종목별 뉴스/테마 임베드).

- 소스: Sisyphe-Bot Featured 잡(16:20 1차/18:30 2차/08:30 익일 복구)이 KIS 배치로 `featured_data.json`을 만들고 create_dashboard로 생성.
- 20일 신고가는 별도 `newhigh_20d.json`(15:50 타이머).
- 18:30 2차가 etf.html도 함께 재생성.

## Reads
- [[store-featured-data]] — featured_data.json / newhigh_20d.json
- `featured_news.json`

## Writes
- (none)

## Depends on
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)
- [[bot-sisyphe]] — Sisyphe-Bot (펀드/일상 텔레그램 봇)

## Code
- `execution/create_dashboard.py`
- `execution/fetch_featured_news.py`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/featured.html)
