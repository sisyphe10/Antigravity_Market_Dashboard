---
id: "src-research-tagging"
name: "Research Notes 태깅 파이프라인 (datalake/tagging/)"
domain: "news-research"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "23:20 (datalake-research-export)"
status: "active"
code:
  - "datalake/tagging/tagging_common.py"
  - "datalake/tagging/tag_worker.py"
  - "datalake/tagging/export_tags_parquet.py"
  - "datalake/tagging/build_theme_trends.py"
  - "datalake/tagging/recompute_rules.py"
  - "datalake/tagging/tag_docs.py"
  - "datalake/tagging/build_tag_index.py"
  - "datalake/tagging/daily_tag_export.sh"
  - "datalake/tagging/ontology.json"
  - "datalake/tagging/aliases_manual.csv"
  - "datalake/tagging/entities_extra.csv"
reads:
  - "store-research-notes-db"
  - "universe_tickers.csv"
writes:
  - "store-research-tags"
  - "store-tag-index"
depends_on:
  - "infra-datalake"
  - "store-research-notes-db"
alerts: "태깅·parquet·집계 실패는 warn(아카이브는 계속) · wrapper 실패 → 텔레그램"
---

# Research Notes 태깅 파이프라인 (datalake/tagging/)

**Domain:** 뉴스 · 리서치 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 23:20 (datalake-research-export) · **Status:** active · **Project:** antigravity

2026-07-27 신설. Research Notes 원문(`research_notes.db`)에 **테마·개체(종목/섹터/기관/인물) 태그**를 붙이는 규칙+LLM 하이브리드 파이프라인. exporter([[infra-datalake]]의 `export_research_notes.py`)와 **완전히 분리된 독립 프로세스** — exporter는 매일 어제+오늘을 통째로 재생성하는 멱등 구조라 거기에 LLM을 넣으면 같은 원문에 매일 다시 과금되고 태그가 흔들린다. 그래서 태그 정본을 [[store-research-tags]]의 `tag_state.sqlite`에 두고, Markdown은 그 캐시를 읽어 투영만 한다.

- **`tagging_common.py`** — 온톨로지·개체 마스터·별칭 매칭 공용 모듈. `universe_tickers.csv`가 상장 종목 마스터의 단일 출처이고, 비상장 기업·기관·인물은 `entities_extra.csv`로 분리. 별칭은 strong/weak 2등급(strong=규칙만으로 자동 승인, weak=LLM 문맥 판정 후보). 본문 URL·도메인은 매칭 전 같은 길이 공백으로 덮어(위치 보존) 대량 오탐 차단. 마스터 해시(ontology/universe/alias)를 노출해 캐시 키에 포함.
- **`tag_worker.py`** — 태깅 워커. ① 규칙 매칭(strong 자동 승인) → ② weak 후보 + 테마 분류만 LLM(micro-batch, `TAG_MODEL` 기본 `claude-haiku-4-5`)에 위임 → ③ 근거·content_hash와 함께 `tag_state.sqlite` 저장. 인자 없이 부르면 캐시 미스(=미태깅분) 전부가 대상이라 전날 실패분도 자동 회수. `--dry-run`(비용 견적)·`--date`·`--sample`·`--retry-failed` 지원.
- **`export_tags_parquet.py`** — `tag_state.sqlite` → 연도별 parquet 3종(`research_items`·`research_item_themes`·`research_entity_mentions`)으로 내보내 데이터레이크 DuckDB 뷰로 노출.
- **`build_theme_trends.py`** — 월별 테마·섹터·종목 언급 추이 `theme_trends.json` 집계(절대건수 대신 count·share·unique_sources 3지표, primary/secondary 분리). `~/work/charts/260715_현선물공매도`의 관심축 차트가 소비.
- **`recompute_rules.py`** — 별칭 사전·규칙만 고쳤을 때 LLM 재호출 없이 규칙 기반 개체 매칭만 재계산(`rule_strong`/`rule_header` 재생성 + URL 안에서만 잡히던 개체 제거). 전량 재태깅(수 시간·수 달러) 회피용 보수 도구.

