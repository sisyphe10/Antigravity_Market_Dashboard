---
id: "src-earnings-pipeline"
name: "실적봇 파이프라인 (execution/earnings_bot/)"
domain: "news-research"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "08:00 (earnings-bot 타이머)"
status: "active"
code:
  - "execution/earnings_bot/runner.py"
  - "execution/earnings_bot/morning_digest.py"
  - "execution/earnings_bot/edgar_monitor.py"
  - "execution/earnings_bot/transcript_watch.py"
  - "execution/earnings_bot/notion_publisher.py"
reads:
  - "store-earnings-db"
writes:
  - "store-earnings-db"
depends_on:
  - "src-earnings-calendar-sync"
  - "ext-notion"
  - "ext-data-apis"
  - "infra-telegram"
alerts: "타이머 OnFailure → 텔레그램"
---

# 실적봇 파이프라인 (execution/earnings_bot/)

**Domain:** 뉴스 · 리서치 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 08:00 (earnings-bot 타이머) · **Status:** active · **Project:** antigravity

미국 실적/IR Day를 번역·요약해 노션 퍼블리시 + 아침 다이제스트를 만드는 다단 파이프라인(`earnings_bot.runner`).

- 단계: 캘린더 sync → EDGAR/트랜스크립트 감시(edgar_monitor/transcript_watch) → 종목 매칭(matcher/ticker_registry) → YoY 계산 → 프롬프트 빌드→번역(Claude) → 노션 퍼블리시 → morning_digest.
- 상태 DB=`earnings.db`. 예정 포맷=`티커/발표일자`(기업명 없음 확정). `--dismiss` CLI.
- 캘린더는 `gha-earnings-calendar-sync`가 채우고 이 파이프라인이 소비.

## Reads
- [[store-earnings-db]] — earnings.db (실적봇 상태)

## Writes
- [[store-earnings-db]] — earnings.db (실적봇 상태)

## Depends on
- [[src-earnings-calendar-sync]] — 실적 캘린더 sync (earnings_calendar_sync.py)
- [[ext-notion]] — Notion (실적·리서치 퍼블리시 대상)
- [[ext-data-apis]] — 외부 데이터 API/소스 집합
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `execution/earnings_bot/runner.py`
- `execution/earnings_bot/morning_digest.py`
- `execution/earnings_bot/edgar_monitor.py`
- `execution/earnings_bot/transcript_watch.py`
- `execution/earnings_bot/notion_publisher.py`

## Alerts
⚠ 타이머 OnFailure → 텔레그램
