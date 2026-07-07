---
id: "ext-data-apis"
name: "외부 데이터 API/소스 집합"
domain: "ops-infra"
project: "antigravity"
type: "external"
runs_on: "external"
schedule_kst: ""
status: "active"
code: []
reads: []
writes: []
depends_on: []
alerts: ""
---

# 외부 데이터 API/소스 집합

**Domain:** 운영 · 인프라 · **Type:** External · **Runs on:** external · **Status:** active · **Project:** antigravity

수집 파이프라인이 호출하는 외부 데이터 제공처 묶음(맥락용 단일 카드). 개별 수집기는 `pipeline_source`가 소유하고, 여기서는 의존하는 외부 면을 한눈에 본다.

- **시세/지수**: KIS OpenAPI(확정지수·시세), yfinance(해외·환율·원자재·크립토), 네이버 금융.
- **한국 공식통계**: ECOS(한국은행), data.go.kr(금투협/국민연금), KOSIS, KRX(pykrx 로그인), KIND, SEIBro, DART.
- **미국/해외**: FRED, Finnhub(실적캘린더), SEC EDGAR, FinMind(대만 월매출), SEAJ/JMTBA(일본 capex).
- **원자재/산업**: SMM(리튬), Sunsirs(폴리실리콘), DRAMeXchange, SiliconData, KPX(SMP), 다나와.
- **뉴스/리서치**: SemiAnalysis, TrendForce, k-neiss(원전), 해외 IR 뉴스룸 ~134곳.
- 운영 함정: 클라우드 IP 차단(KRX/KOSIS/SEAJ/watch 스크랩) → 해당 수집은 VM 경로 강제.

## Reads
- (none)

## Writes
- (none)

## Depends on
- (none)

## Code
- (none)
