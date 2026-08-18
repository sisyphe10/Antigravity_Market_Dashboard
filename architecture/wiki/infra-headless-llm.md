---
id: "infra-headless-llm"
name: "구독 LLM 백엔드 (headless claude · codex 폴백)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "vm_macmini"
schedule_kst: "상시 (호출 시)"
status: "active"
code:
  - "execution/earnings_bot/headless_llm.py"
  - "execution/earnings_bot/tests_headless_llm.py"
  - "execution/research_bot/llm_backends.py"
  - "execution/research_bot/codex_llm.py"
reads: []
writes: []
depends_on:
  - "infra-vm-macmini"
alerts: "인증 만료 사전 경고 = daemon-daily-selfcheck(D-7) · 호출 실패는 각 소비자 잡의 알림 경로"
---

# 구독 LLM 백엔드 (headless claude · codex 폴백)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** vm_macmini · **Schedule (KST):** 상시 (호출 시) · **Status:** active · **Project:** antigravity

2026-08-18 신설. 봇 파이프라인의 LLM 호출을 **종량 API 대신 구독 쿼터**로 태우는 공용 코어. 크레딧 고갈로 파이프라인이 멈춘 사고가 반복되면서([[src-earnings-pipeline]] 3회, [[bot-research-notes]] 2회) 생성 호출을 구독으로 옮긴 결과물이다. [[daemon-datalake-webui]]의 `headless_backend.py`(2026-08-05, 위키 문답)가 원조 패턴이고, 이 노드는 그 패턴을 **도구 없는 순수 생성 전용**으로 봉인해 재사용 가능한 형태로 뽑아낸 것.

- **봉인 코어 `headless_llm.py`**: `claude -p`를 `--output-format stream-json`으로 호출하되 도구를 **양방향으로 차단**한다 — `--safe-mode --tools "" --disallowedTools "*" --strict-mcp-config`(빈 mcp config) `--no-session-persistence --max-turns 1` + 작업 cwd를 빈 전용 홈(`~/.earnings_llm_home`)으로 두고, 그래도 `tool_use` 블록이 나오면 **사후 검사로 실패 처리**. 시스템 프롬프트는 append가 아닌 **대체 모드**(`--system-prompt`)라 CLI 기본 페르소나가 섞이지 않는다. API 저수준 호출과 **같은 반환 계약** + provenance(`resolved_model`·`backend`·`cli_version`)를 돌려주므로 상류는 백엔드 전환을 몰라도 된다. `call_multimodal()`은 `--input-format stream-json`으로 base64 이미지 블록을 실어 보내는 변형(리서치노트 요약용, 텍스트 `call()`은 바이트 무변경).
- **★인증은 env로 결정된다**: `ANTHROPIC_API_KEY`가 환경에 남아 있으면 CLI가 **조용히 API 과금**으로 붙는다. 그래서 상속이 아니라 **allowlist env**(PATH·HOME·LANG·LC_ALL·TZ·TERM·DISABLE_AUTOUPDATER)로 새로 짜서 넘긴다 — dotenv가 `os.environ`을 오염시켜도 무관. 기동 전 `claude auth status`로 preflight(구독 인증 아니면 즉시 AuthError).
- **★실패 판정 함정 3종**(실측): ① CLI는 **인증 실패에도 exit 0 + `subtype='success'`** — 판정은 본문 `Failed to authenticate` 마커로 한다([[daemon-datalake-webui]]가 먼저 겪은 것과 같은 함정). ② `rate_limit_event`는 **정상 성공에도 흘러나온다** — 이벤트 존재만으로 쿼터 소진을 단정하면 안 되고, 쿼터 마커는 `is_error` 결과에 한정해 본다. ③ 입력이 프롬프트 캐시로 계상돼 `modelUsage.inputTokens=1`로 보인다 — 실제 입력은 `cacheCreationInputTokens`이라 토큰 집계는 캐시 필드를 합산한다.
- **타입 예외로 배치 정책을 분기**: `HeadlessAuthError`(재시도 무의미, 즉시 중단) / `HeadlessQuotaError`(잔여는 pending 유지 후 다음 배치 이월) / 일반 `HeadlessError`(1회 재시도). 이 구분이 [[timer-earnings-night-llm]]의 "쿼터 소진=정상 종료, 인증 실패=exit 1" 정책의 근거다.
- **2차 폴백 codex(`codex_llm.py`)**: ChatGPT 구독의 `codex exec`를 같은 격리 원칙으로 감싼다 — env allowlist + **HOME=전용 최소 홈**(`~/.research_codex_home`, 내용물은 `.codex/auth.json` 사본뿐 → 실제 홈의 `.ssh`·`.env` 비노출) + 프롬프트는 argv 금지 **stdin 전달**(ps 노출·argv 한도 회피) + 프로세스그룹 TERM→KILL. ★**모델은 지정하지 않는 것이 정답** — ChatGPT 계정은 `--model gpt-5` 명시를 400으로 거부해(2026-08-18 실측) 기본 모델을 쓰고, 필요 시 `RESEARCH_CODEX_MODEL`로만 오버라이드한다. 미설치·미인증이면 체인이 이 단계를 **skip**하되 사유는 실패 알림에 노출된다.
- **체인·예산·게이트(`llm_backends.py`)**: 1차 headless(구독) → 2차 codex(구독) → 3차 유료 API. 총 25분 예산을 단계별(1차 600s·2차 480s·3차 잔여)로 쪼개고 잔여 60초 미만이면 그 단계를 건너뛴다. 백엔드 출력은 공통 게이트(최소 분량·`## ` 헤딩·거절문 마커·**시크릿 패턴 스캔**·`[IMG:n]`∩manifest 검증)를 통과해야 채택되고, 실패하면 다음 백엔드로 내려간다. 전 단계 실패는 `ChainExhausted`로 단계별 사유 1줄씩을 실어 알린다.
- **롤백은 env 한 줄**(코드 기본값이 구경로): 어닝봇 `EARNINGS_ANALYSIS_BACKEND`/`EARNINGS_TRANSLATE_BACKEND`(기본 `api`), 리서치봇 `RESEARCH_LLM=api`. **유료 3차 폴백은 기본 잠김**(`RESEARCH_ALLOW_PAID_FALLBACK=1`일 때만) — 기본 상태에서 크레딧 소비 0이 구조적으로 보장된다.
- **단일 장애점은 OAuth 만료**: 이 코어를 쓰는 잡이 늘수록 `~/.claude/.credentials.json` 만료 한 번이 넓게 번진다. rc로는 잡히지 않는 실패라 [[daemon-daily-selfcheck]]의 **D-7 만료 사전 경고**가 유일한 선행 감지 경로다.
- 검증 자산: `tests_headless_llm.py`가 fake-CLI 픽스처로 인증 실패·쿼터·도구 유출·타임아웃 등 계약을 고정한다(도입 시 14/14 통과).
- 소비자: [[src-earnings-pipeline]]·[[timer-earnings-night-llm]](전문 번역·분석 시트) · [[bot-research-notes]](23:00 일일 요약).

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (맥미니)

## Code
- `execution/earnings_bot/headless_llm.py`
- `execution/earnings_bot/tests_headless_llm.py`
- `execution/research_bot/llm_backends.py`
- `execution/research_bot/codex_llm.py`

## Alerts
⚠ 인증 만료 사전 경고 = daemon-daily-selfcheck(D-7) · 호출 실패는 각 소비자 잡의 알림 경로
