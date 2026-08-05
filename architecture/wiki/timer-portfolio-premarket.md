---
id: "timer-portfolio-premarket"
name: "장전 포트폴리오 재생성 타이머 (07:30 평일)"
domain: "portfolio-wrap"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "07:30 평일 (월~금)"
status: "active"
code:
  - "launchd/timers/com.antigravity.portfolio-premarket.plist"
  - "scripts/premarket_portfolio_refresh.sh"
reads:
  - "store-wrap-nav-xlsx"
writes:
  - "store-portfolio-data"
  - "page-wrap"
depends_on:
  - "src-create-portfolio-tables"
  - "src-create-dashboard"
alerts: "실패 → notify_sisyphe_failure.sh portfolio-premarket → 텔레그램"
---

# 장전 포트폴리오 재생성 타이머 (07:30 평일)

**Domain:** 포트폴리오 · WRAP · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 07:30 평일 (월~금) · **Status:** active · **Project:** antigravity

2026-08-05 신설. 개장 전 평일 07:30 KST에 포트폴리오 구성 표(`portfolio_data.json`)를 한 번 재생성해 기준일을 당일로 넘기는 standalone launchd 타이머(`com.antigravity.portfolio-premarket` → `scripts/premarket_portfolio_refresh.sh`).

- **왜**: [[src-create-portfolio-tables]]는 행 목록을 "D-1 구성 ∪ 오늘 구성" 합집합으로 만든다(전일 편출 종목을 당일 편출 표시용으로 남기는 의도된 동작). 정규 갱신([[bot-sisyphe]] auto_portfolio_update)의 첫 발화가 09:10이라, 그 전 아침 시간대에 WRAP Order 매트릭스·포트 표에 전일 편출 종목이 weight 0 행으로 계속 보였다. 이 잡이 개장 전에 기준일을 당일로 넘겨 그 구간을 없앤다.
- 체인: `git pull` → `create_portfolio_tables.py` → `create_dashboard.py` → `safe_commit_push.sh`(Darwin에서 `publish_pages.sh` 백그라운드로 gh-pages까지 반영). 커밋 메시지 `[skip ci]`.
- `run_timer_job.sh` 래퍼·`schedule.tsv` 미사용 — [[daemon-journal-api]]의 journal-trades와 동일한 standalone plist 규격(StartCalendarInterval 평일 5행, RunAtLoad=false). 실패 시 `notify_sisyphe_failure.sh portfolio-premarket`.

## Reads
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)

## Writes
- [[store-portfolio-data]] — portfolio_data.json
- [[page-wrap]] — wrap.html (WRAP 대시보드)

## Depends on
- [[src-create-portfolio-tables]] — 포트폴리오 표 생성 (create_portfolio_tables.py)
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)

## Code
- `launchd/timers/com.antigravity.portfolio-premarket.plist`
- `scripts/premarket_portfolio_refresh.sh`

## Alerts
⚠ 실패 → notify_sisyphe_failure.sh portfolio-premarket → 텔레그램
