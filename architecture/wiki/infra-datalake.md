---
id: "infra-datalake"
name: "맥미니 데이터레이크 (~/datalake + 문답 위키)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "vm_macmini"
schedule_kst: "잡별 (20:30 / 20:50 / 23:20 / 23:50 / 일 10:00 / 20분)"
status: "active"
code:
  - "datalake/"
  - "datalake/daily_market_update.py"
  - "datalake/daily_macro_update.py"
  - "datalake/accumulate_macro_series.py"
  - "datalake/build_roc_history.py"
  - "datalake/snapshot_archiver.py"
  - "datalake/mirror_sheets.py"
  - "datalake/launchd/"
reads:
  - "ext-data-apis"
  - "ext-google-workspace"
  - "store-research-notes-db"
writes:
  - "~/datalake (parquet · duckdb · md 아카이브)"
  - "store-research-tags"
  - "store-roc-history"
depends_on:
  - "infra-vm-macmini"
  - "ext-data-apis"
alerts: "launchd wrapper 실패 → notify → 텔레그램"
---

# 맥미니 데이터레이크 (~/datalake + 문답 위키)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** vm_macmini · **Schedule (KST):** 잡별 (20:30 / 20:50 / 23:20 / 23:50 / 일 10:00 / 20분) · **Status:** active · **Project:** antigravity

2026-07-11 신설(코드는 레포 `datalake/`, 데이터 정본은 레포 외부 `~/datalake`). 덮어쓰기형 산출물의 과거 유실을 막고, 전 상장·해외 유니버스 일봉 종가를 백필하며, DuckDB+Claude API 웹 UI로 자연어 질의를 제공하는 로컬 데이터레이크. 백필 스크립트(KRX/KIS·FRED·ECOS·KOFIA·벤치마크·해외)와 `build_catalog.py` 카탈로그가 함께 있다.

- **launchd 잡 7종**(맥미니 전용, wrapper=`datalake/launchd/run_datalake_job.sh`):
  - `datalake-market-update`(20:30) — 일별 증분 적재(`daily_market_update.py`). 2026-07-22 `kr_fundamental` 일별 단면(BPS/PER/PBR 등)을 여기에 추가(휴장일 가드).
  - `datalake-macro-update`(20:50, 2026-07-22 신규) — 매크로 소스 멱등 재적재(`daily_macro_update.py`): 레포 `dataset.csv`→`macro_series` 누적 upsert(`accumulate_macro_series.py`, 2026-07-30 추가) + `backfill_ecos`·`backfill_fred`(YoY 계산이 전 이력 필요) 전량 재실행 + `backfill_kofia --pages 1`. GHA 매크로 잡([[gha-daily-ecos]]·[[gha-daily-fred]]·[[gha-daily-kofia]])과 별개로 데이터레이크 정본에 당일분을 채운다.
  - `datalake-research-export`(23:20) — Research Notes 파이프라인(`datalake/tagging/daily_tag_export.sh`, 2026-07-27부터 태깅 포함): 태깅→md 아카이브→parquet→추이 집계→차트. 원문(`research_notes.db`)을 일별 `.md`+미디어로 아카이브하고, 그 위에 테마·개체 태그를 얹는다(정본 `tag_state.sqlite`). 상세 [[src-research-tagging]] · 출력 [[store-research-tags]].
  - `datalake-snapshot`(23:50) — 덮어쓰기형 레포 산출물 일별 gzip 스냅샷(`snapshot_archiver.py`). 2026-07-30 `dataset.csv`를 화이트리스트에 추가 — "누적형은 자체 보존"이라 제외돼 있었으나 야후 연속선물처럼 과거 값이 소급 재작성되는 시리즈가 있어 원본을 일별 보존한다.
  - `viewer-daily`(23:50, 2026-07-22 신규) — 현선물/공매도/ETF 차트 뷰어 수집+빌드(`~/work/charts/260715_현선물공매도/run_daily.py`). KRX 야간 배포·kodex 23:30 잡 뒤에 배치.
  - `datalake-backup`(일 10:00) — private repo 백업(duckdb/staging 제외).
  - `datalake-sheets-mirror`(20분 폴링, 2026-07-12 신규) — 시지프+선유듀오 구글시트 미러 → `~/datalake/sheets`. 시트 단위 격리 + **3회 재시도(15s·30s 백오프, 2026-07-14)** — read timeout 등 일시 장애를 흡수하고 3회 연속 실패만 비정상 종료→알림(오탐 알림 억제).
