---
id: "timer-earnings-bot"
name: "실적봇 타이머 (earnings-bot)"
domain: "news-research"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "08:00 매일"
status: "active"
code:
  - "scripts/vm_legacy/earnings-bot.timer"
  - "scripts/vm_legacy/earnings-bot.service"
  - "launchd/timers/com.antigravity.earnings-bot.plist"
reads: []
writes:
  - "store-earnings-db"
depends_on:
  - "src-earnings-pipeline"
alerts: "OnFailure → earnings-bot-notify.service → notify_sisyphe_failure.sh earnings-bot → 텔레그램"
---

# 실적봇 타이머 (earnings-bot)

**Domain:** 뉴스 · 리서치 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 08:00 매일 · **Status:** active · **Project:** antigravity

매일 08:00 KST 1회 미국 실적/IR Day 파이프라인 전체를 돌리는 oneshot 타이머(`earnings-bot.timer` → `earnings-bot.service` → `python -m execution.earnings_bot.runner`).

- 한 번 호출로 캘린더 sync + EDGAR/트랜스크립트 폴링 + 번역·요약(Claude) + 노션 퍼블리시 + 아침 다이제스트를 모두 수행.
- 실행 파이프라인 상세는 `src-earnings-pipeline` 참조.
- TimeoutStartSec=45min. 실패 시 `earnings-bot-notify.service`(OnFailure)로 텔레그램.
- **워치독 45→90min 상향(2026-07-31, `run_timer_job.sh` `job_timeout_seconds`=5400)**: 실적 성수기 피크일(2026-07-30 AMC 37건)에 분석 단계가 19/20에서 2700s 강제종료 → 5~9단계(전문 번역·md 발행·전문 저장·아침 다이제스트)가 통째로 미실행되고 텔레그램 다이제스트가 안 나갔다.
- **대량 LLM 작업 분리(2026-08-18)**: 번역·분석이 구독 쿼터([[infra-headless-llm]])를 쓰게 되면서 백로그 소화는 새벽 [[timer-earnings-night-llm]](02:30)으로 넘어갔고, 이 08:00 러너는 **`EARNINGS_MORNING_TRANSLATE_LIMIT`(기본 3)만큼 보충 번역**만 한다(새벽에 못 소화한 소량 보전). 0으로 두면 아침 번역을 아예 건너뛴다 — 러너의 나머지 단계(수집·매칭·발행·다이제스트)는 불변.
- 함정: 2026-07-02 GHA calendar sync SA키 stale로 한 달 무성공 → 로컬 키 검증 후 secret 교체 복구.

## Reads
- (none)

## Writes
- [[store-earnings-db]] — earnings.db (실적봇 상태)

## Depends on
- [[src-earnings-pipeline]] — 실적봇 파이프라인 (execution/earnings_bot/)

## Code
- `scripts/vm_legacy/earnings-bot.timer`
- `scripts/vm_legacy/earnings-bot.service`
- `launchd/timers/com.antigravity.earnings-bot.plist`

## Alerts
⚠ OnFailure → earnings-bot-notify.service → notify_sisyphe_failure.sh earnings-bot → 텔레그램
