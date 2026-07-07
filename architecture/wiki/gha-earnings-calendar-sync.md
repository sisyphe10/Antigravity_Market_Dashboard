---
id: "gha-earnings-calendar-sync"
name: "Earnings Calendar Sync (07:00)"
domain: "news-research"
project: "antigravity"
type: "gha_workflow"
runs_on: "gha"
schedule_kst: "07:00 매일"
status: "active"
code:
  - ".github/workflows/earnings_calendar_sync.yml"
  - "execution/earnings_calendar_sync.py"
reads: []
writes: []
depends_on:
  - "src-earnings-calendar-sync"
  - "ext-google-workspace"
alerts: "실패 자체 알림 없음 (repo 밖 산출) → Phase 2 heartbeat 감시"
---

# Earnings Calendar Sync (07:00)

**Domain:** 뉴스 · 리서치 · **Type:** GHA · **Runs on:** gha · **Schedule (KST):** 07:00 매일 · **Status:** active · **Project:** antigravity

Finnhub 실적 일정을 Google Calendar에 동기화하는 워크플로(07:00 KST/22:00 UTC). 산출은 repo 밖(캘린더 직접 기록) → git push 없음.

- ★이중 실행: **VM cron(15:00 KST)도 같은 스크립트를 돌린다** → 맥미니 이전 시 단일화 필요(캘린더 중복 우려).
- repo 밖 산출이라 신선도 감시 사각 → Phase 2 heartbeat가 커버.
- 시크릿: FINNHUB_API_KEY, GOOGLE_SERVICE_ACCOUNT_KEY. 실적봇 다이제스트가 이 캘린더를 소비.
- 교훈: SA키 stale로 한 달 무성공 사각 → 로컬 키 검증 후 secret 교체.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-earnings-calendar-sync]] — 실적 캘린더 sync (earnings_calendar_sync.py)
- [[ext-google-workspace]] — Google Workspace (Sheets · Calendar · Drive)

## Code
- `.github/workflows/earnings_calendar_sync.yml`
- `execution/earnings_calendar_sync.py`

## Alerts
⚠ 실패 자체 알림 없음 (repo 밖 산출) → Phase 2 heartbeat 감시
