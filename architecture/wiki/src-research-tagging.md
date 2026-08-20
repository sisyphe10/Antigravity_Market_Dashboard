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
  - "datalake/tagging/tagdocs_backlog_night.sh"
  - "datalake/tagging/ontology.json"
  - "datalake/tagging/aliases_manual.csv"
  - "datalake/tagging/entities_extra.csv"
  - "datalake/tagging/search_aliases.csv"
reads:
  - "store-research-notes-db"
  - "universe_tickers.csv"
writes:
  - "store-research-tags"
  - "store-tag-index"
depends_on:
  - "infra-datalake"
  - "store-research-notes-db"
  - "infra-headless-llm"
alerts: "태깅·parquet·집계 실패는 warn(아카이브는 계속) · wrapper 실패 → 텔레그램"
---

# Research Notes 태깅 파이프라인 (datalake/tagging/)

**Domain:** 뉴스 · 리서치 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 23:20 (datalake-research-export) · **Status:** active · **Project:** antigravity

2026-07-27 신설. Research Notes 원문(`research_notes.db`)에 **테마·개체(종목/섹터/기관/인물) 태그**를 붙이는 규칙+LLM 하이브리드 파이프라인. exporter([[infra-datalake]]의 `export_research_notes.py`)와 **완전히 분리된 독립 프로세스** — exporter는 매일 어제+오늘을 통째로 재생성하는 멱등 구조라 거기에 LLM을 넣으면 같은 원문에 매일 다시 과금되고 태그가 흔들린다. 그래서 태그 정본을 [[store-research-tags]]의 `tag_state.sqlite`에 두고, Markdown은 그 캐시를 읽어 투영만 한다.

- **`tagging_common.py`** — 온톨로지·개체 마스터·별칭 매칭 공용 모듈. `universe_tickers.csv`가 상장 종목 마스터의 단일 출처이고, 비상장 기업·기관·인물은 `entities_extra.csv`로 분리. 별칭은 strong/weak 2등급(strong=규칙만으로 자동 승인, weak=LLM 문맥 판정 후보). 본문 URL·도메인은 매칭 전 같은 길이 공백으로 덮어(위치 보존) 대량 오탐 차단. **캐시 키(2026-08-05 개정)**: 종전엔 universe/alias 마스터 해시를 통째로 키에 넣어 **종목 1건만 추가해도 전량 재태깅**을 유발했다(8/3 Panasonic 추가 → 3,249건 재태깅 → 야간 잡 3일 연속 타임아웃). 이를 `alias_epoch`로 대체해 **추가는 그 별칭이 등장하는 문서만 부분 재태깅**하고, 삭제·변경만 전량 무효화하도록 바꿨다(`--migrate-cache-key`로 기존 행 1회 제자리 이관).
- **`tag_worker.py`** — 태깅 워커. ① 규칙 매칭(strong 자동 승인) → ② weak 후보 + 테마 분류만 LLM(micro-batch, `TAG_MODEL` 기본 `claude-haiku-4-5`)에 위임 → ③ 근거·content_hash와 함께 `tag_state.sqlite` 저장. 인자 없이 부르면 캐시 미스(=미태깅분) 전부가 대상이라 전날 실패분도 자동 회수. `--dry-run`(비용 견적)·`--date`·`--sample`·`--retry-failed` 지원.
- **`export_tags_parquet.py`** — `tag_state.sqlite` → 연도별 parquet 3종(`research_items`·`research_item_themes`·`research_entity_mentions`)으로 내보내 데이터레이크 DuckDB 뷰로 노출.
- **`build_theme_trends.py`** — 월별 테마·섹터·종목 언급 추이 `theme_trends.json` 집계(절대건수 대신 count·share·unique_sources 3지표, primary/secondary 분리). `~/work/charts/260715_현선물공매도`의 관심축 차트가 소비.
- **`recompute_rules.py`** — 별칭 사전·규칙만 고쳤을 때 LLM 재호출 없이 규칙 기반 개체 매칭만 재계산(`rule_strong`/`rule_header` 재생성 + URL 안에서만 잡히던 개체 제거). 전량 재태깅(수 시간·수 달러) 회피용 보수 도구.

