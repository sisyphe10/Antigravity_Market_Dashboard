---
id: "store-research-tags"
name: "리서치 태그 정본 (tag_state.sqlite + theme_trends.json + parquet)"
domain: "news-research"
project: "antigravity"
type: "store"
runs_on: "vm_macmini"
schedule_kst: "23:20 (datalake-research-export)"
status: "active"
code: []
reads: []
writes: []
depends_on:
  - "src-research-tagging"
alerts: ""
---

# 리서치 태그 정본 (tag_state.sqlite + theme_trends.json + parquet)

**Domain:** 뉴스 · 리서치 · **Type:** Store · **Runs on:** vm_macmini · **Schedule (KST):** 23:20 (datalake-research-export) · **Status:** active · **Project:** antigravity

2026-07-27 신설. Research Notes 원문에 붙인 테마·개체 태그의 데이터 계층. **정본은 `tag_state.sqlite` 하나**이고, parquet·JSON·Markdown 태그는 전부 여기서 파생되는 투영이다. 경로는 `~/datalake/research_notes/`(레포 외부 데이터레이크, git 미추적).

- **`tag_state.sqlite`** — 태그 정본. 메시지별 테마 배정·개체 언급을 근거(surface/문자위치·method·confidence·rank)와 함께 저장. 캐시 키 = `message_id + content_hash + tagger_version + prompt_hash + ontology_hash + universe_hash + alias_hash` → 원문·마스터가 안 바뀌면 LLM 재호출 없음.
- **연도 파티션 parquet**(`market/<name>/<year>.parquet`, DuckDB 뷰 등록) — `research_items`(메시지 1행: 날짜·출처채널·유형·길이·테마 수) · `research_item_themes`(메시지×테마: rank/confidence/evidence) · `research_entity_mentions`(메시지×개체: role/method/섹터/표면형). 기계 질의는 여기를 본다.
- **`theme_trends.json`** — 월별 테마·섹터·종목 언급 추이(count·share·unique_sources, primary/secondary 분리). `~/work/charts/260715_현선물공매도`의 관심축 차트가 소비.
- Markdown 코퍼스([[store-transcripts-md]]와 나란한 `~/datalake/research_notes/*.md`)의 태그 줄은 [[src-research-tagging]]가 이 캐시를 읽어 투영한 것 — 사람이 읽는 표시일 뿐 기계 질의 대상 아님.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-research-tagging]] — Research Notes 태깅 파이프라인 (datalake/tagging/)

## Code
- (none)
