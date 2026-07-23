---
id: "src-kofia"
name: "금투협 예탁금/신용잔고/반대매매 (fetch_kofia_stats.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "21:30 평일 (gha-daily-kofia)"
status: "active"
code:
  - "execution/fetch_kofia_stats.py"
reads: []
writes:
  - "kofia_stats.json"
  - "store-dataset-csv"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# 금투협 예탁금/신용잔고/반대매매 (fetch_kofia_stats.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 21:30 평일 (gha-daily-kofia) · **Status:** active · **Project:** antigravity

고객예탁금/신용잔고/반대매매금액(data.go.kr 금투협 종합통계)을 수집해 `kofia_stats.json`+dataset.csv에 적재(index.html 랜딩 차트, market.html DATA).

- 예탁금=invrDpsgAmt, 신용잔고=crdTrFingWhl, 반대매매금액=brkTrdUcolMnyVsOppsTrdAmt(위탁매매 미수금 반대매매, 억원, 2021-10~ 백필). 오퍼레이션 8종 검증 완료.

## Reads
- (none)

## Writes
- `kofia_stats.json`
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_kofia_stats.py`
