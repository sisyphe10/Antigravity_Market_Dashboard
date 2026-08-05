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
- **신용잔고 시장별 분리(2026-08-04)**: 전체 신용잔고 한 계열에 더해 **코스피/코스닥 신용잔고**를 별도 2계열로 쪼개 DATA 탭에 등재(2021-11~ 백필, 시장당 1,155행). dataset append를 일반화하고 json 신용창을 clip. create_dashboard가 코스피/코스닥 신용잔고 계열을 억원 단위로 배선.

## Reads
- (none)

## Writes
- `kofia_stats.json`
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_kofia_stats.py`
