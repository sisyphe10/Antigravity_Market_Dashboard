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
- ★**IR Day 분리(2026-07-20)**: 한 스크립트가 두 일을 하던 것을 플래그로 쪼갰다 — 캘린더 sync(146건 Google Calendar 쓰기, 느림)와 IR Day 수집(Finnhub 뉴스 315종목 + EDGAR 8-K, 느림)이 한 잡 900s 타임아웃을 함께 소진해 IR Day가 강제종료되던 문제. `--skip-ir-day`(캘린더만) / `--skip-earnings`(IR Day만)로 분리하고 맥미니 launchd에서 두 잡으로 스태거 실행(07:00 캘린더 + **07:15 IR Day**, [[launchd-gha-phase2]]의 `gha-earnings-ir-day`). 두 잡 모두 타임아웃 1800s로 상향.
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
