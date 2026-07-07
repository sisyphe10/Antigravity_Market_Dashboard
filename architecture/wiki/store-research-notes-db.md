---
id: "store-research-notes-db"
name: "research_notes.db + media/ (리서치봇)"
domain: "news-research"
project: "antigravity"
type: "store"
runs_on: "vm_macmini"
schedule_kst: "이벤트 시"
status: "active"
code: []
reads: []
writes: []
depends_on:
  - "bot-research-notes"
alerts: ""
---

# research_notes.db + media/ (리서치봇)

**Domain:** 뉴스 · 리서치 · **Type:** Store · **Runs on:** vm_macmini · **Schedule (KST):** 이벤트 시 · **Status:** active · **Project:** antigravity

Research Notes 봇이 수신 메시지·이미지를 보관하는 SQLite + 미디어 폴더(VM 로컬, git 미추적).

- 요약→노션 퍼블리시 전 원본 보관. re-clone 시 백업 대상.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[bot-research-notes]] — Research Notes 봇

## Code
- (none)
