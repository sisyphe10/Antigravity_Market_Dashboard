---
id: "src-kosdaq-lev-etf-aum"
name: "코스닥 레버리지 ETF AUM (fetch_kosdaq_lev_etf_aum.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "18:30 + 08:20 평일 (gha-daily-krx-valuation 합승)"
status: "active"
code:
  - "execution/fetch_kosdaq_lev_etf_aum.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# 코스닥 레버리지 ETF AUM (fetch_kosdaq_lev_etf_aum.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 18:30 + 08:20 평일 (gha-daily-krx-valuation 합승) · **Status:** active · **Project:** antigravity

코스닥 레버리지 ETF의 일간 순자산총액(AUM) 합산을 KRX MDCSTAT04301(ETF 전종목시세)에서 날짜당 1콜로 수집해 dataset.csv에 적재(2026-08-10 신설). 시리즈 1개 — `코스닥 레버리지 ETF AUM`, dtype `ETF_AUM`, 값=원 단위 정수.

- **대상 선정은 종목 마스터가 아니라 날짜별 종목명 필터**("코스닥"+"레버리지", 공백 정규화) — 상장·상폐·브랜드 개명(KBSTAR→RISE 등)이 자동 반영된다. 2026-08 기준 5종(KODEX 233740·TIGER 233160·RISE 278240·HANARO 306530·KIWOOM 291630). 구성 변동으로 생기는 점프는 신호의 일부로 보고 **보정·평활화하지 않는다**.
- **엄격 합산**: 대상 중 한 종목이라도 AUM 파싱 불가면 그 날짜는 통째로 미적재(조용한 과소계상 방지). 전 종목이 `-`면 비거래일로 보고 skip.
- ★**당일 0 = 결측(2026-08-12 fix, `e471e20f`)**: KRX는 **당일 저녁 미확정 AUM을 `-`가 아니라 `0`으로 반환**한다(8/10·8/11 실측). 종전 파서는 `-`(dashes)와 음수만 걸렀기에 0이 유효값으로 합산돼 **AUM이 0에 가깝게 폭락한 가짜 점프**가 적재됐다. 이제 `v == 0`을 dashes로 세어 결측 취급하고, 전 종목 0이면 기존 `holiday` 분기가 그대로 잡아 skip한다. 실존 ETF의 AUM 0은 불가능하므로 유효값 손실은 없다. 오염된 08-11 값은 같은 커밋에서 lookback 재조회로 치유했다.
  - 이 성질이 곧 **08:20 아침 실행([[gha-daily-krx-valuation]])의 존재 이유**다 — 당일 18:30 실행은 구조적으로 당일분을 넣을 수 없고(0→결측), 전일 확정치가 밤사이 공표되므로 아침 실행의 lookback 창이 D-1을 채운다. 즉 이 시리즈는 **항상 D-1까지만** 채워진 상태가 정상이다.
- 증분 = 기존 max 날짜 − lookback 10일 재조회 후 (날짜, 제품명) upsert. `--backfill`은 2015-12-17(KODEX 233740 상장일)부터 평일 순회하며 콜 간 0.5~0.8초 랜덤 sleep + 신규 50행마다 체크포인트 append(중단 재개 가능). 최초 백필 2015-12-17~2026-08-07 2,608행(`aa0510ab`).
- 로그인은 [[src-krx-valuation]]과 동일 경로(pykrx 패치판이 import 시 env `KRX_ID`/`KRX_PW`로 로그인, 세션은 `get_auth_session()`). ★**프로세스당 1회, 실패해도 재시도하지 않는다** — KRX는 로그인 5회 실패 시 계정 잠금. 자격증명 값은 어떤 경로로도 출력하지 않는다.
- 소비: market.html DATA 탭 INDEX_KOREA 패널에 배선(표시 단위 **억원**, `CMB_SERIES_SCALE` 1e8 제수 — 축이 1조를 넘으면 조원으로 자동 승격). `ETF_AUM`은 create_dashboard의 **5년 창(long_mask)** 대상이라 기본 2년 창보다 긴 이력이 임베드되고, draw_charts의 `ETF_` 프리픽스 제외 규칙에 걸려 **PNG는 만들지 않는다**(동적 차트 전용).

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_kosdaq_lev_etf_aum.py`
