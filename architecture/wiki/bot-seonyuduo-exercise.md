---
id: "bot-seonyuduo-exercise"
name: "선유듀오 운동봇 (@SeonyuDuo_bot)"
domain: "personal"
project: "antigravity"
type: "bot"
runs_on: "vm_macmini"
schedule_kst: "상시 (06:00 다이제스트 등)"
status: "active"
code:
  - "execution/seonyuduo_exercise_bot.py"
  - "scripts/vm_legacy/seonyuduo-exercise-bot.service"
  - "launchd/bots/com.antigravity.seonyuduo-exercise-bot.plist"
reads:
  - "seonyuduo_exercise_user_map.json"
  - "seonyuduo_feedback_tips.json"
  - "seonyuduo_pms_tips.json"
writes: []
depends_on:
  - "ext-google-workspace"
  - "ext-seonyuduo-repo"
  - "infra-telegram"
  - "infra-headless-llm"
alerts: "OnFailure → notify_sisyphe_failure.sh seonyuduo-exercise-bot → 텔레그램"
---

# 선유듀오 운동봇 (@SeonyuDuo_bot)

**Domain:** 개인 · 가족 · **Type:** Bot · **Runs on:** vm_macmini · **Schedule (KST):** 상시 (06:00 다이제스트 등) · **Status:** active · **Project:** antigravity

부부 공유 운동기록 봇(`execution/seonyuduo_exercise_bot.py`). 자연어 운동기록을 LLM으로 파싱해 Google Sheet에 적재하고, 캘린더 다이제스트·리마인드를 보낸다.

- ★**분류 LLM 구독 이관(2026-08-20)**: `classify`의 자연어→batch 파싱이 종량 Haiku API에서 **구독 headless**([[infra-headless-llm]])로 넘어갔다(`SEONYUDUO_LLM`, 기본 `headless`·롤백 `api`). 사용자가 메시지를 보내고 기다리는 **대화형 경로**라 배치 잡들과 달리 지연이 곧 체감 품질 — headless 단발 호출(`hl.call`, 60s 타임아웃)을 기존 `run_in_executor` 스레드 안에서 돌려 이벤트 루프를 막지 않고, 재시도는 바깥 루프가 그대로 담당한다(계층 중복 회피). API 키 미설정은 종전 "조용한 None 반환"에서 **예외로 승격**돼 기존 재시도·오류 응답 경로를 탄다.

- 06:00 다이제스트 + 운동 1시간 전 리마인드(랜덤 피드백 팁). 가계부(ledger) 조회도 지원.
- 표기: 식/여니/듀오(내부 코드 TS/NY 유지). `/운동피드백` 커맨드.
- **`/pms` 생리통 약 복용 리마인드(2026-08-03 신설)**: 시작 시각(앵커)부터 **8시간 간격 15회(5일)** 슬롯을 미리 확정해 상태파일에 저장하고, 케어 팁을 곁들여 알린다. `/pms YYYY-MM-DD-HH`·`/pms N`(오늘 N시)로 직접 지정하거나, 무인자 시 시작 시각을 되묻는다(질문에 답장 입력, 그룹은 reply 필수). `/pms off` 중단. 팁=`seonyuduo_pms_tips.json`(생리 전→피크→회복 단계 순 15개), 상태=`.seonyuduo_pms.json`.
- `seonyuduo_exercise_user_map.json`, `seonyuduo_feedback_tips.json`. SeonyuDuo repo 생태계와 연동.

## Reads
- `seonyuduo_exercise_user_map.json`
- `seonyuduo_feedback_tips.json`
- `seonyuduo_pms_tips.json`

## Writes
- (none)

## Depends on
- [[ext-google-workspace]] — Google Workspace (Sheets · Calendar · Drive)
- [[ext-seonyuduo-repo]] — SeonyuDuo repo (가족 영상 · 운동봇 연동)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)
- [[infra-headless-llm]] — 구독 LLM 백엔드 (headless claude · codex 폴백)

## Code
- `execution/seonyuduo_exercise_bot.py`
- `scripts/vm_legacy/seonyuduo-exercise-bot.service`
- `launchd/bots/com.antigravity.seonyuduo-exercise-bot.plist`

## Alerts
⚠ OnFailure → notify_sisyphe_failure.sh seonyuduo-exercise-bot → 텔레그램
