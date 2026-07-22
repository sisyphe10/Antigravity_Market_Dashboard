---
id: "ext-notion"
name: "Notion (실적·리서치 퍼블리시 대상)"
domain: "news-research"
project: "antigravity"
type: "external"
runs_on: "external"
schedule_kst: ""
status: "active"
code:
  - "execution/earnings_bot/notion_publisher.py"
  - "execution/research_bot/notion_publisher.py"
reads: []
writes: []
depends_on: []
alerts: ""
---

# Notion (실적·리서치 퍼블리시 대상)

**Domain:** 뉴스 · 리서치 · **Type:** External · **Runs on:** external · **Status:** active · **Project:** antigravity

리서치노트봇이 요약 결과를 퍼블리시하는 노션 워크스페이스(NOTION_API_KEY / NOTION_EARNINGS_DATABASE_ID 등). 실적봇에겐 **동결 아카이브**다.

- 실적봇: ~~번역·요약된 미국 실적/IR Day 노트를 실적 DB에 페이지로 생성~~ → **2026-07-22 datalake md 발행으로 대체**됐다. 분석 1-page는 [[store-analyses-md]](`~/datalake/analyses/`), 어닝콜 전문은 [[store-transcripts-md]](2026-07-21)가 정본이며, 기존 Notion 분석 페이지는 `backfill_analyses_md.py`로 md 백필 후 Notion은 동결 아카이브로 남는다(구 `notion_publisher.py`는 롤백용 잔존). [[src-earnings-pipeline]] 참조.
- 리서치노트봇: 텔레그램 리서치 메시지를 요약→노션 페이지(엄중/중요 표시는 빨간색 텍스트) — 계속 활성.
- 이미지는 GitHub에 올린 뒤 URL로 삽입.

## Reads
- (none)

## Writes
- (none)

## Depends on
- (none)

## Code
- `execution/earnings_bot/notion_publisher.py`
- `execution/research_bot/notion_publisher.py`
