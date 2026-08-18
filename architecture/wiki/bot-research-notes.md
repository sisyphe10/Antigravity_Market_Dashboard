---
id: "bot-research-notes"
name: "Research Notes 봇"
domain: "news-research"
project: "antigravity"
type: "bot"
runs_on: "vm_macmini"
schedule_kst: "상시 (이벤트 드리븐) + 23:00 일일 요약"
status: "active"
code:
  - "execution/research_bot/research_notes_bot.py"
  - "execution/research_bot/summarizer.py"
  - "execution/research_bot/llm_backends.py"
  - "execution/research_bot/codex_llm.py"
  - "execution/research_bot/notion_publisher.py"
  - "scripts/vm_legacy/research-notes-bot.service"
reads: []
writes:
  - "store-research-notes-db"
  - "research_headlines.json"
depends_on:
  - "infra-headless-llm"
  - "ext-notion"
  - "infra-telegram"
alerts: "OnFailure → notify_sisyphe_failure.sh research-notes-bot → 텔레그램"
---

# Research Notes 봇

**Domain:** 뉴스 · 리서치 · **Type:** Bot · **Runs on:** vm_macmini · **Schedule (KST):** 상시 (이벤트 드리븐) + 23:00 일일 요약 · **Status:** active · **Project:** antigravity

텔레그램으로 들어온 리서치 메시지(텍스트+이미지)를 LLM으로 상세 요약해 노션에 퍼블리시하는 봇(`execution/research_bot/research_notes_bot.py`). 수집은 상시(이벤트 드리븐), 요약·게시는 매일 **23:00 KST** 잡(`/summary`로 수동 실행, `force`로 강제 재실행).

- 요약 규칙: 토픽별 불릿 8~12개+, 이미 불릿이면 원문 유지, 모든 이미지 첨부, 엄중/중요 표시는 {RED} 태그→노션 빨간색.
- 메시지·미디어는 로컬 SQLite(`research_notes.db`) + `media/`에 보관 후 노션 페이지로.
- RA_Sisyphe_bot의 05:10 헤드라인이 이 봇이 쌓은 `research_headlines.json`을 읽어 아침 요약을 만든다.
- ★**일일 요약 LLM 백엔드 체인 전환(2026-08-18)**: 유료 API 단일 경로가 크레딧 고갈로 요약을 통째로 날린 사고 2회(7/21·8/17) 뒤, **1차 headless Claude(구독) → 2차 codex exec(ChatGPT 구독) → 3차 유료 API** 체인으로 바꿨다([[infra-headless-llm]]). **3차는 기본 잠김**(`RESEARCH_ALLOW_PAID_FALLBACK=1`일 때만)이라 평시 크레딧 소비는 0이고, 롤백은 `RESEARCH_LLM=api`(+봇 재시작)로 v0 유료 경로 복원. 이미지가 섞인 요약은 headless `call_multimodal`(stream-json 이미지 블록)로 넘어간다.
- **재실행 안전(같은 전환의 일부)**: 날짜별 single-flight + `media/summaries/<date>.state.json` **사이드카 상태**(generated→published→completed). 입력 해시가 같으면 LLM을 다시 부르지 않고 저장된 요약을 재사용하며, 게시 단계가 분리돼 **재시도가 노션 중복 페이지를 만들지 않는다**(체인이 25분 예산 안에서 여러 백엔드를 시도하는 구조라 중간 실패·재실행이 상시 가능하다는 전제). 블로킹 LLM·노션 호출은 `asyncio.to_thread`로 빼 봇 이벤트 루프를 막지 않는다.
- **게시 이미지의 단일 출처는 본문 `[IMG:n]`** — 종전 메타 '이미지:' 라인은 폐기하고, 본문이 실제로 참조한 인덱스 ∩ 입력 manifest만 붙인다(모델이 없는 이미지 번호를 만들어 붙이거나, 첨부만 되고 본문에 안 나오는 이미지가 섞이던 어긋남 차단).

## Reads
- (none)

## Writes
- [[store-research-notes-db]] — research_notes.db + media/ (리서치봇)
- `research_headlines.json`

## Depends on
- [[infra-headless-llm]] — 구독 LLM 백엔드 (headless claude · codex 폴백)
- [[ext-notion]] — Notion (실적·리서치 퍼블리시 대상)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `execution/research_bot/research_notes_bot.py`
- `execution/research_bot/summarizer.py`
- `execution/research_bot/llm_backends.py`
- `execution/research_bot/codex_llm.py`
- `execution/research_bot/notion_publisher.py`
- `scripts/vm_legacy/research-notes-bot.service`

## Alerts
⚠ OnFailure → notify_sisyphe_failure.sh research-notes-bot → 텔레그램
