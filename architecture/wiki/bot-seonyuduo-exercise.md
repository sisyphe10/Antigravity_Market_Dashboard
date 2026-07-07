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
  - "scripts/seonyuduo-exercise-bot.service"
  - "launchd/bots/com.antigravity.seonyuduo-exercise-bot.plist"
reads:
  - "seonyuduo_exercise_user_map.json"
  - "seonyuduo_feedback_tips.json"
writes: []
depends_on:
  - "ext-google-workspace"
  - "ext-seonyuduo-repo"
  - "infra-telegram"
alerts: "OnFailure → notify_sisyphe_failure.sh seonyuduo-exercise-bot → 텔레그램"
---

# 선유듀오 운동봇 (@SeonyuDuo_bot)

**Domain:** 개인 · 가족 · **Type:** Bot · **Runs on:** vm_macmini · **Schedule (KST):** 상시 (06:00 다이제스트 등) · **Status:** active · **Project:** antigravity

부부 공유 운동기록 봇(`execution/seonyuduo_exercise_bot.py`). 자연어 운동기록을 Haiku로 파싱해 Google Sheet에 적재하고, 캘린더 다이제스트·리마인드를 보낸다.

- 06:00 다이제스트 + 운동 1시간 전 리마인드(랜덤 피드백 팁). 가계부(ledger) 조회도 지원.
- 표기: 식/여니/듀오(내부 코드 TS/NY 유지). `/운동피드백` 커맨드.
- `seonyuduo_exercise_user_map.json`, `seonyuduo_feedback_tips.json`. SeonyuDuo repo 생태계와 연동.

## Reads
- `seonyuduo_exercise_user_map.json`
- `seonyuduo_feedback_tips.json`

## Writes
- (none)

## Depends on
- [[ext-google-workspace]] — Google Workspace (Sheets · Calendar · Drive)
- [[ext-seonyuduo-repo]] — SeonyuDuo repo (가족 영상 · 운동봇 연동)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `execution/seonyuduo_exercise_bot.py`
- `scripts/seonyuduo-exercise-bot.service`
- `launchd/bots/com.antigravity.seonyuduo-exercise-bot.plist`

## Alerts
⚠ OnFailure → notify_sisyphe_failure.sh seonyuduo-exercise-bot → 텔레그램
