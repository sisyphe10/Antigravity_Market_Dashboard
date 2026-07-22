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
- **KST 정렬 날짜·라벨(2026-07-22)**: 캘린더 이벤트를 미국 현지 기준이 아니라 한국시간 기준으로 배치·표기한다. 장전(bmo)=KST 당일 저녁·장중(dmh)=KST 당일 밤은 그대로, **장후(amc)만 발표가 KST 다음날 새벽이라 캘린더 날짜를 +1일 이동**. summary 접두어는 `저녁/새벽/밤`, 본문에 `발표일(미국 현지)` + `한국시간` 두 줄을 병기. 시각 미상(hour 없음) 이벤트는 `미정 |` 접두어를 붙인다. event_id(`agearn`+md5)는 미국 현지일 기준이라 불변(중복 방지 유지).
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
