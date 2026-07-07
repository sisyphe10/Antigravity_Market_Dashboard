---
id: "src-kna-kneiss"
name: "원전 뉴스 KNA/KNEISS (sources/kna.py)"
domain: "news-research"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "18:00 (ra-sisyphe)"
status: "active"
code:
  - "execution/sources/kna.py"
  - "execution/fetch_kneiss_news.py"
reads:
  - "store-sources-state"
writes:
  - "store-sources-state"
depends_on:
  - "src-generic-pipeline"
  - "infra-telegram"
alerts: ""
---

# 원전 뉴스 KNA/KNEISS (sources/kna.py)

**Domain:** 뉴스 · 리서치 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 18:00 (ra-sisyphe) · **Status:** active · **Project:** antigravity

세계 원전시장동향 신규 게시글을 폴링해 텔레그램 발송(18:00 KST).

- 소스 k-neiss.org 회원게시판 전환(폼 로그인 KNEISS_ID/PW, 클라우드IP OK). fetcher는 `fetch_kneiss_news.py`.
- 구 `fetch_kna_news.py`는 롤백 보존이었으나 origin에서 삭제됨(dead code 정리). 마지막 본 글 ID는 `kna_state.json`.

## Reads
- [[store-sources-state]] — sources_state/ + kna_state.json

## Writes
- [[store-sources-state]] — sources_state/ + kna_state.json

## Depends on
- [[src-generic-pipeline]] — Generic Source Pipeline (execution/sources/)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `execution/sources/kna.py`
- `execution/fetch_kneiss_news.py`
