---
id: "src-earnings-pipeline"
name: "실적봇 파이프라인 (execution/earnings_bot/)"
domain: "news-research"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "02:30 (night-llm 배치) + 08:00 (earnings-bot 타이머)"
status: "active"
code:
  - "execution/earnings_bot/runner.py"
  - "execution/earnings_bot/night_llm.py"
  - "execution/earnings_bot/headless_llm.py"
  - "execution/earnings_bot/morning_digest.py"
  - "execution/earnings_bot/edgar_monitor.py"
  - "execution/earnings_bot/transcript_watch.py"
  - "execution/earnings_bot/transcript_sources/search_provider.py"
  - "execution/earnings_bot/transcript_gate.py"
  - "execution/earnings_bot/prompt_builder.py"
  - "execution/earnings_bot/translator.py"
  - "execution/earnings_bot/ticker_registry.py"
  - "execution/earnings_bot/cli/transcript_override.py"
  - "execution/earnings_bot/notion_publisher.py"
  - "execution/earnings_bot/transcript_store.py"
  - "execution/earnings_bot/analysis_store.py"
  - "execution/earnings_bot/backfill_analyses_md.py"
reads:
  - "store-earnings-db"
writes:
  - "store-earnings-db"
  - "store-transcripts-md"
  - "store-analyses-md"
depends_on:
  - "src-earnings-calendar-sync"
  - "infra-headless-llm"
  - "ext-notion"
  - "ext-data-apis"
  - "infra-telegram"
alerts: "타이머 OnFailure → 텔레그램"
---

# 실적봇 파이프라인 (execution/earnings_bot/)

**Domain:** 뉴스 · 리서치 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 02:30 (night-llm 배치) + 08:00 (earnings-bot 타이머) · **Status:** active · **Project:** antigravity

미국 실적/IR Day를 번역·요약해 datalake md로 발행 + 아침 다이제스트를 만드는 다단 파이프라인(`earnings_bot.runner`).

