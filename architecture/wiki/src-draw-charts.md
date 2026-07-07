---
id: "src-draw-charts"
name: "차트 렌더러 (draw_charts + draw_wrap_charts)"
domain: "ops-infra"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "23:00 (daily_crawl)"
status: "active"
code:
  - "execution/draw_charts.py"
  - "execution/draw_wrap_charts.py"
reads:
  - "store-dataset-csv"
  - "store-wrap-nav-xlsx"
writes:
  - "charts/"
depends_on:
  - "src-market-crawler"
alerts: ""
---

# 차트 렌더러 (draw_charts + draw_wrap_charts)

**Domain:** 운영 · 인프라 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 23:00 (daily_crawl) · **Status:** active · **Project:** antigravity

dataset.csv/NAV로 market·wrap 차트 PNG를 그리는 렌더 단계.

- daily_crawl에서 `rm -f charts/*.png` 후 재생성.
- 한글 폰트(Nanum/Pretendard) 필요 — GHA 스텝에서 폰트 설치, 맥미니는 부트스트랩 전제.

## Reads
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)

## Writes
- `charts/`

## Depends on
- [[src-market-crawler]] — 마스터 시장 크롤러 (market_crawler.py)

## Code
- `execution/draw_charts.py`
- `execution/draw_wrap_charts.py`
