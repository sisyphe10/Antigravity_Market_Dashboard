---
id: "store-notion-study-md"
name: "Notion Study md (~/datalake/notion_study/)"
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
  - "src-notion-study"
alerts: ""
---

# Notion Study md (~/datalake/notion_study/)

**Domain:** 뉴스 · 리서치 · **Type:** Store · **Runs on:** vm_macmini · **Schedule (KST):** 23:20 (datalake-research-export) · **Status:** active · **Project:** antigravity

2026-08-03 신설. 사용자의 Notion **Study DB**(학습 노트)를 데이터레이크 md로 미러링한 코퍼스. [[src-notion-study]]가 증분 동기화로 채우고, 태깅 파이프라인의 `#태그` 검색이 `study` 코퍼스로 소비한다.

- 경로: `~/datalake/notion_study/<year>/<page_id>.md` + 상태 `_sync_state.json`(id→last_edited/path/sha). 이미지 presigned 쿼리스트링은 렌더 전 제거해 결정론 유지(다운스트림 재태깅 오발 방지).
- 삭제 처리: 연속 2회 전체 run에서 사라진 페이지만 `~/datalake/_tombstones/notion_study/`로 이동(자동 영구삭제 없음).
- 소비: [[src-research-tagging]]의 `tag_docs.py`가 `SOURCES["study"] = notion_study`로 kind별 매핑해 md 문서 태거 코퍼스에 편입 → [[store-tag-index]] 통합 인덱스에서 `#태그` 검색.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-notion-study]] — Notion Study DB 동기화 (notion_study_sync.py)

## Code
- (none)
