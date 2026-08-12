---
id: "timer-kodex-sectors"
name: "KODEX 섹터 타이머 (23:30 + 08:10, +KOSIS/일본capex/파생 편승)"
domain: "tech-semis"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "23:30 매일 + 08:10 매일(D-1 AUM 확정 백필)"
status: "active"
code:
  - "scripts/vm_legacy/kodex-sectors.timer"
  - "scripts/vm_legacy/kodex-sectors.service"
  - "scripts/run_kodex_sectors.sh"
  - "launchd/timers/com.antigravity.kodex-sectors.plist"
reads: []
writes:
  - "kodex_sectors.json"
  - "store-dataset-csv"
depends_on:
  - "src-kodex-sectors"
  - "src-kosis-series"
  - "src-japan-capex"
  - "src-immigration"
  - "src-deriv-daily"
alerts: "OnFailure → sisyphe-bot-notify@kodex-sectors → 텔레그램"
---

# KODEX 섹터 타이머 (23:30 + 08:10, +KOSIS/일본capex/파생 편승)

**Domain:** 반도체 · 테크 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 23:30 매일 + 08:10 매일(D-1 AUM 확정 백필) · **Status:** active · **Project:** antigravity

매일 23:30 KST(daily_crawl 23:00 직후) KOSPI200/KOSDAQ150 섹터 비중을 수집하는 타이머. 클라우드 IP가 KRX/KOSIS/SEAJ를 막아 VM 경로 전용이라, GHA로 못 하는 수집들이 여기에 편승한다.

- `run_kodex_sectors.sh`가 순서대로: `fetch_kodex_sectors.py`(섹터) → `fetch_kosis_series.py`(KOSIS 유통·소비·고용·미분양·퇴직연금) → `fetch_japan_capex.py`(SEAJ 반도체장비/JMTBA 공작기계) → `fetch_immigration.py`(법무부 출입국 월별 5종, 2026-07-23 추가 — [[src-immigration]]) → `fetch_deriv_daily.py`(삼전·하이닉스 파생·수급 13종, 2026-07-16 추가 — [[src-deriv-daily]]). 편승 4종은 전부 `|| true`라 실패해도 섹터 push는 진행.
- ★**아침 08:10 2회차 발화(2026-08-12 추가)**: plist `StartCalendarInterval`이 배열로 바뀌어 23:30 본 실행 + **매일 08:10** 재실행한다. 이유는 KRX ETF 순자산총액(AUM) — 당일 저녁엔 미확정이라 [[src-deriv-daily]]의 레버리지 ETF AUM(삼성전자·SK하이닉스)이 비고, 전일 확정치가 밤사이 공표되므로 아침 실행이 D-1을 채운다. 래퍼가 통째로 다시 도는 방식이라 편승 4종도 함께 재실행되지만 전부 멱등 upsert다. 08:20 [[gha-daily-krx-valuation]]과 **10분 간격으로 KRX 로그인을 직렬화**(동시 로그인·잠금 회피). catch-up 앵커인 `schedule.tsv`는 **23:30 본 실행만 유지** — 즉 셀프체크 신선도 판정 기준도 23:30이다.
- stale `.git/index.lock` 60초 가드 + flock 중복실행 방지 내장. push 대상은 `kodex_sectors.json` + `dataset.csv`.
- 함정: 실패 알림 문구는 오진 표현, 실제 대개 KRX 인증 오류. loginErrMaxCnt=5 잠금 주의(반복 로그인 금지).

## Reads
- (none)

## Writes
- `kodex_sectors.json`
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[src-kodex-sectors]] — KODEX 섹터 비중 (fetch_kodex_sectors.py)
- [[src-kosis-series]] — KOSIS 시계열 레지스트리 (fetch_kosis_series.py)
- [[src-japan-capex]] — 일본 CAPEX 지표 (fetch_japan_capex.py)
- [[src-immigration]] — 출입국 월별 통계 (fetch_immigration.py)
- [[src-deriv-daily]] — 파생·수급 13종 (fetch_deriv_daily.py)

## Code
- `scripts/vm_legacy/kodex-sectors.timer`
- `scripts/vm_legacy/kodex-sectors.service`
- `scripts/run_kodex_sectors.sh`
- `launchd/timers/com.antigravity.kodex-sectors.plist`

## Alerts
⚠ OnFailure → sisyphe-bot-notify@kodex-sectors → 텔레그램