- 단계: 캘린더 sync → EDGAR/트랜스크립트 감시(edgar_monitor/transcript_watch) → 종목 매칭(matcher/ticker_registry) → YoY 계산 → 프롬프트 빌드→번역(Claude) → **분석 1-page md 발행(analysis_store)** → **번역 전문 datalake md 저장(transcript_store)** → morning_digest.
- **분석 발행처 전환(2026-07-22)**: runner 6단계가 종전 `notion_publisher.publish_pending`(Notion 실적 DB 페이지 생성)에서 `analysis_store.publish_pending`으로 교체됐다. 분석 1-page 시트는 이제 [[store-analyses-md]](`~/datalake/analyses/YYYY/`)에 정본으로 발행된다(구 Notion 코드는 롤백용 잔존). 발행은 earnings.db `stage='published'` upsert(메타 `md_path`)로 기록해 dedup/다이제스트 판정을 유지한다. `backfill_analyses_md.py`로 기존 Notion 분석 페이지를 md 백필했고 [[ext-notion]]은 동결 아카이브로 남는다. 발행된 md는 [[daemon-datalake-webui]] Earnings Library(`/library`)·문답 코퍼스로 열람·검색된다.
- **transcript 본문 저장처 전환(2026-07-21)**: runner 7단계가 종전 `notion_publisher.append_pending_translations`(Notion 페이지 append)에서 `transcript_store.save_pending`으로 교체됐다. 번역 완료 어닝콜 전문은 이제 [[store-transcripts-md]](`~/datalake/transcripts/YYYY/`)에 정본으로 저장된다(구 Notion append 코드는 롤백용 잔존). 저장 여부는 earnings.db `md_path`/`md_saved_at` 컬럼으로 추적하며, morning_digest의 🟢 완료 신호도 `notion_appended_at OR md_saved_at`로 확장됐다. 저장된 md는 [[daemon-datalake-webui]] 코퍼스로 검색된다.
- **외국 사기업(FPI) 6-K 감시(2026-07-15 확장)**: 미국 기업의 8-K와 달리 ADR·외국 발행사는 6-K로 실적을 내므로 `ticker_registry.FOREIGN_PRIVATE_ISSUERS`에 등록된 티커만 6-K 경로를 탄다. universe USD 전수 스캔(SEC submissions API)으로 활성 FPI 10종(AS·BABA·ERIC·JD·NOK·NVO·NXE·ONON·SE·SPOT)을 일괄 등록해 기존 3종(ASML·TSM·CCJ)과 합쳐 13종. 판별 기준=최신 6-K가 현행이고 최근 8-K/10-K 없음(NXPI·SATL·SHOP·SN은 8-K 전환 완료라 제외). 미등록이 곧 미수신인 구조 — ERIC Q2(6-K, 2026-07-14) 누락이 계기였다. **2026-07-30 ARM(Arm Holdings plc, GB, 20-F/6-K 전용·8-K/10-K 이력 전무) 추가로 14종** — 미등록으로 1Q27 6-K 누락 확인이 계기. **2026-07-31 universe USD 316 전수 재스캔으로 6-K 전용 5종(CCEP·FER·NBIS·PDD·TRI) 추가 → 19종.**
- **전문 오매칭·날조 하드 게이트(2026-07-31 사고 대응, `transcript_gate.py`)**: matcher의 5점수(회사명·티커·분기표현·날짜·키워드)에는 "이 문서가 실제 발화 기록인가"를 재는 항목이 없어, 가이던스 예고 기사가 제목만으로 0.80을 얻어 임계값 0.70을 통과 → 기사/요약페이지가 전문으로 수집(22건)되고 소스가 올해 전문을 안 올렸을 땐 **작년 같은 분기 전문**이 대신 수집(11건)됐다. 한 건은 프롬프트에 "전문이 아닐 때" 지시가 없어 **CEO 발언을 날조**(IBM id=134)했다. 이제 점수(soft)가 아닌 **하드 veto** — 원문 길이(`MIN_RAW_CHARS`, 정상 153건 최솟값 21,237자 기준으로 18,000 출발 → 2026-08-17 15,000 하향)·URL 블록리스트/날짜 허용오차·본문 빈티지(공시월 ±4개월)·번역/원문 길이비(하드 0.12·경고 0.30)·숫자 정합성을 통과 못 하면 수집·번역·발행 어느 단계도 진행하지 않는다("못 구한 것"은 빈칸, "만들어낸 것"은 안 남긴다). 청크별 sentinel 검증·독립 ground truth 대조, 프롬프트 stub 섹션 차단, 다이제스트에 `gate_blocked` 노출, override CLI(`cli/transcript_override.py`)에도 게이트 적용.
- **게이트 길이 임계 하향 18,000 → 15,000(2026-08-17)**: 소형주는 어닝콜 자체가 짧을 수 있어 정상 전문(LTBR 2Q26, 17,205자·발화 구조 정상)이 `raw_too_short`로 하드 차단됐다. 2026-07-31 캘리브레이션에서 의심 46건 중 41건이 14,816자 이하였으므로 15,000으로 내려도 차단 커버리지는 동일하게 유지된다. 전문 266건 회귀에서 false-pass 0건·신규 false-block 0건 확인. 게이트의 나머지 항목(URL·빈티지·길이비·숫자 정합성)은 불변 — 길이는 **가장 거친 1차 필터**일 뿐이고 오염 차단의 실질은 뒤 항목들이 맡는다는 설계가 유지된다.
- **번역 큐 관심종목 한정(2026-07-31)**: 전문은 universe 전수 수집하되 **번역은 별표(`universe_stars_v1`) 종목만** — 하루 3건 상한에서 관심 없는 종목이 3주치 백로그를 쌓던 문제. `prefs.json` 미판독 시 fail-open(전량 번역). 게이트 차단 백로그 59건은 사용자 결정으로 `gave_up` 종결(과거 누락은 빈칸, 재시도 폭주 없음).
- **다이제스트 별표 한정(2026-08-10)**: morning_digest의 **전 섹션**(신규·재시도·보류·게이트 격리·예정)을 별표(`universe_stars_v1`) 종목만 표시하도록 좁혔다 — 번역 큐에 이어 열람 면까지 관심종목 기준으로 통일. `prefs.json` 로드 실패 시 전 종목 폴백(fail-open) — 이때 폴백이 조용히 일어나지 않도록 **다이제스트 제목의 `★별표만` 태그가 사라지는 것**으로 필터 적용 여부를 드러낸다. 필터 후에도 표시분을 확보하려고 조회 SQL LIMIT을 20→200으로 올렸다(표시 상한이 아니라 필터 전 후보 풀).
- **오탐 차단(2026-07-15)**: matcher는 company_name 스코어링에서 맨 티커를 제외하고 티커 언급을 word-boundary로 잡는다(타사 트랜스크립트의 인명 'Eric Mendelson'이 ERIC에 0.8로 매칭되던 HEICO 케이스 → 0.577 < 0.7). attachment_parser는 HK FF305 'Next Day Disclosure Return'·월간 자사주 매입 양식을 실적 신호 규칙보다 **먼저** `6-K_EVENT`로 분류(BABA 자사주 표의 'per share'가 `6-K_QUARTERLY`/HIGH를 유발하던 건).
- **파서·본문선택 견고화(2026-07-30, ARM 1Q27 계기)**: ① `attachment_parser`의 6-K 분기 분류가 재무 신호를 종전 8000자 창 안에서만 찾다 짧은 커버 PR + 초대형 주주서한(EX-99.2) 구조를 놓치던 문제를, 전체 exhibit 텍스트에서 **강한 재무 신호(`STRONG_EARNINGS_KEYWORDS`) 3개 이상 또는 실적 제목 패턴**을 요구하는 심층 판정을 더해 해결(약한 신호 per share/diluted는 제외해 CCJ M&A 오탐 회피). ② `translator`에 `_resolve_analysis_text`를 추가 — `primary_text`가 강한 재무 신호를 담고 있으면 그대로 쓰고, 부족할 때만 첨부 중 **가장 긴 EX-99**를 분석 본문으로 덧붙인다(ARM은 2,842자 커버 PR → EX-99.2 89,073자로 확장, BABA는 폴백 미채택). 프롬프트 빌더는 손대지 않아 prompt version hash는 불변.
- ★**LLM 호출 구독 이관 + 새벽 배치 분리(2026-08-18)**: 전문 번역·분석 시트 생성을 종량 Anthropic API에서 **구독 headless CLI**([[infra-headless-llm]])로 옮겼다 — 크레딧 고갈로 파이프라인이 통째로 멈추는 사고가 3회 반복된 게 계기(비용 0원화보다 **정지 위험 제거**가 목적). translator의 저수준 호출 2곳(`_call_sonnet`=분석, `_call_haiku_long`=전문 청크)이 백엔드 디스패치를 타고, 실사용 모델은 행 단위 `model` 필드에 `claude-sonnet-5@headless` 형태로 기록돼 **어느 백엔드가 만든 산출물인지 사후 판별**된다. 전환은 env 스위치(`EARNINGS_ANALYSIS_BACKEND`·`EARNINGS_TRANSLATE_BACKEND`, **코드 기본값은 `api`**)라 롤백=env 제거.
  - 대량 소화는 08:00 러너에서 떼어내 **새벽 02:30 배치**([[timer-earnings-night-llm]], `night_llm.py`)로 옮겼다 — 구독 쿼터가 사용자 오전 사용분과 경합하는 것을 피하는 분업. 08:00 러너는 `EARNINGS_MORNING_TRANSLATE_LIMIT`(기본 3)만큼만 **보충 번역**한다.
  - 동반 견고화: `db.py`에 busy_timeout + **oldest-first 무기아 pending 쿼리**(새벽 배치가 최신 것만 집어 오래된 항목이 영구 후순위가 되는 것 차단), 재번역 시 기존 md 무효화, `transcript_store` **원자적 md 쓰기**(배치 중 강제종료로 반쯤 쓰인 md가 남지 않도록).
  - 다이제스트에 `🌙 번역 완료·전일` / `🌙 번역 백로그 N건` 섹션 추가 — 완료 전환이 24h 창 밖(새벽)에서 일어나면서 기존 창 기준 섹션에서 통째로 빠지던 유실을 메운다.
