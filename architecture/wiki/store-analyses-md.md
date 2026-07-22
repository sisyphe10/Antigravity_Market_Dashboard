---
id: "store-analyses-md"
name: "실적 분석 1-page md (~/datalake/analyses/)"
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

# 실적 분석 1-page md (~/datalake/analyses/)

**Domain:** 뉴스 · 리서치 · **Type:** Store · **Runs on:** vm_macmini · **Schedule (KST):** 08:00 (earnings-bot 타이머) · **Status:** active · **Project:** antigravity

2026-07-22 신설. 실적봇이 미국 실적/IR Day를 번역·요약해 만든 **분석 1-page 시트**를 보관하는 데이터레이크 md 코퍼스. 종전엔 Notion 실적 DB 페이지로 퍼블리시했으나, 사용자 결정으로 **분석 시트의 정본은 `~/datalake/analyses/`로 전환**됐다([[store-transcripts-md]] 어닝콜 전문 전환과 동일 패턴, 2026-07-21). 기존 Notion 분석 페이지는 `backfill_analyses_md.py`로 md 백필 후 **Notion=동결 아카이브**로 남긴다([[ext-notion]]).

- 경로: `$DATALAKE_ROOT/analyses/YYYY/YYYY-MM-DD_TICKER_<accession뒤6자리>.md` (filed_at 기준 연도 파티션). 파일명에 accession 뒤 6자리를 넣어 동일 티커·동일일 복수 filing 충돌을 방지.
- 각 md는 frontmatter(ticker·filed_at·document_subtype·accession 등) + 분석 본문. 발행은 상태 DB([[store-earnings-db]])의 `stage='published'` upsert(메타 `md_path`)로 기록해 기존 dedup/다이제스트 판정을 그대로 유지.
- 생성 주체 = [[src-earnings-pipeline]]의 `analysis_store.py`(runner 6단계 `publish_pending` — 종전 `notion_publisher.publish_pending` 대체, 구 Notion 코드는 롤백용 잔존). CLI `backfill_analyses_md.py`로 기존 Notion 분석분 소급 생성 가능.
- 소비: [[daemon-datalake-webui]]가 `analyses`를 SEARCH_ROOTS + Earnings Library(`/library`)에 등록 → AoE 'Wiki' 자연어 문답 검색 및 'Earnings' 탭 열람(transcripts와 함께).

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-earnings-pipeline]] — 실적봇 파이프라인 (execution/earnings_bot/)

## Code
- (none)
