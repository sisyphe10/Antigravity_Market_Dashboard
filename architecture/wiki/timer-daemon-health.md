---
id: "timer-daemon-health"
name: "웹 데몬 헬스체크 타이머 (11:00, probe+자가복구)"
domain: "ops-infra"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "11:00 매일"
status: "active"
code:
  - "launchd/timers/com.antigravity.daemon-health.plist"
  - "scripts/check_daemon_ports.sh"
reads: []
writes: []
depends_on:
  - "infra-vm-macmini"
  - "infra-telegram"
  - "daemon-watchlist-quoteboard"
  - "daemon-datalake-webui"
  - "daemon-plan-api"
alerts: "kickstart 개입 시에만 텔레그램(전부 정상=무음) · 복구 실패 잔존 시 exit 1 → run_timer_job notify_failure 추가 발화"
---

# 웹 데몬 헬스체크 타이머 (11:00, probe+자가복구)

**Domain:** 운영 · 인프라 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 11:00 매일 · **Status:** active · **Project:** antigravity

2026-07-27 신설. 매일 11:00 KST AoE 웹 데몬 3종의 포트를 probe하고 다운이면 `launchctl kickstart -k`로 자가복구하는 launchd 타이머(`com.antigravity.daemon-health` → `run_timer_job.sh daemon-health` → `scripts/check_daemon_ports.sh`).

- 대상 3종(다운 시 사용자 체감이 서로 다름): [[daemon-watchlist-quoteboard]] `8778`(첫 화면/리다이렉트 대상 → 죽으면 루트부터 502), [[daemon-datalake-webui]] `8787`(Wiki·Earnings 탭 502), [[daemon-plan-api]] `8790`(Memento/Ledger 데이터 로드·저장 실패, 페이지 자체는 뜸).
- ★**KeepAlive가 못 살리는 유형을 겨냥**: 세 데몬 모두 launchd `KeepAlive=true`로 자동 재기동되지만, **좀비 프로세스가 포트를 점유해 bind가 반복 실패**하는 경우엔 재기동이 무한 실패한다(실사례: 2026-07-16 plan-api 8790 좀비 점유 → 502 지속). 이 타이머가 그 사각지대를 메운다.
- 동작: `curl -m5`로 probe(2xx/3xx=정상) → 다운이면 `kickstart -k system/com.antigravity.<name>` 1회 → 대기 후 재probe → 텔레그램 보고. 대기시간은 watchlist·datalake-webui 20초, plan-api 130초(기동 ~120초). run_timer_job 타임아웃 600초.
- 결과별 발화: 전부 정상(무개입)=**무음 exit 0** / kickstart로 복구=텔레그램 알림+exit 0 / kickstart 후에도 잔존=텔레그램 알림+**exit 1**(러너가 notify_failure 추가 발화, "좀비 포트 점유 의심: lsof -ti :PORT" 안내).
- ★**root 실행(의도)**: plist에 `UserName` 없음 = root — `kickstart -k system/*` 자가복구에 root 권한이 필요하다(수동 user 실행 시 probe만 유효, kickstart는 무효). `install_timers.sh` NAMES 목록에 등재돼 다른 타이머와 함께 설치·enable된다.
- [[daemon-daily-selfcheck]](08:50)의 웹 섹션이 Caddy·도달성·스냅숏 나이를 **감지만** 하던 것을 보완 — 이쪽은 데몬 포트를 직접 probe하고 **자가복구까지** 수행한다.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (맥미니)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)
- [[daemon-watchlist-quoteboard]] — 관심종목 시세판 데몬 (Watchlist, 127.0.0.1:8778)
- [[daemon-datalake-webui]] — 데이터레이크 문답 웹 UI 데몬 (AoE Wiki, 127.0.0.1:8787)
- [[daemon-plan-api]] — Plan API 데몬 (Sisyphe Ledger 자금계획, 127.0.0.1:8790)

## Code
- `launchd/timers/com.antigravity.daemon-health.plist`
- `scripts/check_daemon_ports.sh`

## Alerts
⚠ kickstart 개입 시에만 텔레그램(전부 정상=무음) · 복구 실패 잔존 시 exit 1 → run_timer_job notify_failure 추가 발화