- ★**전문 탐색 web_search도 구독 이관(2026-08-20, `transcript_sources/search_provider.py`)**: 8/18에 번역·분석은 구독으로 옮겼지만 **전문 URL을 찾는 web_search만 종량 API에 남아** 있었다 — 크레딧이 마르면 번역할 전문 자체가 안 들어오므로 여기가 마지막 종량 의존점이었다. 이제 `claude -p`에 **WebSearch 도구만 허용**하고 `--json-schema`로 `{results:[{url,title}]}`를 강제해 받는다(`EARNINGS_SEARCH_BACKEND`, 기본 `headless`·롤백 `api`). 도구를 여는 만큼 [[infra-headless-llm]] 봉인 코어를 쓰지 않고 이 모듈이 CLI를 직접 띄우되, **환경 격리·전용 홈·프로세스그룹 종료는 코어 헬퍼를 재사용**한다.
  - API의 `allowed_domains`에 대응하는 **도메인 경계 사후 필터**(`host == site` 또는 `.site`로 끝날 때만 채택) + 중복 제거를 파이썬 쪽에 둔다 — CLI에는 도메인 제한 인자가 없어 모델의 자율 검색 결과를 그대로 믿으면 site 한정이 사실상 풀린다. 프롬프트도 "실제로 찾은 URL만, 없으면 빈 목록"으로 날조를 막는다.
  - **인증 실패는 raise, 그 외 실패·0건은 빈 리스트**: 조용한 영구 0건(무경보로 전문 수집이 말라붙는 실패 모드)을 막으려는 구분이고, 기존 API 경로의 `AuthenticationError` re-raise 정책을 그대로 승계했다. ★**유료 API 자동 폴백은 두지 않는다**(2026-08-20 사용자 규칙 — 유료 전환은 사전 승인 사항). `--max-turns`는 비용 상한이 아니라 폭주 방지용일 뿐, API의 `max_uses=1`과 동등하지 않다.
