---
id: "daemon-journal-api"
name: "Journal Trade API 데몬 (Escape Velocity, 127.0.0.1:8791)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "vm_macmini"
schedule_kst: "상시 + 일일 18:00 (trades 추출·재생성)"
status: "active"
code:
  - "launchd/web/com.antigravity.journal-api.plist"
  - "launchd/web/com.antigravity.journal-trades.plist"
reads:
  - "ext-sisyphe"
writes: []
depends_on:
  - "infra-vm-macmini"
  - "ext-sisyphe"
alerts: "KeepAlive=true (launchd 자동 재기동, ThrottleInterval=10)"
---

# Journal Trade API 데몬 (Escape Velocity, 127.0.0.1:8791)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** vm_macmini · **Schedule (KST):** 상시 + 일일 18:00 (trades 추출·재생성) · **Status:** active · **Project:** antigravity

2026-08-05 신설. 투자일지 Escape Velocity 웹뷰(`/journal/`)의 'Trade' 탭 매매일지+사유를 양방향 서빙하는 상시 데몬(`com.antigravity.journal-api`, RunAtLoad + KeepAlive)과, 매일 18:00 KST 매매 추출·전체 페이지 재생성 타이머(`com.antigravity.journal-trades`)의 한 쌍.

- 바인딩: `127.0.0.1:8791` 루프백 고정 — 직접 공개 노출 없음. Caddy가 `/journal/*`를 서빙하고 API를 이 포트로 리버스 프록시([[web-caddy]]).
- **백엔드 코드·데이터 모두 repo 밖**: journal-api plist가 `~/Journal/scripts/journal_api.py`를 repo venv 파이썬으로 띄우고, journal-trades는 `~/Journal/scripts/daily_refresh.sh`(Trade 추출 → Escape Velocity 전체 페이지 재생성)를 돈다. Journal 자산은 맥미니 로컬 전용으로 git·게시 파이프라인과 격리(전역 규칙 Journal 섹션) → **repo가 소유하는 것은 launchd 유닛 2개뿐**. [[daemon-plan-api]]와 같은 패턴.
- journal-api는 `run_bot.sh` 래퍼 미사용(의도) — 루프백 전용이라 네트워크 대기 불필요, 기동 120초 지연 회피. journal-trades는 standalone 타이머(`run_timer_job.sh`·`schedule.tsv` 미사용, premarket 잡과 동일 규격).
- 일일 18:00 잡은 **구 토요일 09:30 crontab(`# journal-chart`)을 대체**한다.
- launchd 관리: journal-api `ThrottleInterval=10`, 로그는 `logs/launchd/journal-api.{out,err}` · `journal-trades.{out,err}`. 계산 잡 아님(catch-up 대상 아님).

## Reads
- [[ext-sisyphe]] — Sisyphe 가계부/운동 대시보드 + 투자일지 시트

## Writes
- (none)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (맥미니)
- [[ext-sisyphe]] — Sisyphe 가계부/운동 대시보드 + 투자일지 시트

## Code
- `launchd/web/com.antigravity.journal-api.plist`
- `launchd/web/com.antigravity.journal-trades.plist`

## Alerts
⚠ KeepAlive=true (launchd 자동 재기동, ThrottleInterval=10)
