---
id: "store-tag-index"
name: "통합 태그 인덱스 (tag_index.sqlite + doc_tag_state.sqlite)"
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

# 통합 태그 인덱스 (tag_index.sqlite + doc_tag_state.sqlite)

**Domain:** 뉴스 · 리서치 · **Type:** Store · **Runs on:** vm_macmini · **Schedule (KST):** 23:20 (datalake-research-export) · **Status:** active · **Project:** antigravity

2026-07-29 신설. 리서치노트·어닝콜 전문·실적 분석 + 자체 보고서 4종(주간 WRAP·긴급 코멘트·월간운용보고·목표달성보고, 2026-07-31 추가)의 태그를 한 장부로 합쳐 `#태그` 즉시 검색을 뒷받침하는 **조회 전용 데이터 계층**. 각 코퍼스의 태그 정본(리서치노트=[[store-research-tags]]의 `tag_state.sqlite`)은 그대로 두고, 여기 두 파일은 거기서 파생되는 정본/인덱스다. 경로는 `~/datalake/`(레포 외부 데이터레이크, git 미추적).

- **`doc_tag_state.sqlite`** — 문서 태거([[src-research-tagging]]의 `tag_docs.py`) **정본**. 어닝콜 전문·실적 분석 + 보고서 4종(주간/코멘트/월간/목표) md를 **청크 단위**(기본 4000자)로 태깅한 테마·개체를 근거·content_hash와 함께 저장한다. 콜 전문 한 건이 4만자를 넘어 문서당 태그 하나만 붙이면 "#HBM 이 어느 대목이었나"를 잃기 때문에 청크로 쪼갠다. 리서치노트 태거(`tag_worker.py`)의 온톨로지·별칭사전·프롬프트·저장 스키마를 **그대로 재사용**해 코퍼스 간 태그 어휘를 일치시킨다. md frontmatter(themes/tickers/sectors/orgs)는 이 캐시를 읽어 재투영한 사본.
- **`tag_index.sqlite`** — **통합 조회 인덱스**([[src-research-tagging]]의 `build_tag_index.py`가 매 실행 통째 재생성). `research_notes/tag_state.sqlite`(리서치노트) + `doc_tag_state.sqlite`(전문·분석·보고서 4종)를 조인해, `#KLAC` 하나로 전 코퍼스를 한 번에 훑도록 태그→문서 히트를 미리 펼쳐 둔다. **LLM 호출이 전혀 없다** — 이미 붙은 태그를 재배열할 뿐이라 언제 몇 번을 돌려도 무료·멱등. 정규화 키(대소문자·공백 무시)로 `#태그`와 평문을 같은 키로 묶고, 스니펫·앵커(rn-id / chunk 번호)·라벨 빈도를 담는다.
- 소비: [[daemon-datalake-webui]]의 `#태그` 즉시 검색(`/tags/suggest`·`/tags/search`·`/tags/doc` + Claude가 부르는 `search_tags` 도구)이 이 인덱스만 읽는다.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-research-tagging]] — Research Notes 태깅 파이프라인 (datalake/tagging/)

## Code
- (none)