- 저장: 데이터셋별 연도 파티션 parquet(`kr_ohlcv`·`kr_marcap`·`overseas_ohlcv` 등) + `market.duckdb` 뷰. KRX 수정주가 캡 실측 대응으로 `kr_ohlcv`(무수정)/`kr_ohlcv_adj` 분리.
- **`kr_fundamental` 패스(2026-07-20 재활성화)**: KRX 주당지표(BPS/PER/PBR/EPS/DIV/DPS). 연간 확정 BPS 기준이라 분기 정밀 밸류엔 계단식으로 부정확해 2026-07-13 제외됐으나, 장기 PBR/PER 밴드·사이클 고점 분석엔 표준 소스라 사용자 요청으로 되살림.
- **공매도·선물 패스(2026-07-15 신규)**: `kr_short`(종목별 일별 공매도 거래량·거래대금·잔고수량/금액, KRX SRT30001 — 잔고는 T+2 공시라 최근 1~2일 NaN이 lookback 재조회로 self-heal. ★전면금지 2023-11-06~2025-03-30·부분금지 2020-03-16~2021-05-02 구간은 빈 값이 정상) · `kr_short_investor`(시장단위 투자자별 공매도) · `kr_futures_ohlcv`(선물 7상품 월물별 시세+미결제약정, 상품 단위 합계는 `kr_futures_oi_daily` 뷰). 선물 OI는 pykrx api wrapper가 `ACC_OPNINT_QTY`를 떨궈 **core 전종목시세(MDCSTAT12501) 클래스를 직접 호출**하고, 백필은 (상품,연도) 단위 staging 체크포인트로 재개한다.
- **파생 투자자별 수급 패스(`kr_deriv_investor`, 2026-07-26 신규)**: 파생상품 투자자별 순매수를 일별 적재(KRX [13106] MDCSTAT13103). 10상품(선물 7상품+K200옵션+선물전체+옵션전체) × 단위 2종(`metric`=volume 계약 | value 원) × 방향 3종(`side`=ask 매도 | bid 매수 | net 순매수)에 세부 주체 9종(금융투자~외국인) + 기관합계 파생 컬럼. pykrx 미노출 화면이라 `KrxWebIo`를 `backfill_krx.py`에 직접 구현해 호출한다. 일별 증분은 `daily_market_update.py`의 `deriv_investor_update()`가 최근 `RANGE_DAYS` 창을 재조회(10×2×3=60콜, ~30초) upsert. 검증: 7/20주 K200선물 외국인 순매수 −1,308계약이 네이버 교차 일치. `build_catalog.py`에 뷰 설명·예시 SQL 등록.
- **`macro_series` 미러→누적 전환(2026-07-30 신규, `accumulate_macro_series.py`)**: 종전 `macro_series`는 `dataset.csv`를 `shutil.copy2`로 통째 복사한 사본을 읽는 DuckDB VIEW(=미러)라, dataset.csv에서 행이 사라지면 레이크에서도 사라져 "덮어쓰기형 산출물 과거 유실 방지"라는 본래 목적을 900여 시리즈에 대해 달성하지 못했다. 이제 연도 파티션 parquet에 `(date, series)` 키로 **upsert 누적**한다(행 삭제 무시·정정은 keep=last 반영·멱등). 20:50 macro-update뿐 아니라 GHA Daily Market Crawl 파이프라인([[gha-daily-crawl]])에서도 당일 수집분을 즉시 누적한다.
- **RoC² 월말 백필 채널(2026-07-30 신규, `build_roc_history.py`→[[store-roc-history]])**: [[page-market]] DATA 탭 RoC² 서브패널은 YoY lag 12개월 + MA3 때문에 월 14버킷을 요구하는데 `dataset.csv`의 일별 시장 시리즈는 이력이 12개월뿐이라 KOSPI·S&P500·환율 등 31종이 계산 불가였다. 일별 원계열을 dataset.csv에 통째로 백필하지 않고(월 버킷만 쓰므로 낭비·메인 차트 과거 구간 단절·인라인 JSON 폭발 회피), 데이터레이크(`global_markets`·`kr_index_ohlcv`)에서 각 월 마지막 관측만 뽑아 `roc_history.csv`로 내보내는 전용 월말 채널을 신설했다. 후보 시리즈 화이트리스트는 `score_roc2.py`(부호 런 평균 길이 + lag-1 자기상관 판독성 점수)가 산출하고, 지수·환율·금리·원자재·크립토 백필은 `backfill_benchmarks.py`·`backfill_macro_extra.py`가 채운다.
- 웹 UI(`datalake/webui/`)는 duckdb 샌드박스(allowed→잠금) 위에서 md 코퍼스 문답. 상세: `datalake/DESIGN.md`.

## Reads
- [[ext-data-apis]] — 외부 데이터 API/소스 집합
- [[ext-google-workspace]] — Google Workspace (Sheets · Calendar · Drive)
- [[store-research-notes-db]] — research_notes.db + media/ (리서치봇)

## Writes
- `~/datalake (parquet · duckdb · md 아카이브)`
- [[store-research-tags]] — 리서치 태그 정본 (tag_state.sqlite + theme_trends.json + parquet)
- [[store-roc-history]] — roc_history.csv (RoC² 월말 백필)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `datalake/`
- `datalake/daily_market_update.py`
- `datalake/daily_macro_update.py`
- `datalake/accumulate_macro_series.py`
- `datalake/build_roc_history.py`
- `datalake/snapshot_archiver.py`
- `datalake/mirror_sheets.py`
- `datalake/launchd/`

## Alerts
⚠ launchd wrapper 실패 → notify → 텔레그램
