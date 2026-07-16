---
id: "src-deriv-daily"
name: "파생·수급 13종 (fetch_deriv_daily.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "23:30 (kodex 타이머 편승)"
status: "active"
code:
  - "execution/fetch_deriv_daily.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "timer-kodex-sectors"
  - "ext-data-apis"
alerts: "실패해도 타이머 계속(|| true) — 결손은 신선도 점검(3영업일)이 경보"
---

# 파생·수급 13종 (fetch_deriv_daily.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 23:30 (kodex 타이머 편승) · **Status:** active · **Project:** antigravity

2026-07-16 신설. 삼성전자·SK하이닉스의 파생·수급 지표와 VKOSPI를 매일 수집해 `dataset.csv`에 적재하는 소스. 이력은 커밋 `19eeefcd`로 백필됐다.

- **시리즈 13종** — 종목별(삼성전자·SK하이닉스) 6종: 현선물 괴리율(%, KRX MDCSTAT12501 최근월물), 미결제약정(계약, 전월물 합산), 미결제약정 금액(억원, 합산계약×승수10주×최근월물 종가), 공매도잔고(억원, pykrx, **T+2 공시**), 시가총액(억원, pykrx), 레버리지 ETF AUM(억원, KRX MDCSTAT04501 단일종목 레버리지·인버스 제외 순자산 합산). 여기에 `VKOSPI`(pt, KIS FHKUP03500100 업종 U/0503).
- 기본 최근 7일 upsert(휴장일 조용 skip → T+2 공매도가 자연 보정), `--days N`으로 조정.
- **실행 경로**: `run_kodex_sectors.sh`가 kodex→KOSIS→일본capex 다음 4번째로 `|| true` 호출 — 즉 23:30 [[timer-kodex-sectors]] 편승이다. KRX 인증이 필요해 클라우드 IP가 막히는 VM 전용 경로에 얹은 것으로, KRX 로그인은 kodex와 직렬화된다.
- ★**함정**: 소스 docstring은 '맥미니 launchd deriv-daily (23:40 KST)'라고 적혀 있으나 그런 타이머 유닛은 없다(`schedule.tsv`·`launchd/timers/` 모두 부재) — 실제는 위 23:30 편승. docstring이 stale.
- 소비자: `create_dashboard.py`가 market.html DATA 탭 '파생·수급' 그룹 차트로 그린다([[page-market]]).

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[timer-kodex-sectors]] — KODEX 섹터 타이머 (23:30, +KOSIS/일본capex/파생 편승)
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_deriv_daily.py`

## Alerts
⚠ 실패해도 타이머 계속(|| true) — 결손은 신선도 점검(3영업일)이 경보
