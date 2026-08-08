---
id: "daemon-datalake-webui"
name: "데이터레이크 문답 웹 UI 데몬 (AoE Wiki, 127.0.0.1:8787)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "vm_macmini"
schedule_kst: "상시"
status: "active"
code:
  - "datalake/launchd/com.antigravity.datalake-webui.plist"
  - "datalake/launchd/com.antigravity.datalake-wiki-model.plist"
  - "datalake/webui/run_webui.sh"
  - "datalake/webui/server.py"
  - "datalake/webui/headless_backend.py"
  - "datalake/webui/wiki_mcp.py"
  - "datalake/webui/wiki_tools.py"
  - "datalake/webui/wiki_jobs.py"
  - "datalake/webui/wiki_model.py"
  - "datalake/webui/wiki_system_prompt.md"
reads:
  - "infra-datalake"
  - "store-transcripts-md"
  - "store-analyses-md"
  - "store-tag-index"
  - "store-news-md"
writes: []
depends_on:
  - "infra-vm-macmini"
  - "infra-datalake"
alerts: "KeepAlive=true (launchd 자동 재기동, ThrottleInterval=15)"
---

# 데이터레이크 문답 웹 UI 데몬 (AoE Wiki, 127.0.0.1:8787)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** vm_macmini · **Schedule (KST):** 상시 · **Status:** active · **Project:** antigravity

2026-07-12 신설. 데이터레이크의 DuckDB+Claude 자연어 문답 UI를 **상시 데몬**으로 띄우는 launchd 서비스(2026-08-05 백엔드를 구독 쿼터 headless Claude Code로 전환 — 아래 참조)(`com.antigravity.datalake-webui`, RunAtLoad + KeepAlive). 기존 수동 기동(`run_webui.sh`)을 데몬화해, ts.net 대시보드의 'Wiki' 탭 백엔드로 상주시킨다.

- 바인딩: FastAPI 서버(`server.py`)가 `127.0.0.1:8787` 루프백 고정 — 직접 공개 노출 없음. Caddy가 `/wiki/*`를 이 포트로 리버스 프록시([[web-caddy]]) → AoE 'Wiki'·'Earnings' 탭.
- 질의 대상 = 데이터레이크 md 코퍼스 + duckdb 샌드박스(allowed→잠금). 소스·설계 상세는 [[infra-datalake]] / `datalake/DESIGN.md`.
- **코퍼스 확장(2026-07-21)**: SEARCH_ROOTS에 `transcripts`(어닝콜 한국어 번역 전문, [[store-transcripts-md]])를 추가하고 시스템 프롬프트에 어닝콜 전문 소스를 명시. 긴 전문 대응으로 `read_file`에 offset 페이징(1회 최대 20000자, `(truncated ... offset=)` 안내)을 도입.
- **Earnings Library + analyses 코퍼스(2026-07-22)**: SEARCH_ROOTS에 `analyses`(실적 분석 1-page, [[store-analyses-md]])를 추가하고, 별도 열람 UI 엔드포인트 `/library`(+`/library/list`·`/library/doc`)를 신설. transcripts+analyses md를 필터·프론트매터·md 렌더로 보여주는 'Earnings Library' 페이지(터미널 블랙+앰버)로, ts.net `/wiki/library`에 리버스 프록시되고 nav 'Earnings' 탭이 여기를 가리킨다. 실적봇의 Notion 분석 퍼블리시가 md 발행으로 대체되며([[src-earnings-pipeline]]) 이 UI가 Notion 열람을 대신한다.
- **통합 `#태그` 즉시 검색 + 서버측 대화 이력(2026-07-29)**: [[store-tag-index]]의 `tag_index.sqlite`를 읽어 `#KLAC` 한 번으로 리서치노트·어닝콜 전문·실적 분석 세 코퍼스를 훑는 즉시 검색을 추가(`/tags/suggest`·`/tags/search`·`/tags/doc` 엔드포인트 + Claude가 부르는 `search_tags` 도구, **LLM 미사용**이라 무료). 동시에 문답 채팅을 **리서치 애널리스트 페르소나**(결론 우선·사실/추정 구분·비교 기준 명시) 시스템 프롬프트로 바꾸고, 서버측 대화 이력 사이드바·thinking 인디케이터·답변을 그 대화에 고정(pin)·저장/삭제 실패 노출을 도입. publish 훅은 root가 아니라 레포 소유자로 실행하도록 고쳤다.
- **답변기 견고성·계측(2026-08-04)**: 도구 예산 소진 시 수집한 근거를 버리고 무응답으로 끝나던 문제를 없앴다 — 툴 루프 상한 `MAX_LOOP` 12→20으로 늘리고, 소진 시 `tool_choice=none` 강제 최종 호출로 지금까지 모은 근거로 답을 마무리(dead-end 금지). 동시에 대화 이력에 롤링 `cache_control` breakpoint를 얹어(종전엔 시스템 프롬프트만 캐시) 다턴 재전송 비용을 낮추고, 턴별 usage 집계로 질문당 비용($)·캐시 히트율을 로그·응답에 실었다.
- ★**headless 백엔드 전환·라이브(2026-08-05, 호출당 과금 0원)**: `/wiki` 문답을 Anthropic **API 루프에서 구독 쿼터의 Claude Code CLI(headless)로 이관**하고, 롤백 여지 없이 **API 경로를 완전히 제거**(제로 코스트가 구조적으로 확정). 새 `headless_backend.py`가 CLI를 `stream-json`으로 몰아 API 루프와 동일한 `{answer, steps[]}` 계약을 유지한다. 도구는 **MCP 3종(`run_sql`·`search_notes`·`search_tags`, `wiki_mcp.py`+`wiki_tools.py`) + 네이티브 Read/Glob**만 허용하고 쓰기·실행·웹 계열은 allow/deny 양쪽으로 차단. 코퍼스 SEARCH_ROOTS에 `news`([[store-news-md]])가 추가됐다.
  - **모델 자동 추종**(`wiki_model.py`, 464f5c6e): CLI `--model opus` 별칭이 실측상 뒤처져서(별칭이 구 Opus를 가리킴) 하드코딩 대신 **상위 메이저를 직접 탐침해 더 새 Opus를 고른다**(Fable/Mythos는 사용자 지시로 제외, 탐침 결과 24h 캐시). 별칭·탐침 양쪽을 봐 CLI가 나중에 별칭을 고치면 자동 수렴. CLI 버전 변화는 핀 대신 **headless 계약을 검증**(`wiki_smoke.py`).
  - **모델 탐침 프리웜 잡**(`com.antigravity.datalake-wiki-model.plist`, 04:40 KST 매일): 캐시 만료 후 첫 질문이 탐침 ~20초를 떠안지 않도록 새벽에 미리 최신 Opus를 갱신. `run_datalake_job.sh datalake-wiki-model`.
  - **비동기 잡 엔드포인트 + A/B**(`wiki_jobs.py`, 2d54e8b7·abb0ff8a): 긴 headless 질의를 async job으로 돌리고, headless↔API 답을 나란히 비교하는 A/B eval harness(`ab_eval.py`)와 대조 페이지(`/wiki/test/headless/ab`)를 붙였다. duckdb 샌드박스 `allowed_directories` 보강·큐 무음 종료 방지(codex 리뷰 P0/P1).
  - ★**실패 사유 계측(2026-08-08)**: CLI가 **인증 만료 같은 실패에서도 `result.subtype='success'`를 돌려주는 것**이 실측돼(8/8 인증 만료 사고), 그 값을 그대로 쓰면 실패 알림 사유가 문자 그대로 "success"가 되어 정보량이 0이었다. `headless_backend.py`가 `subtype=='success'`면 `result_error`로 대체하고, **응답 본문 첫 줄(300자)을 사유에 덧붙여** 코드값만으로 못 읽던 원인을 알림에 싣는다([[infra-telegram]]의 `DETAIL` 인자와 짝). 같은 날 인증 만료 자체의 사전 경고는 [[daemon-daily-selfcheck]]가 맡게 됐다 — CLI가 인증 실패에도 exit 0이라 rc 감시로는 이 데몬의 무응답을 잡을 수 없다.
  - ★라우트는 `server.py`의 `__main__` 앞에 등록해야 하고, `index.html` 수정은 한 체인에서 커밋한다(스냅숏 미경유 사본 — 아래 참조).
