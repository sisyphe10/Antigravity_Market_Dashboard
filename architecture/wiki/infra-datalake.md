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
  - "datalake/mirror_sheets.py"
  - "datalake/launchd/"
reads:
  - "ext-data-apis"
  - "ext-google-workspace"
  - "store-research-notes-db"
writes:
  - "~/datalake (parquet · duckdb · md 아카이브)"
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
  - `datalake-macro-update`(20:50, 2026-07-22 신규) — 매크로 3소스 멱등 재적재(`daily_macro_update.py`): `backfill_ecos`·`backfill_fred`(YoY 계산이 전 이력 필요) 전량 재실행 + `backfill_kofia --pages 1`. GHA 매크로 잡([[gha-daily-ecos]]·[[gha-daily-fred]]·[[gha-daily-kofia]])과 별개로 데이터레이크 정본에 당일분을 채운다.
  - `datalake-research-export`(23:20) — Research Notes 원문(`research_notes.db`)을 일별 `.md`+미디어로 아카이브.
  - `datalake-snapshot`(23:50) — 덮어쓰기형 레포 산출물 일별 gzip 스냅샷.
  - `viewer-daily`(23:50, 2026-07-22 신규) — 현선물/공매도/ETF 차트 뷰어 수집+빌드(`~/work/charts/260715_현선물공매도/run_daily.py`). KRX 야간 배포·kodex 23:30 잡 뒤에 배치.
  - `datalake-backup`(일 10:00) — private repo 백업(duckdb/staging 제외).
  - `datalake-sheets-mirror`(20분 폴링, 2026-07-12 신규) — 시지프+선유듀오 구글시트 미러 → `~/datalake/sheets`. 시트 단위 격리 + **3회 재시도(15s·30s 백오프, 2026-07-14)** — read timeout 등 일시 장애를 흡수하고 3회 연속 실패만 비정상 종료→알림(오탐 알림 억제).
- 저장: 데이터셋별 연도 파티션 parquet(`kr_ohlcv`·`kr_marcap`·`overseas_ohlcv` 등) + `market.duckdb` 뷰. KRX 수정주가 캡 실측 대응으로 `kr_ohlcv`(무수정)/`kr_ohlcv_adj` 분리.
- **`kr_fundamental` 패스(2026-07-20 재활성화)**: KRX 주당지표(BPS/PER/PBR/EPS/DIV/DPS). 연간 확정 BPS 기준이라 분기 정밀 밸류엔 계단식으로 부정확해 2026-07-13 제외됐으나, 장기 PBR/PER 밴드·사이클 고점 분석엔 표준 소스라 사용자 요청으로 되살림.
- **공매도·선물 패스(2026-07-15 신규)**: `kr_short`(종목별 일별 공매도 거래량·거래대금·잔고수량/금액, KRX SRT30001 — 잔고는 T+2 공시라 최근 1~2일 NaN이 lookback 재조회로 self-heal. ★전면금지 2023-11-06~2025-03-30·부분금지 2020-03-16~2021-05-02 구간은 빈 값이 정상) · `kr_short_investor`(시장단위 투자자별 공매도) · `kr_futures_ohlcv`(선물 7상품 월물별 시세+미결제약정, 상품 단위 합계는 `kr_futures_oi_daily` 뷰). 선물 OI는 pykrx api wrapper가 `ACC_OPNINT_QTY`를 떨궈 **core 전종목시세(MDCSTAT12501) 클래스를 직접 호출**하고, 백필은 (상품,연도) 단위 staging 체크포인트로 재개한다.
- 웹 UI(`datalake/webui/`)는 duckdb 샌드박스(allowed→잠금) 위에서 md 코퍼스 문답. 상세: `datalake/DESIGN.md`.

## Reads
- [[ext-data-apis]] — 외부 데이터 API/소스 집합
- [[ext-google-workspace]] — Google Workspace (Sheets · Calendar · Drive)
- [[store-research-notes-db]] — research_notes.db + media/ (리서치봇)

## Writes
- `~/datalake (parquet · duckdb · md 아카이브)`

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `datalake/`
- `datalake/daily_market_update.py`
- `datalake/mirror_sheets.py`
- `datalake/launchd/`

## Alerts
⚠ launchd wrapper 실패 → notify → 텔레그램
