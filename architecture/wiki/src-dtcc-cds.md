---
id: "src-dtcc-cds"
name: "DTCC 하이퍼스케일러 CDS 5Y (fetch_dtcc_cds.py)"
domain: "market-global"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "11:30 화~토 (gha-dtcc-cds)"
status: "active"
code:
  - "execution/fetch_dtcc_cds.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on: []
alerts: ""
---

# DTCC 하이퍼스케일러 CDS 5Y (fetch_dtcc_cds.py)

**Domain:** 해외 · 매크로 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 11:30 화~토 (gha-dtcc-cds) · **Status:** active · **Project:** antigravity

JPM 커스텀 지수 JPAIHYRS(AI 하이퍼스케일러 신용 스프레드) 근사 프록시. 도드-프랭크 공시(DTCC PPD SEC/CFTC 일별 누적 슬라이스, 무료·무인증)에서 단일명 CDS 체결을 수집해 종목 5Y 스프레드 5종 + 시총가중 바스켓(빅5)을 dataset.csv DATA INTEREST RATES에 등재.

- ★공개창 ~2년 롤링(실측 경계 2024-06-09 부근) → 원본 zip을 `~/datalake/raw/dtcc_sbsdr/`에 영구 보존. zip이 정본, 시리즈는 매 run 전 기간 재계산(upsert-heal, 늦은 CORR 자동 소급).
- 관측 = NEWT×TRAD×Spread notation 3만. CORR/EROR=supersede, MODI 제외. 5Y=체결일+5년 최근접 표준롤(6/20·12/20) 정확 일치. ET 체결일 스탬프, 일중 비가중 중앙값(블록 노셔널 캡).
- 매칭 = REDID+anchored 법인명 alias(부분문자열 금지 — AMENTUM(AMAZON HOLDCO) 등 오인 차단), 신규 표기는 발견 리포트로 수동 승인.
- 바스켓 = 빅5(ORCL/AMZN/META/MSFT/GOOGL) 시총가중(datalake overseas_ohlcv 종가 × 유효주식수), 스프레드 ffill 상한 15영업일, 전 구성원 유효일만 산출. 코어위브는 관측 5일 미만 미등재(원본은 축적).
- CFTC(CDX 지수) zip도 동시 보존 — 상대 스프레드 시리즈는 2단계.

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- (none)

## Code
- `execution/fetch_dtcc_cds.py`
