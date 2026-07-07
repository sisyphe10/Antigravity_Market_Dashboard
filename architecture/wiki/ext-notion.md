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

실적봇과 리서치노트봇이 요약 결과를 퍼블리시하는 노션 워크스페이스(NOTION_API_KEY / NOTION_EARNINGS_DATABASE_ID 등).

- 실적봇: 번역·요약된 미국 실적/IR Day 노트를 실적 DB에 페이지로 생성.
- 리서치노트봇: 텔레그램 리서치 메시지를 요약→노션 페이지(엄중/중요 표시는 빨간색 텍스트).
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
