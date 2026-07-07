---
id: "src-landing-highlights"
name: "랜딩 하이라이트 생성 (create_landing_highlights.py)"
domain: "ops-infra"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "18:45 (landing-highlights 타이머)"
status: "active"
code:
  - "execution/create_landing_highlights.py"
reads:
  - "page-market-alert"
  - "page-seibro"
  - "store-featured-data"
writes:
  - "store-landing-highlights"
depends_on: []
alerts: "OnFailure(landing-highlights) → 텔레그램"
---

# 랜딩 하이라이트 생성 (create_landing_highlights.py)

**Domain:** 운영 · 인프라 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 18:45 (landing-highlights 타이머) · **Status:** active · **Project:** antigravity

index.html 회전 위젯(sparkline+한줄 코멘트, 50슬롯) 데이터 `landing_highlights.json` 생성.

- 여러 산출물(market_alert/seibro/featured 등)에서 하이라이트 슬롯을 뽑는다. Featured 2차(18:30) 마감 후 배치.

## Reads
- [[page-market-alert]] — market_alert.html (투자유의종목)
- [[page-seibro]] — seibro.html (SEIBro)
- [[store-featured-data]] — featured_data.json / newhigh_20d.json

## Writes
- [[store-landing-highlights]] — landing_highlights.json

## Depends on
- (none)

## Code
- `execution/create_landing_highlights.py`

## Alerts
⚠ OnFailure(landing-highlights) → 텔레그램
