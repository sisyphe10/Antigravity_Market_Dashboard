---
id: "src-create-market-alert"
name: "투자유의 생성기 (create_market_alert.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "16:05 / 23:00 (sisyphe-bot)"
status: "active"
code:
  - "execution/create_market_alert.py"
reads: []
writes:
  - "page-market-alert"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# 투자유의 생성기 (create_market_alert.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 16:05 / 23:00 (sisyphe-bot) · **Status:** active · **Project:** antigravity

투자유의/경고/위험 지정 종목 페이지 `market_alert.html`을 생성. Sisyphe-Bot 16:05/23:00 잡이 호출.

- KIS marcap 사용. 지정예고는 투자주의 fetch에 들어옴(경고 아님) 함정.
- 텔레그램 4블록 요약은 RA_Sisyphe_bot(05:15)가 이 결과를 읽어 별도 발송.

## Reads
- (none)

## Writes
- [[page-market-alert]] — market_alert.html (투자유의종목)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/create_market_alert.py`