- 상태 DB=`earnings.db`. 예정 포맷=`티커/발표일자`(기업명 없음 확정). `--dismiss` CLI.
- 캘린더는 `gha-earnings-calendar-sync`가 채우고 이 파이프라인이 소비.

## Reads
- [[store-earnings-db]] — earnings.db (실적봇 상태)

## Writes
- [[store-earnings-db]] — earnings.db (실적봇 상태)
- [[store-transcripts-md]] — 어닝콜 번역 전문 md (~/datalake/transcripts/)
- [[store-analyses-md]] — 실적 분석 1-page md (~/datalake/analyses/)

## Depends on
- [[src-earnings-calendar-sync]] — 실적 캘린더 sync (earnings_calendar_sync.py)
- [[infra-headless-llm]] — 구독 LLM 백엔드 (headless claude · codex 폴백)
- [[ext-notion]] — Notion (실적·리서치 퍼블리시 대상)
- [[ext-data-apis]] — 외부 데이터 API/소스 집합
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `execution/earnings_bot/runner.py`
- `execution/earnings_bot/night_llm.py`
- `execution/earnings_bot/headless_llm.py`
- `execution/earnings_bot/morning_digest.py`
- `execution/earnings_bot/edgar_monitor.py`
- `execution/earnings_bot/transcript_watch.py`
- `execution/earnings_bot/transcript_sources/search_provider.py`
- `execution/earnings_bot/transcript_gate.py`
- `execution/earnings_bot/prompt_builder.py`
- `execution/earnings_bot/translator.py`
- `execution/earnings_bot/ticker_registry.py`
- `execution/earnings_bot/cli/transcript_override.py`
- `execution/earnings_bot/notion_publisher.py`
- `execution/earnings_bot/transcript_store.py`
- `execution/earnings_bot/analysis_store.py`
- `execution/earnings_bot/backfill_analyses_md.py`

## Alerts
⚠ 타이머 OnFailure → 텔레그램
