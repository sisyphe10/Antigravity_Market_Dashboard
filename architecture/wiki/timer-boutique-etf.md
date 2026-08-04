---
id: "timer-boutique-etf"
name: "부티크 액티브 ETF 타이머 (09:10/10:10/18:20 평일)"
domain: "market-kr"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "09:10 / 10:10 / 18:20 평일"
status: "active"
code:
  - "launchd/timers/com.antigravity.boutique-etf.plist"
  - "launchd/timers/run_timer_job.sh"
  - "scripts/run_boutique_etf.sh"
reads: []
writes:
  - "store-boutique-etf-db"
depends_on:
  - "src-boutique-etf"
alerts: "run_timer_job stamp + OnFailure 텔레그램"
---

# 부티크 액티브 ETF 타이머 (09:10/10:10/18:20 평일)

**Domain:** 국내 시장 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 09:10 / 10:10 / 18:20 평일 · **Status:** active · **Project:** antigravity

2026-08-04 신설. 매 영업일 3회 [[src-boutique-etf]] 수집+알림+뷰어 재빌드를 실행하는 launchd 타이머(`com.antigravity.boutique-etf` → `run_timer_job.sh boutique-etf` → `run_boutique_etf.sh`).

- **스케줄 근거**: ETF 자산구성내역(PDF)은 매 영업일 **장 개시 전** 공표 → **09:10**이 본 실행이자 가장 이른 인지 시점(사용자 요구=갱신 즉시). **10:10**=늦게 올리는 운용사 보충, **18:20**=최종 안전망. 수집은 ETF 단위 멱등, 알림은 항목 단위 증분(`alert_sent`)이라 3회 실행해도 중복 없이 늦게 온 것만 `(추가)`로 나감.
- `run_timer_job.sh`가 .env 로드·락·타임아웃(900s)·stamp를 담당. `run_boutique_etf.sh`는 collect가 부분 실패해도 alert·뷰어 실행 후 코드 반환(공휴일 전량 stale·일부 운용사 장애 대응).
- `schedule.tsv`에 3행 등재.

## Reads
- (none)

## Writes
- [[store-boutique-etf-db]] — boutique_etf.db (부티크 액티브 ETF SQLite)

## Depends on
- [[src-boutique-etf]] — 부티크 액티브 ETF 팔로업 (boutique_etf collect+alert)

## Code
- `launchd/timers/com.antigravity.boutique-etf.plist`
- `launchd/timers/run_timer_job.sh`
- `scripts/run_boutique_etf.sh`

## Alerts
⚠ run_timer_job stamp + OnFailure 텔레그램
