---
id: "store-transcripts-md"
name: "어닝콜 번역 전문 md (~/datalake/transcripts/)"
domain: "news-research"
project: "antigravity"
type: "store"
runs_on: "vm_macmini"
schedule_kst: "08:00 (earnings-bot 타이머)"
status: "active"
code: []
reads: []
writes: []
depends_on:
  - "src-earnings-pipeline"
alerts: ""
---

# 어닝콜 번역 전문 md (~/datalake/transcripts/)

**Domain:** 뉴스 · 리서치 · **Type:** Store · **Runs on:** vm_macmini · **Schedule (KST):** 08:00 (earnings-bot 타이머) · **Status:** active · **Project:** antigravity

2026-07-21 신설. 실적봇이 번역 완료한 미국 유니버스 종목 컨퍼런스콜 전문(한국어)을 보관하는 데이터레이크 md 코퍼스. 종전엔 Notion 페이지에 append 했으나, 사용자 결정으로 **transcript 본문은 Notion 미접촉·`~/datalake/transcripts/`가 정본**으로 전환됐다(기존 Notion 발행분은 아카이브로 유지).

- 경로: `$DATALAKE_ROOT/transcripts/YYYY/YYYY-MM-DD_TICKER_<accession뒤6자리>.md` (filed_at 기준 연도 파티션). 파일명에 accession 뒤 6자리를 넣어 동일 티커·동일일 복수 filing/복수 소스 충돌을 방지.
- 각 md는 frontmatter(ticker·filed_at·fiscal·accession·source·match_confidence·translation_model 등) + 한국어 번역 본문 + 원문 출처 각주.
- 생성 주체 = [[src-earnings-pipeline]]의 `transcript_store.py`(runner 7단계 `save_pending`). 상태 DB([[store-earnings-db]])의 `md_path`/`md_saved_at` 컬럼으로 저장 여부를 추적(멱등). CLI `transcript_store --backfill`로 번역 전건 소급 생성 가능.
- 소비: [[daemon-datalake-webui]]가 `transcripts`를 SEARCH_ROOTS에 등록 → AoE 'Wiki' 탭 자연어 문답에서 검색·읽기(긴 파일은 read_file offset 페이징).

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-earnings-pipeline]] — 실적봇 파이프라인 (execution/earnings_bot/)

## Code
- (none)
