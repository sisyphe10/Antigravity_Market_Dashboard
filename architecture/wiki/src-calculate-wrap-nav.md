---
id: "src-calculate-wrap-nav"
name: "기준가 엔진 (calculate_wrap_nav.py)"
domain: "portfolio-wrap"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "체인 (finalize/recalc/crawl)"
status: "active"
code:
  - "calculate_wrap_nav.py"
reads:
  - "store-wrap-nav-xlsx"
writes:
  - "store-wrap-nav-xlsx"
depends_on:
  - "store-wrap-nav-xlsx"
  - "ext-data-apis"
alerts: ""
---

# 기준가 엔진 (calculate_wrap_nav.py)

**Domain:** 포트폴리오 · WRAP · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 체인 (finalize/recalc/crawl) · **Status:** active · **Project:** antigravity

Wrap_NAV.xlsx의 NEW(종목·비중)+AUM 시트로 랩 상품별 일별 기준가를 계산해 기준가 시트에 적재하는 NAV 엔진.

- 지수/종가는 KIS 확정 일봉이 primary(잠정 종가 자가복구: 신규 포트폴리오 없는 일반 실행은 최근 3거래일 롤백 재계산).
- 목표전환형은 end_date로 청산일까지 완결(주석 금지 — combine_first 동결 버그 방지).
- 상품 정의는 `wrap_config.py` 레지스트리에서 파생.

## Reads
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)

## Writes
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)

## Depends on
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `calculate_wrap_nav.py`