**코퍼스 확장(2026-07-29)**: 리서치노트 메시지뿐 아니라 어닝콜 전문·실적 분석 md까지 **같은 태그 어휘**로 태깅하고, 코퍼스를 한 인덱스로 합친다. **2026-07-31 확장**: `tag_docs.SOURCES`에 자체 산출 보고서 4종 — 주간 WRAP 보고(`reports/weekly`, kind=weekly)·긴급/스팟 시장 코멘트(`reports/comments`, comment)·월간운용보고서(`reports/monthly`, monthly)·목표달성보고서(`reports/target`, target) — 를 추가해 md 문서 코퍼스가 전문·분석 2종에서 **6종**으로 늘었다(리서치노트까지 통합 인덱스는 7 코퍼스). **2026-08-03 확장**: `SOURCES`에 Notion **Study DB** 미러([[store-notion-study-md]], kind=study — [[src-notion-study]]가 일일 동기화)를 더해 md 문서 코퍼스가 **7종**(리서치노트까지 통합 인덱스 8 코퍼스)이 됐다.
- **`tag_docs.py`** — md 문서 태거. 어닝콜 전문([[store-transcripts-md]])·실적 분석([[store-analyses-md]]) + 자체 보고서 4종(주간/코멘트/월간/목표) + Notion Study([[store-notion-study-md]], kind=study)를 `SOURCES` 딕셔너리로 kind별 경로 매핑. 리서치노트가 텔레그램 메시지 단위인 것과 달리, 4만자를 넘는 콜 전문을 **청크 단위**(기본 4000자)로 태깅해 "#HBM 이 어느 대목이었나"를 잃지 않는다. 온톨로지·별칭·프롬프트·저장 스키마는 `tag_worker`를 그대로 재사용하고, 정본은 [[store-tag-index]]의 `doc_tag_state.sqlite`·md frontmatter(themes/tickers/sectors/orgs)는 그 투영. `--dry-run`·`--kind`·`--max-items`·`--project`(재투영만) 지원.
- **`build_tag_index.py`** — 전 코퍼스(리서치노트·전문·분석·주간/코멘트/월간/목표 보고서·Notion Study)의 태그를 [[store-tag-index]]의 `tag_index.sqlite` 한 장부로 합치는 **통합 인덱스 빌더**. corpus 매핑 딕셔너리로 kind→라벨을 잇고 `#KLAC` 하나로 전부 훑도록 조인을 미리 펼친다. **LLM 미사용**(이미 붙은 태그 재배열)이라 무료·멱등, 매 실행 통째 재생성. [[daemon-datalake-webui]]의 `#태그` 즉시 검색 백엔드(`/tags/doc`이 `reports/` 경로도 허용).

## 일일 실행 (`daily_tag_export.sh`)

23:20 `datalake-research-export` 잡의 실체([[infra-datalake]] `run_datalake_job.sh`가 이 셸을 호출). 단계: **0 이미지 OCR([[src-research-ocr]] `ocr_worker.py`, 미처리분)** → **0b Notion Study 동기화([[src-notion-study]] `notion_study_sync.py`, 실패는 warn·계속)** → ① 태깅(미처리분) → ①b 문서 태깅(전문·분석·보고서·Study 미처리분) → ② md 아카이브(어제+오늘) → ②b 통합 태그 인덱스 재생성(LLM 미사용) → ③ parquet → ④ 추이 집계 → ⑤ 관심축 차트 빌드. **OCR·태깅을 아카이브보다 앞**에 둬 당일 md가 이미지 텍스트·태그와 함께 나오게 한다. 실패 정책: 태깅·문서 태깅·인덱스·parquet·집계가 실패해도 **원문 아카이브 생성은 반드시 진행**(아카이브가 1차 산출물, 태그는 파생물) — 아카이브 실패만 exit 1.

## Reads
- [[store-research-notes-db]] — research_notes.db + media/ (리서치봇)
- `universe_tickers.csv`

## Writes
- [[store-research-tags]] — 리서치 태그 정본 (tag_state.sqlite + theme_trends.json + parquet)
- [[store-tag-index]] — 통합 태그 인덱스 (tag_index.sqlite + doc_tag_state.sqlite)

## Depends on
- [[infra-datalake]] — 맥미니 데이터레이크 (~/datalake + 문답 위키)
- [[store-research-notes-db]] — research_notes.db + media/ (리서치봇)

## Code
- `datalake/tagging/tagging_common.py`
- `datalake/tagging/tag_worker.py`
- `datalake/tagging/export_tags_parquet.py`
- `datalake/tagging/build_theme_trends.py`
- `datalake/tagging/recompute_rules.py`
- `datalake/tagging/tag_docs.py`
- `datalake/tagging/build_tag_index.py`
- `datalake/tagging/daily_tag_export.sh`
- `datalake/tagging/ontology.json`
- `datalake/tagging/aliases_manual.csv`
- `datalake/tagging/entities_extra.csv`

## Alerts
⚠ 태깅·parquet·집계 실패는 warn(아카이브는 계속) · wrapper 실패 → 텔레그램
