---
id: "timer-earnings-night-llm"
name: "실적봇 새벽 LLM 배치 타이머 (earnings-night-llm 02:30)"
domain: "news-research"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "02:30 매일"
status: "active"
code:
  - "launchd/timers/com.antigravity.earnings-night-llm.plist"
  - "launchd/timers/run_timer_job.sh"
  - "execution/earnings_bot/night_llm.py"
reads:
  - "store-earnings-db"
writes:
  - "store-earnings-db"
  - "store-transcripts-md"
  - "store-analyses-md"
depends_on:
  - "src-earnings-pipeline"
  - "infra-headless-llm"
alerts: "run_timer_job stamp + OnFailure → notify_sisyphe_failure.sh earnings-night-llm → 텔레그램"
---

# 실적봇 새벽 LLM 배치 타이머 (earnings-night-llm 02:30)

**Domain:** 뉴스 · 리서치 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 02:30 매일 · **Status:** active · **Project:** antigravity

2026-08-18 신설. [[src-earnings-pipeline]]의 무거운 LLM 작업(분석 시트·전문 번역)만 떼어 새벽에 돌리는 launchd 타이머(`com.antigravity.earnings-night-llm` → `run_timer_job.sh earnings-night-llm` → `python -m execution.earnings_bot.night_llm`).

- **분리 이유**: 번역·분석이 [[infra-headless-llm]] 구독 쿼터를 쓰게 되면서, 08:00 러너와 같은 창에서 대량 배치를 돌리면 사용자 오전 사용분과 쿼터가 경합한다. 대량 소화는 새벽으로 밀고 08:00 러너는 소량 보충만 맡는 분업.
- **순서가 곧 정책**: ① 분석 백로그 먼저 → ② 전문 번역(둘 다 `oldest_first` — 번역이 쿼터를 다 먹어 분석이 영구 후순위가 되는 역전, 그리고 오래된 항목의 기아를 동시에 차단). ③ 발행·md 저장은 `finally`에서 실행돼 중간 실패와 무관하게 남는다.
- **정지 조건 3종**: 내부 데드라인 `NIGHT_LLM_DEADLINE`(기본 06:30 — 쿼터 창이 사용자 오전과 겹치는 꼬리를 자르고 08:00 러너와 간격 확보) · 상한 `NIGHT_LLM_MAX_ITEMS`(기본 60, 분석+번역 합산) · 쿼터 소진. **쿼터 소진은 정상 종료(exit 0, partial)** 로 잔여를 pending 그대로 다음 새벽에 이월하고, **인증 실패만 exit 1**로 래퍼 notify를 태운다.
- 래퍼 워치독 `job_timeout_seconds`=**17700s(07:25 하드컷)** — 내부 데드라인(06:30)이 1차, 워치독이 2차 방어선. 잡 락·.env 로드·stamp·실패 알림은 `run_timer_job.sh`가 담당하고 배치는 exit 코드만 정직하게 돌려준다.
- **캐치업 안전**: 02:30을 놓쳐 [[daemon-catchup]]이 낮에 재기동해도 데드라인 검사가 먼저 걸려 LLM 루프를 통째로 스킵한다 — 주간 쿼터 오발화 없음.
- `schedule.tsv`에 1행 등재 → [[daemon-daily-selfcheck]] stamp 신선도 감시에 자동 편입.
- 소화 결과는 다음 아침 다이제스트의 `🌙 번역 완료·전일` / `🌙 번역 백로그 N건` 섹션으로 드러난다(24h 창 밖에서 일어난 완료 전환이 유실되지 않도록 morning_digest에 추가된 섹션).

## Reads
- [[store-earnings-db]] — earnings.db (실적봇 상태)

## Writes
- [[store-earnings-db]] — earnings.db (실적봇 상태)
- [[store-transcripts-md]] — 어닝콜 번역 전문 md (~/datalake/transcripts/)
- [[store-analyses-md]] — 실적 분석 1-page md (~/datalake/analyses/)

## Depends on
- [[src-earnings-pipeline]] — 실적봇 파이프라인 (execution/earnings_bot/)
- [[infra-headless-llm]] — 구독 LLM 백엔드 (headless claude · codex 폴백)

## Code
- `launchd/timers/com.antigravity.earnings-night-llm.plist`
- `launchd/timers/run_timer_job.sh`
- `execution/earnings_bot/night_llm.py`

## Alerts
⚠ run_timer_job stamp + OnFailure → notify_sisyphe_failure.sh earnings-night-llm → 텔레그램
