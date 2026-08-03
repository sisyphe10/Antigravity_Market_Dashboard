---
id: "src-notion-study"
name: "Notion Study DB 동기화 (notion_study_sync.py)"
domain: "news-research"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "23:20 (datalake-research-export)"
status: "active"
code:
  - "datalake/notion_study_sync.py"
reads: []
writes:
  - "store-notion-study-md"
depends_on:
  - "ext-notion"
  - "infra-datalake"
alerts: "동기화 실패는 warn (문서 태깅은 계속) → 텔레그램"
---

# Notion Study DB 동기화 (notion_study_sync.py)

**Domain:** 뉴스 · 리서치 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 23:20 (datalake-research-export) · **Status:** active · **Project:** antigravity

2026-08-03 신설. Notion **Study DB**(read-only, NOTION_API_KEY)를 데이터레이크 md로 증분 미러링하는 수집기. 산출 코퍼스 [[store-notion-study-md]]는 [[src-research-tagging]]의 문서 태거가 `study` kind로 태깅해 `#태그` 검색에 편입한다.

- 변경 감지 = 페이지 `last_edited_time` vs 로컬 상태(`_sync_state.json`). 변경 없는 페이지는 재요청하지 않고, 재렌더 결과가 동일하면 파일도 다시 쓰지 않는다(이미지 presigned 서명 쿼리스트링 제거 → 결정론 → 하위 재태깅 오발 없음).
- Notion REST API(`2022-06-28`), 페이스 ~3 req/s(공식 상한), 블록 트리 최대 깊이 6. 락파일(`_sync.lock`)로 중복 실행 방지.
- 삭제: 연속 2회 전체 run에서 누락된 페이지만 tombstone 이동(자동 영구삭제 없음). `--limit`(테스트 서브셋, tombstoning 안 함)·`--ids`(특정 페이지 강제 재수집) 지원. 첫 run = 전체 백필.
- 실행 위치 = [[src-research-tagging]]의 `daily_tag_export.sh`(23:20 `datalake-research-export`) 서두에서 호출 → 문서 태깅 전에 최신 md를 확보. 실패는 warn(태깅은 계속).

## Reads
- (none)

## Writes
- [[store-notion-study-md]] — Notion Study md (~/datalake/notion_study/)

## Depends on
- [[ext-notion]] — Notion (실적·리서치 퍼블리시 대상)
- [[infra-datalake]] — 맥미니 데이터레이크 (~/datalake + 문답 위키)

## Code
- `datalake/notion_study_sync.py`

## Alerts
⚠ 동기화 실패는 warn (문서 태깅은 계속) → 텔레그램
