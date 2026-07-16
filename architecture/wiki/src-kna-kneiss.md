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
- 2026-07-16 **첨부 전용 글 오판 수정**: 본문 없이 이미지+PDF 첨부로만 올라온 월간 미국시장 요약(#7919)을 파서가 페이월로 오인해 엉뚱한 '로그인 실패' 안내를 보냈다. 이제 `news_view`에 img/첨부가 있으면 페이월이 아닌 것으로 보고, **PDF 첨부는 내려받아 pypdf로 텍스트를 추출**해 본문으로 쓴다.

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
