---
id: "store-earnings-db"
name: "earnings.db (실적봇 상태)"
domain: "news-research"
project: "antigravity"
type: "store"
runs_on: "vm_macmini"
schedule_kst: "08:00 갱신"
status: "active"
code: []
reads: []
writes: []
depends_on:
  - "src-earnings-pipeline"
alerts: ""
---

# earnings.db (실적봇 상태)

**Domain:** 뉴스 · 리서치 · **Type:** Store · **Runs on:** vm_macmini · **Schedule (KST):** 08:00 갱신 · **Status:** active · **Project:** antigravity

실적봇 파이프라인의 상태 SQLite(~635KB). 발견한 실적/트랜스크립트, 처리·발송 상태, 종목 매칭 캐시 등.

- earnings-bot 타이머가 매일 갱신. 멱등 처리로 재발송 방지.
- 2026-07-21: `transcripts` 테이블에 `md_path`/`md_saved_at` 컬럼 추가 — 번역 전문의 datalake md 저장([[store-transcripts-md]]) 여부를 추적(구 `notion_appended_at`과 병행).

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-earnings-pipeline]] — 실적봇 파이프라인 (execution/earnings_bot/)

## Code
- (none)
