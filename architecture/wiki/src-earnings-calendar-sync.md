---
id: "src-earnings-calendar-sync"
name: "실적 캘린더 sync (earnings_calendar_sync.py)"
domain: "news-research"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "07:00 (GHA) + 15:00 (VM cron)"
status: "active"
code:
  - "execution/earnings_calendar_sync.py"
reads: []
writes: []
depends_on:
  - "ext-google-workspace"
  - "ext-data-apis"
alerts: ""
---

# 실적 캘린더 sync (earnings_calendar_sync.py)

**Domain:** 뉴스 · 리서치 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 07:00 (GHA) + 15:00 (VM cron) · **Status:** active · **Project:** antigravity

Finnhub 실적 일정을 Google Calendar에 기록하는 모듈. GHA(07:00 KST)와 VM cron(15:00 KST) **양쪽에서** 실행(이중).

- 맥미니 이전 시 단일화 필요(캘린더 중복 기록 방지). 실적봇 파이프라인이 이 캘린더를 소비.
- 시크릿: FINNHUB_API_KEY, GOOGLE_SERVICE_ACCOUNT_KEY.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[ext-google-workspace]] — Google Workspace (Sheets · Calendar · Drive)
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/earnings_calendar_sync.py`
