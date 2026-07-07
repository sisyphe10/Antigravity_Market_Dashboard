---
id: "src-featured-kis"
name: "Featured KIS/신고가 (fetch_featured_data_kis.py + enrich)"
domain: "portfolio-wrap"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "15:50 (featured-kis 타이머)"
status: "active"
code:
  - "execution/fetch_featured_data_kis.py"
  - "execution/enrich_newhigh_themes.py"
reads: []
writes:
  - "store-featured-data"
  - "featured_data_kis.json"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# Featured KIS/신고가 (fetch_featured_data_kis.py + enrich)

**Domain:** 포트폴리오 · WRAP · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 15:50 (featured-kis 타이머) · **Status:** active · **Project:** antigravity

KIS 시세로 20일 신고가(`newhigh_20d.json`)를 만들고 테마를 enrich하는 수집기(15:50 타이머).

- `enrich_newhigh_themes.py`가 Naver 뉴스+Haiku로 테마 부착(실패해도 수집 유지).
- 16:00 RA_Sisyphe_bot 신고가 알림이 이 산출을 소비. Featured 배치 KIS 전환 완료.

## Reads
- (none)

## Writes
- [[store-featured-data]] — featured_data.json / newhigh_20d.json
- `featured_data_kis.json`

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_featured_data_kis.py`
- `execution/enrich_newhigh_themes.py`
