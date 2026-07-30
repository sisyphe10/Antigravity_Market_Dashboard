---
id: "store-roc-history"
name: "roc_history.csv (RoC² 월말 백필)"
domain: "market-global"
project: "antigravity"
type: "dataset"
runs_on: "github"
schedule_kst: "Daily Market Crawl + macro-update 20:50"
status: "active"
code:
  - "datalake/build_roc_history.py"
reads: []
writes: []
depends_on:
  - "infra-datalake"
alerts: ""
---

# roc_history.csv (RoC² 월말 백필)

**Domain:** 해외 · 매크로 · **Type:** Dataset · **Runs on:** github · **Schedule (KST):** Daily Market Crawl + macro-update 20:50 · **Status:** active · **Project:** antigravity

2026-07-30 신설. [[page-market]] DATA 탭 RoC²(변화율의 변화율) 서브패널 전용 월말 시계열(`series,date,value` — 각 월 마지막 관측).

- **왜 별도 파일인가**: DATA 탭 RoC² 는 YoY lag 12개월 + MA3 때문에 월 14버킷 이상을 요구하는데, `dataset.csv` 의 일별 시장 시리즈는 이력이 12개월뿐이라 KOSPI·S&P500·환율 등 31종이 계산 불가였다(2026-07-29 실측 120/184종만 가능). 일별 원계열을 dataset.csv 에 통째로 백필하지 않는 이유는 ① RoC² 는 월 버킷만 써서 일별은 낭비 ② dataset.csv 에 월말 과거를 섞으면 메인 차트 과거 구간이 월별로 끊김 ③ market.html 이 인라인 JSON 으로 싣는 구조라 일별 25만행은 페이지를 폭발시킴 — 그래서 dataset.csv 는 손대지 않고 RoC² 전용 월말 채널을 따로 둔다.
- **생성**: [[infra-datalake]] `build_roc_history.py` 가 데이터레이크(`global_markets`·`kr_index_ohlcv`)에서 각 월 마지막 관측만 뽑아 산출. 티커 정의는 `execution/config.py` YFINANCE_TICKERS 단일 출처를 읽고, config 미보유분(S&P 500·NASDAQ 종합·RUSSELL 2000 등)만 별도 명시. 지수·환율·금리·원자재·크립토 장기 이력 백필은 `backfill_benchmarks.py`·`backfill_macro_extra.py` 가 채운다.
- **소비**: [[src-create-dashboard]] 가 `cmbRocHist` 인라인 JSON 으로 market.html 에 싣고, RoC² 판독성 화이트리스트(`score_roc2.py` 산출: 부호 런 평균 길이 + lag-1 자기상관)로 필터링된 시리즈만 서브패널에 노출. csv 는 `dataset.csv` '제품명' 키라 사이드바 표시명으로 정규화해 매칭한다.
- **적재 순서**: Daily Market Crawl(run_gha_job.sh)이 `accumulate_macro_series.py` → `build_roc_history.py` → `create_dashboard.py` 순으로 실행해 당일 갱신본을 market.html 이 싣도록 보장. datalake/duckdb 부재·잠금은 비치명 처리(대시보드를 막지 않음).

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[infra-datalake]] — 맥미니 데이터레이크 (~/datalake + 문답 위키)

## Code
- `datalake/build_roc_history.py`
