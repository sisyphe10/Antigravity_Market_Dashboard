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
- ★2026-08-04: `newhigh_20d.json`은 이제 수집 결과 + `newhigh_themes.json`(테마 정본 sidecar)을 합친 **materialized view** — 16:20·18:30 재수집이 테마를 날리던 문제 해결([[src-featured-kis]]). 비거래일 행은 거래일 가드로 더 이상 기록되지 않음(과거 오염분은 `repair_featured_history.py`로 정리).

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-featured-kis]] — Featured KIS/신고가 (fetch_featured_data_kis.py + enrich)
- [[bot-sisyphe]] — Sisyphe-Bot (펀드/일상 텔레그램 봇)

## Code
- (none)