- ★**nav는 손으로 맞춰야 하는 사본**(`datalake/webui/static/index.html`): 이 페이지는 스냅숏이 아니라 데몬에서 직접 서빙되므로 [[web-publish-snapshot]]의 `compose_personal_view.py` nav 주입이 **닿지 않는다**. 2026-07-16 nav 개편 때 [[daemon-watchlist-quoteboard]]와 함께 이 파일의 topnav 마크업을 따로 고쳐 통일했다(`Wiki` 탭에 `margin-left:auto`를 줘 Wiki·Architecture를 우측 그룹으로 미는 것도 여기 사본에 직접 박혀 있다). 2026-07-18 브랜드 라벨을 `AoE` → `AGE OF EMERGENCE`로 확장할 때도 이 사본을 손으로 맞췄다([[web-publish-snapshot]]). 2026-07-22 nav 재편(좌 Watchlist·Market·Journal·Weekly·Earnings·Wiki / 우 Memento·Ledger·Architecture)과 'Earnings'(`/wiki/library`) 탭 추가도 이 사본에 직접 반영했다.
- launchd 관리: `ThrottleInterval=15`로 크래시 루프 억제, 로그는 `logs/launchd/datalake-webui.{out,err}`. 계산 잡 아님(catch-up 대상 아님).

## Reads
- [[infra-datalake]] — 맥미니 데이터레이크 (~/datalake + 문답 위키)
- [[store-transcripts-md]] — 어닝콜 번역 전문 md (~/datalake/transcripts/)
- [[store-analyses-md]] — 실적 분석 1-page md (~/datalake/analyses/)
- [[store-tag-index]] — 통합 태그 인덱스 (tag_index.sqlite + doc_tag_state.sqlite)
- [[store-news-md]] — 뉴스 소스 아카이브 md (~/datalake/news/)

## Writes
- (none)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (맥미니)
- [[infra-datalake]] — 맥미니 데이터레이크 (~/datalake + 문답 위키)

## Code
- `datalake/launchd/com.antigravity.datalake-webui.plist`
- `datalake/launchd/com.antigravity.datalake-wiki-model.plist`
- `datalake/webui/run_webui.sh`
- `datalake/webui/server.py`
- `datalake/webui/headless_backend.py`
- `datalake/webui/wiki_mcp.py`
- `datalake/webui/wiki_tools.py`
- `datalake/webui/wiki_jobs.py`
- `datalake/webui/wiki_model.py`
- `datalake/webui/wiki_system_prompt.md`

## Alerts
⚠ KeepAlive=true (launchd 자동 재기동, ThrottleInterval=15)
