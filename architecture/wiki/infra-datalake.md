---
id: "infra-datalake"
name: "맥미니 데이터레이크 (~/datalake + 문답 위키)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "vm_macmini"
schedule_kst: "잡별 (20:30 / 23:20 / 23:50 / 일 10:00 / 20분)"
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

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** vm_macmini · **Schedule (KST):** 잡별 (20:30 / 23:20 / 23:50 / 일 10:00 / 20분) · **Status:** active · **Project:** antigravity

2026-07-11 신설(코드는 레포 `datalake/`, 데이터 정본은 레포 외부 `~/datalake`). 덮어쓰기형 산출물의 과거 유실을 막고, 전 상장·해외 유니버스 일봉 종가를 백필하며, DuckDB+Claude API 웹 UI로 자연어 질의를 제공하는 로컬 데이터레이크. 백필 스크립트(KRX/KIS·FRED·ECOS·KOFIA·벤치마크·해외)와 `build_catalog.py` 카탈로그가 함께 있다.

- **launchd 잡 5종**(맥미니 전용):
  - `datalake-market-update`(20:30) — 일별 증분 적재(`daily_market_update.py`).
  - `datalake-research-export`(23:20) — Research Notes 원문(`research_notes.db`)을 일별 `.md`+미디어로 아카이브.
  - `datalake-snapshot`(23:50) — 덮어쓰기형 레포 산출물 일별 gzip 스냅샷.
  - `datalake-backup`(일 10:00) — private repo 백업(duckdb/staging 제외).
  - `datalake-sheets-mirror`(20분 폴링, 2026-07-12 신규) — 시지프+선유듀오 구글시트 미러 → `~/datalake/sheets`.
- 저장: 데이터셋별 연도 파티션 parquet(`kr_ohlcv`·`kr_marcap`·`overseas_ohlcv` 등) + `market.duckdb` 뷰. KRX 수정주가 캡 실측 대응으로 `kr_ohlcv`(무수정)/`kr_ohlcv_adj` 분리.
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