**코퍼스 확장(2026-07-29)**: 리서치노트 메시지뿐 아니라 어닝콜 전문·실적 분석 md까지 **같은 태그 어휘**로 태깅하고, 코퍼스를 한 인덱스로 합친다. **2026-07-31 확장**: `tag_docs.SOURCES`에 자체 산출 보고서 4종 — 주간 WRAP 보고(`reports/weekly`, kind=weekly)·긴급/스팟 시장 코멘트(`reports/comments`, comment)·월간운용보고서(`reports/monthly`, monthly)·목표달성보고서(`reports/target`, target) — 를 추가해 md 문서 코퍼스가 전문·분석 2종에서 **6종**으로 늘었다(리서치노트까지 통합 인덱스는 7 코퍼스). **2026-08-03 확장**: `SOURCES`에 Notion **Study DB** 미러([[store-notion-study-md]], kind=study — [[src-notion-study]]가 일일 동기화)를 더해 md 문서 코퍼스가 **7종**(리서치노트까지 통합 인덱스 8 코퍼스)이 됐다. **2026-08-07 확장**: `SOURCES`에 **외부 증권사 리포트**(`reports/research`, kind=research)를 더해 md 문서 코퍼스가 **8종**(리서치노트까지 통합 인덱스 9 코퍼스)이 됐다.
- **`tag_docs.py`** — md 문서 태거. 어닝콜 전문([[store-transcripts-md]])·실적 분석([[store-analyses-md]]) + 자체 보고서 4종(주간/코멘트/월간/목표) + Notion Study([[store-notion-study-md]], kind=study) + 외부 증권사 리포트(kind=research)를 `SOURCES` 딕셔너리로 kind별 경로 매핑. 리서치노트가 텔레그램 메시지 단위인 것과 달리, 4만자를 넘는 콜 전문을 **청크 단위**(기본 4000자)로 태깅해 "#HBM 이 어느 대목이었나"를 잃지 않는다. 온톨로지·별칭·프롬프트·저장 스키마는 `tag_worker`를 그대로 재사용하고, 정본은 [[store-tag-index]]의 `doc_tag_state.sqlite`·md frontmatter(themes/tickers/sectors/orgs)는 그 투영. `--dry-run`·`--kind`·`--max-items`·`--project`(재투영만) 지원.
  - **증권사·저자 강제 태깅(2026-08-07)**: 증권사 리포트는 frontmatter의 `broker`/`authors`를 규칙·LLM과 무관하게 개체 태그로 강제 동기화한다(`force_frontmatter_tags`, method=`fm_meta`, 멱등). `resolve_broker_entity`가 frontmatter 증권사 문자열을 `entities_extra.csv` 개체 id로 대조(별칭은 리스트일 수 있어 정규화)하고, 미등록이면 `inst:` 접두로 임시 부여. frontmatter tickers 는 종목코드에 회사명을 함께 실어 라벨 가독성을 살린다. frontmatter 메타(`fm_meta`)만 바뀐 문서는 **콘텐츠 캐시 히트라도 재투영**해 태그가 최신 frontmatter를 따라간다. 국내 잔여+해외 증권사는 `entities_extra.csv`에 2회차로 확충했고, 검색 전용 별칭은 태깅 어휘를 오염시키지 않도록 `search_aliases.csv`(신설)로 분리 — [[store-tag-index]] `#태그` 검색에서만 확장된다.
  - ★**문서 태거도 구독 headless 전환(2026-08-20)**: `tag_docs`의 LLM 호출이 종량 Anthropic API에서 **구독 headless**([[infra-headless-llm]])로 넘어갔다 — 노트 태거(`tag_worker`)가 2026-08-05에 먼저 넘어간 뒤 문서 태거만 API에 남아, 크레딧이 마르면 야간 잡이 통째로 갈리던 잔여 구멍을 메운 것. 엔진 선택은 `tag_worker`와 **같은 `TAG_ENGINE` 스위치**(기본 `headless`, 롤백=`api`)를 공유하고, 어댑터(`runtime_system`·`call_llm_headless`·`resolve_tag_model`·`build_anchor`·`EngineError`)도 그대로 재사용한다. 실행 이력은 `tag_runs.run_meta_json`에 엔진·모델·CLI 버전·anchor 해시·배치크기로 남아 **어느 백엔드가 붙인 태그인지 사후 판별**된다.
  - **폭주 가드는 문서 전용 상한으로 분리**: 청크 단위라 노트보다 대상 수가 한 자릿수 크므로 `DOC_TAG_HEADLESS_MAX_TODO`(120)·`DOC_TAG_HEADLESS_MAX_CALLS`(15)를 `TAG_HEADLESS_*`와 별도로 둔다. 상한 초과, 또는 **캐시 키 드리프트**(본문 동일·키 불일치 = 프롬프트/온톨로지/epoch가 바뀌어 전량 재태깅이 임박했다는 신호) 검출 시 **LLM 호출 0회로 정책 차단(rc 78)**. `--force`/`--migrate-cache-key`도 headless에서는 차단 — 대량 재태깅은 API 엔진 전용이다.
  - **실패 위계 = rc로 표현**: 인증 preflight(`claude auth status`, 어닝봇 8/18 패턴) 실패나 배치 중 `EngineError`(쿼터·인증·CLI 장애)는 항목을 **failed로 마킹하지 않고** 즉시 중단해 rc **75**(내일 자연 회수)로 나간다 — 마킹하면 attempts가 헛되이 소진된다. 연속 예외 조기 중단(`exc_streak` 3회)은 **API 경로 한정**으로 좁혔다. 조기 중단된 실행은 `full_pass`여도 **별칭 서명을 확정하지 않는다** — 확정하면 새 별칭이 등장하는 문서가 재태깅 없이 영구 캐시 적중이 된다(`tag_worker` engine_down과 동일 정책). 조기 중단(rc 75) 자체는 크레딧 고갈 시 문서 2,728건을 실패 배치로 계속 갈다 잡 타임아웃(rc 143)에 걸려 **뒤따르는 md 아카이브 단계까지 죽이던 사고**가 계기다(2026-08-20 오전 선행 수정).
  - **`--migrate-only`**: 드리프트 행의 키만 무LLM 제자리 이관하고 종료(별칭 서명 미확정) — headless에서도 허용(호출 0회).
