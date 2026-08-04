---
id: "store-boutique-etf-db"
name: "boutique_etf.db (부티크 액티브 ETF SQLite)"
domain: "market-kr"
project: "antigravity"
type: "store"
runs_on: "vm_macmini"
schedule_kst: "09:10 / 10:10 / 18:20 갱신 (평일)"
status: "active"
code: []
reads: []
writes: []
depends_on:
  - "src-boutique-etf"
alerts: ""
---

# boutique_etf.db (부티크 액티브 ETF SQLite)

**Domain:** 국내 시장 · **Type:** Store · **Runs on:** vm_macmini · **Schedule (KST):** 09:10 / 10:10 / 18:20 갱신 (평일) · **Status:** active · **Project:** antigravity

2026-08-04 신설. 부티크 액티브 ETF 팔로업 전용 **독립 SQLite DB**(repo 루트, gitignore·[[store-etf-db]] 불가침). [[timer-boutique-etf]]가 채운다.

- 테이블: `etf_registry`(유니버스)·`etf_daily`(NAV·AUM·상장주식수)·`etf_constituents`(구성종목·비중·평가액·시총·invest_amt, PK=date+etf_code+stock_code)·`collection_log`(status/source/fingerprint)·`etf_changes`(편입/편출/급변)·`mcap_cache`·`excd_map`·`alert_sent`(항목 단위 발송 이력).
- 전량 보존(알림 필터는 DB가 아닌 발송 단계에만 적용). 뷰어 `build_viewer_boutique.py` + [[src-boutique-etf]] 알림이 소비.
- `BOUTIQUE_ETF_DB` env로 경로 오버라이드 가능. WAL 모드.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-boutique-etf]] — 부티크 액티브 ETF 팔로업 (boutique_etf collect+alert)

## Code
- (none)
