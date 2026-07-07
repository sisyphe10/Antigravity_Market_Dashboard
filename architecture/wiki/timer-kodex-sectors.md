---
id: "timer-kodex-sectors"
name: "KODEX 섹터 타이머 (23:30, +KOSIS/일본capex 편승)"
domain: "tech-semis"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "23:30 매일"
status: "active"
code:
  - "scripts/kodex-sectors.timer"
  - "scripts/kodex-sectors.service"
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
alerts: "OnFailure → sisyphe-bot-notify@kodex-sectors → 텔레그램"
---

# KODEX 섹터 타이머 (23:30, +KOSIS/일본capex 편승)

**Domain:** 반도체 · 테크 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 23:30 매일 · **Status:** active · **Project:** antigravity

매일 23:30 KST(daily_crawl 23:00 직후) KOSPI200/KOSDAQ150 섹터 비중을 수집하는 타이머. 클라우드 IP가 KRX/KOSIS/SEAJ를 막아 VM 경로 전용이라, GHA로 못 하는 3종 수집이 여기에 편승한다.

- `run_kodex_sectors.sh`가 순서대로: `fetch_kodex_sectors.py`(섹터) → `fetch_kosis_series.py`(KOSIS 유통·소비·고용·미분양·퇴직연금) → `fetch_japan_capex.py`(SEAJ 반도체장비/JMTBA 공작기계).
- stale `.git/index.lock` 60초 가드 + flock 중복실행 방지 내장.
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

## Code
- `scripts/kodex-sectors.timer`
- `scripts/kodex-sectors.service`
- `scripts/run_kodex_sectors.sh`
- `launchd/timers/com.antigravity.kodex-sectors.plist`

## Alerts
⚠ OnFailure → sisyphe-bot-notify@kodex-sectors → 텔레그램