- **`build_tag_index.py`** — 전 코퍼스(리서치노트·전문·분석·주간/코멘트/월간/목표 보고서·Notion Study·외부 증권사 리포트)의 태그를 [[store-tag-index]]의 `tag_index.sqlite` 한 장부로 합치는 **통합 인덱스 빌더**. corpus 매핑 딕셔너리로 kind→라벨을 잇고 `#KLAC` 하나로 전부 훑도록 조인을 미리 펼친다. **LLM 미사용**(이미 붙은 태그 재배열)이라 무료·멱등, 매 실행 통째 재생성. [[daemon-datalake-webui]]의 `#태그` 즉시 검색 백엔드(`/tags/doc`이 `reports/` 경로도 허용).

## 일일 실행 (`daily_tag_export.sh`)

23:20 `datalake-research-export` 잡의 실체([[infra-datalake]] `run_datalake_job.sh`가 이 셸을 호출). 단계: **0 이미지 OCR([[src-research-ocr]] `ocr_worker.py`, 미처리분)** → **0b Notion Study 동기화([[src-notion-study]] `notion_study_sync.py`, 실패는 warn·계속)** → ① 태깅(미처리분) → ①b 문서 태깅(전문·분석·보고서·Study 미처리분) → ② md 아카이브(어제+오늘) → ②b 통합 태그 인덱스 재생성(LLM 미사용) → ③ parquet → ④ 추이 집계 → ⑤ 관심축 차트 빌드. **OCR·태깅을 아카이브보다 앞**에 둬 당일 md가 이미지 텍스트·태그와 함께 나오게 한다. 실패 정책: 태깅·문서 태깅·인덱스·parquet·집계가 실패해도 **원문 아카이브 생성은 반드시 진행**(아카이브가 1차 산출물, 태그는 파생물) — 아카이브 실패만 exit 1.

