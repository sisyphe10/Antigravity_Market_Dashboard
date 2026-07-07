---
id: "store-featured-data"
name: "featured_data.json / newhigh_20d.json"
domain: "portfolio-wrap"
project: "antigravity"
type: "dataset"
runs_on: "github"
schedule_kst: "Featured 잡 + 15:50"
status: "active"
code: []
reads: []
writes: []
depends_on:
  - "src-featured-kis"
  - "bot-sisyphe"
alerts: ""
---

# featured_data.json / newhigh_20d.json

**Domain:** 포트폴리오 · WRAP · **Type:** Dataset · **Runs on:** github · **Schedule (KST):** Featured 잡 + 15:50 · **Status:** active · **Project:** antigravity

Featured TOP 종목 데이터(~11MB)와 20일 신고가 데이터. Sisyphe-Bot Featured 잡 + featured-kis 타이머가 생성.

- featured.html(create_dashboard)과 RA_Sisyphe 신고가 알림이 소비.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-featured-kis]] — Featured KIS/신고가 (fetch_featured_data_kis.py + enrich)
- [[bot-sisyphe]] — Sisyphe-Bot (펀드/일상 텔레그램 봇)

## Code
- (none)
