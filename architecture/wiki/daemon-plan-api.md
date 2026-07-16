---
id: "daemon-plan-api"
name: "Plan API 데몬 (Sisyphe Ledger 자금계획, 127.0.0.1:8790)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "vm_macmini"
schedule_kst: "상시"
status: "active"
code:
  - "launchd/web/com.antigravity.plan-api.plist"
  - "launchd/bots/run_bot.sh"
reads:
  - "ext-sisyphe"
writes: []
depends_on:
  - "infra-vm-macmini"
  - "ext-sisyphe"
alerts: "KeepAlive=true (launchd 자동 재기동, ThrottleInterval=10)"
---

# Plan API 데몬 (Sisyphe Ledger 자금계획, 127.0.0.1:8790)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** vm_macmini · **Schedule (KST):** 상시 · **Status:** active · **Project:** antigravity

2026-07-15 신설. Sisyphe Ledger 'Plan' 탭의 자금계획 JSON을 서빙하는 상시 데몬(`com.antigravity.plan-api`, RunAtLoad + KeepAlive). Caddy가 `/plan-api/*`를 이 포트로 리버스 프록시([[web-caddy]]).

- 바인딩: `127.0.0.1:8790` 루프백 고정 — 직접 공개 노출 없음. 게이트는 **테일넷 단독**(Caddy 라우트 주석은 'basic_auth 이중'이라 적혀 있으나 실제 설정엔 auth import가 없다 — 주석이 stale).
- **백엔드 코드·데이터 모두 repo 밖** — plist가 `~/Journal/scripts/plan_api.py`를 repo venv 파이썬으로 띄우고, 데이터는 `~/Journal/plan_web.json`(**계좌번호 포함**). Journal 자산은 맥미니 로컬 전용으로 git·게시 파이프라인과 격리(전역 규칙 Journal 섹션) → repo가 소유하는 것은 launchd 유닛뿐.
- launchd 관리: `ThrottleInterval=10`으로 크래시 루프 억제, 실행은 봇 공용 wrapper `launchd/bots/run_bot.sh plan-api`, 로그는 `logs/launchd/plan-api.{out,err}`. 계산 잡 아님(catch-up 대상 아님).
- ★plist의 경로가 프로덕션 트리(`~/Antigravity_Market_Dashboard`)로 하드코딩돼 있다 — 다른 타이머 plist의 `__REPO__` 토큰 치환 방식과 달라 클론에서 그대로 쓸 수 없다.

## Reads
- [[ext-sisyphe]] — Sisyphe 가계부/운동 대시보드 + 투자일지 시트

## Writes
- (none)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)
- [[ext-sisyphe]] — Sisyphe 가계부/운동 대시보드 + 투자일지 시트

## Code
- `launchd/web/com.antigravity.plan-api.plist`
- `launchd/bots/run_bot.sh`

## Alerts
⚠ KeepAlive=true (launchd 자동 재기동, ThrottleInterval=10)