**rc 분기(2026-08-20)**: OCR(step 0)·문서 태깅(step 1b)이 이제 성공/실패 2치가 아니라 **rc별로 갈린다** — 일반 실패(rc 1)만 재시도하고(문서 태깅은 `DOC_TAG_BATCH=4`로 배치를 줄여 `--retry-failed`), **엔진 장애(75)는 재시도 없이 warn 후 계속**(같은 쿼터·인증 벽에 다시 부딪힐 뿐, 미처리분은 다음날 자연 회수), **정책 차단(78)은 사람이 봐야 하는 신호**라 재시도 없이 warn만 남긴다. 재시도할 가치가 없는 실패에 잡 시간을 태우지 않는 것이 요지.

### 야간 백로그 회수 (`tagdocs_backlog_night.sh`, 2026-08-20 한시)
헤드리스 전환 시점에 쌓여 있던 문서 태깅 백로그(가드 상한을 크게 넘는 잔여 청크)를 **새벽 03:20 cron으로 하룻밤 1,400청크씩 잘라 회수**하는 임시 래퍼. 야간 잡 본체의 가드는 건드리지 않고 이 래퍼 안에서만 `DOC_TAG_HEADLESS_MAX_TODO/CALLS`를 올려 `--max-items`로 슬라이스한다. 03:20인 이유는 02:30 [[timer-earnings-night-llm]]과 **구독 쿼터 경합을 피하려는 시차**. `shlock` 중복 실행 방지, 단계별 rc 확인, 엔진 장애(75)·정책 차단(78)이면 cron을 유지해 익야 멱등 재시도.
- **완주 판정 후 자가 소멸**: `--dry-run`의 잔여 청크가 0이 되면 재투영 → 통합 인덱스 → parquet → 추이 집계 체인을 돌리고 **자기 crontab 항목을 marker(`tagdocs-backlog-260820`)로 제거**한다. 제거 실패는 exit 1로 드러낸다 — 한시 잡이 조용히 상주하는 것을 막는 장치.
- **연동된 알림 억제**: 백로그가 남아 있는 동안 야간 문서 태깅은 상한 가드에 걸려 **78이 뜨는 것이 정상**이라, `daily_tag_export.sh`가 crontab에 marker가 있을 때만 78 경보를 억제한다 — 억제 범위는 **문서 태깅(step 1b)의 78 한 갈래뿐**이고 노트 태깅(step 1)·OCR(step 0)의 78과 다른 rc는 그대로 경보한다. 억제 시엔 `rc=1`을 세우지 않아 잡 전체 종료코드도 오염되지 않는다. marker가 사라지는 순간 **경보가 자동 복귀**한다 — 억제 해제를 사람 기억에 맡기지 않는 배선. 억제 정책이 한 곳(marker 존재 여부)에만 있다는 점이 핵심.

## Reads
- [[store-research-notes-db]] — research_notes.db + media/ (리서치봇)
- `universe_tickers.csv`

## Writes
- [[store-research-tags]] — 리서치 태그 정본 (tag_state.sqlite + theme_trends.json + parquet)
- [[store-tag-index]] — 통합 태그 인덱스 (tag_index.sqlite + doc_tag_state.sqlite)

## Depends on
- [[infra-datalake]] — 맥미니 데이터레이크 (~/datalake + 문답 위키)
- [[store-research-notes-db]] — research_notes.db + media/ (리서치봇)
- [[infra-headless-llm]] — 구독 LLM 백엔드 (headless claude · codex 폴백)

## Code
- `datalake/tagging/tagging_common.py`
- `datalake/tagging/tag_worker.py`
- `datalake/tagging/export_tags_parquet.py`
- `datalake/tagging/build_theme_trends.py`
- `datalake/tagging/recompute_rules.py`
- `datalake/tagging/tag_docs.py`
- `datalake/tagging/build_tag_index.py`
- `datalake/tagging/daily_tag_export.sh`
- `datalake/tagging/tagdocs_backlog_night.sh`
- `datalake/tagging/ontology.json`
- `datalake/tagging/aliases_manual.csv`
- `datalake/tagging/entities_extra.csv`
- `datalake/tagging/search_aliases.csv`

## Alerts
⚠ 태깅·parquet·집계 실패는 warn(아카이브는 계속) · wrapper 실패 → 텔레그램
