---
id: "bot-research-notes"
name: "Research Notes 봇"
domain: "news-research"
project: "antigravity"
type: "bot"
runs_on: "vm_macmini"
schedule_kst: "상시 (이벤트 드리븐)"
status: "active"
code:
  - "execution/research_bot/research_notes_bot.py"
  - "execution/research_bot/summarizer.py"
  - "execution/research_bot/notion_publisher.py"
  - "scripts/research-notes-bot.service"
reads: []
writes:
  - "store-research-notes-db"
  - "research_headlines.json"
depends_on:
  - "ext-notion"
  - "infra-telegram"
alerts: "OnFailure → notify_sisyphe_failure.sh research-notes-bot → 텔레그램"
---

# Research Notes 봇

**Domain:** 뉴스 · 리서치 · **Type:** Bot · **Runs on:** vm_macmini · **Schedule (KST):** 상시 (이벤트 드리븐) · **Status:** active · **Project:** antigravity

텔레그램으로 들어온 리서치 메시지(텍스트+이미지)를 Haiku로 상세 요약해 노션에 퍼블리시하는 봇(`execution/research_bot/research_notes_bot.py`).

- 요약 규칙: 토픽별 불릿 8~12개+, 이미 불릿이면 원문 유지, 모든 이미지 첨부, 엄중/중요 표시는 {RED} 태그→노션 빨간색.
- 메시지·미디어는 로컬 SQLite(`research_notes.db`) + `media/`에 보관 후 노션 페이지로.
- RA_Sisyphe_bot의 05:10 헤드라인이 이 봇이 쌓은 `research_headlines.json`을 읽어 아침 요약을 만든다.

## Reads
- (none)

## Writes
- [[store-research-notes-db]] — research_notes.db + media/ (리서치봇)
- `research_headlines.json`

## Depends on
- [[ext-notion]] — Notion (실적·리서치 퍼블리시 대상)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `execution/research_bot/research_notes_bot.py`
- `execution/research_bot/summarizer.py`
- `execution/research_bot/notion_publisher.py`
- `scripts/research-notes-bot.service`

## Alerts
⚠ OnFailure → notify_sisyphe_failure.sh research-notes-bot → 텔레그램
