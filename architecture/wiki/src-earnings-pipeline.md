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
- **외국 사기업(FPI) 6-K 감시(2026-07-15 확장)**: 미국 기업의 8-K와 달리 ADR·외국 발행사는 6-K로 실적을 내므로 `ticker_registry.FOREIGN_PRIVATE_ISSUERS`에 등록된 티커만 6-K 경로를 탄다. universe USD 전수 스캔(SEC submissions API)으로 활성 FPI 10종(AS·BABA·ERIC·JD·NOK·NVO·NXE·ONON·SE·SPOT)을 일괄 등록해 기존 3종(ASML·TSM·CCJ)과 합쳐 13종. 판별 기준=최신 6-K가 현행이고 최근 8-K/10-K 없음(NXPI·SATL·SHOP·SN은 8-K 전환 완료라 제외). 미등록이 곧 미수신인 구조 — ERIC Q2(6-K, 2026-07-14) 누락이 계기였다.
- **오탐 차단(2026-07-15)**: matcher는 company_name 스코어링에서 맨 티커를 제외하고 티커 언급을 word-boundary로 잡는다(타사 트랜스크립트의 인명 'Eric Mendelson'이 ERIC에 0.8로 매칭되던 HEICO 케이스 → 0.577 < 0.7). attachment_parser는 HK FF305 'Next Day Disclosure Return'·월간 자사주 매입 양식을 실적 신호 규칙보다 **먼저** `6-K_EVENT`로 분류(BABA 자사주 표의 'per share'가 `6-K_QUARTERLY`/HIGH를 유발하던 건).
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
