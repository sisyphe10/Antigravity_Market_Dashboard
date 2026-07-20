---
id: "launchd-gha-phase2"
name: "GHA 잡 흡수 layer (launchd Phase 2 초안)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "vm_macmini"
schedule_kst: "이관 완료 — 각 잡 스케줄"
status: "active"
code:
  - "launchd/gha/"
  - "launchd/gha/run_gha_job.sh"
  - "launchd/gha/schedule_gha.tsv"
  - "launchd/gha/install_gha.sh"
reads: []
writes:
  - "store-heartbeats"
depends_on:
  - "infra-vm-macmini"
  - "gha-daily-crawl"
  - "gha-daily-fred"
  - "gha-daily-ecos"
  - "gha-daily-kofia"
  - "gha-daily-universe"
  - "gha-daily-krx-valuation"
  - "gha-daily-disclosures"
  - "gha-earnings-calendar-sync"
  - "gha-finalize-orders"
  - "gha-daily-taiwan-revenue"
alerts: "wrapper notify_failure → 텔레그램 (맥미니)"
---

# GHA 잡 흡수 layer (launchd Phase 2 초안)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** vm_macmini · **Schedule (KST):** 이관 완료 — 각 잡 스케줄 · **Status:** active · **Project:** antigravity

GitHub Actions 스케줄 워크플로를 맥미니 launchd LaunchDaemon으로 흡수하는 Phase 2 레이어(`launchd/gha/`). **2026-07-11 컷오버 완료 — GHA 이관 잡 10종(taiwan 포함)이 맥미니에서 라이브.** 각 원본 yml은 `schedule:`만 제거되고 `workflow_dispatch`는 롤백 경로로 유지된다.

- 대상 10잡: gha-fred/universe/ecos/kofia/krx-valuation/disclosures/crawl/earnings-calendar-sync/finalize-orders + taiwan-revenue(plan 이후 추가, 10번째). 이후 earnings-ir-day(2026-07-20 분리, 11번째)가 더해졌다.
- 공용 wrapper `run_gha_job.sh`: 잡별 락 + `wrap-nav-pipeline` 공유 락(GHA concurrency 대체) + 안전 .env 파서 + 타임아웃 워치독 + 성공 stamp + 실패 알림 + `heartbeats.json` 방출 + 성공 훅에서 [[web-publish-snapshot]] 게시.
- UTC→KST 환산 함정: gha-fred는 월~금 22:50 UTC → **화~토 07:50 KST**(요일 +1일).
- 컷오버는 하루 1잡 짝 커밋으로 진행됐고 finalize-orders가 최후였다.
- ★earnings-calendar-sync 이중 실행(VM cron 15:00 + GHA 07:00) 단일화는 이관 시 정리 대상.
- ★**earnings IR Day 분리(2026-07-20)**: `gha-earnings-calendar-sync`가 캘린더 쓰기만으로 900s를 소진해 IR Day(Finnhub 315종목 + EDGAR 8-K)가 강제종료 → `earnings_calendar_sync.py`를 `--skip-ir-day`/`--skip-earnings` 플래그로 쪼개 **11번째 launchd 잡 `gha-earnings-ir-day`(07:15)**를 신설(같은 스크립트, 별도 yml 없음). 두 잡 타임아웃 900→1800s(`run_gha_job.sh` `job_timeout_seconds`), `schedule_gha.tsv`·`install_gha.sh`(ALL_JOBS/Wave3) 등재.

## Reads
- (none)

## Writes
- [[store-heartbeats]] — heartbeats.json (Phase 2 워치독 인터페이스)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)
- [[gha-daily-crawl]] — Daily Market Crawl (23:00)
- [[gha-daily-fred]] — Daily FRED US Macro (07:50 화~토)
- [[gha-daily-ecos]] — Daily ECOS BOK (17:40 평일)
- [[gha-daily-kofia]] — Daily KOFIA Stats + NPS (17:30 평일)
- [[gha-daily-universe]] — Daily Universe yfinance (18:30 + 07:00)
- [[gha-daily-krx-valuation]] — Daily KRX Index Valuation (18:30 평일)
- [[gha-daily-disclosures]] — Daily Disclosures DART+KIND (16:30)
- [[gha-earnings-calendar-sync]] — Earnings Calendar Sync (07:00)
- [[gha-finalize-orders]] — Finalize Pending Orders + AUM (16:00)
- [[gha-daily-taiwan-revenue]] — Daily Taiwan Monthly Revenue (23:20)

## Code
- `launchd/gha/`
- `launchd/gha/run_gha_job.sh`
- `launchd/gha/schedule_gha.tsv`
- `launchd/gha/install_gha.sh`

## Alerts
⚠ wrapper notify_failure → 텔레그램 (맥미니)
