---
id: "gha-daily-health-check"
name: "Daily Data Health Check (11:00)"
domain: "ops-infra"
project: "antigravity"
type: "gha_workflow"
runs_on: "gha"
schedule_kst: "11:00 매일"
status: "active"
code:
  - ".github/workflows/daily_health_check.yml"
  - "execution/check_data_freshness.py"
reads:
  - "store-dataset-csv"
  - "store-heartbeats"
writes: []
depends_on:
  - "infra-github"
  - "infra-telegram"
alerts: "stale 감지 → 텔레그램 (이 워크플로가 곧 경보원)"
---

# Daily Data Health Check (11:00)

**Domain:** 운영 · 인프라 · **Type:** GHA · **Runs on:** gha · **Schedule (KST):** 11:00 매일 · **Status:** active · **Project:** antigravity

일별 수집물이 임계(보통 2 거래일 연속 누락) 이상 멈추면 텔레그램 경보하는 신선도 워치독(`check_data_freshness.py`, 순수 표준 라이브러리).

- 워크플로가 green이어도 개별 시리즈가 stale인지 origin/main 산출물로 점검(대부분 데이터 잡이 실패 시 조용히 green이라 이 감시가 유일한 그물).
- GHA 스케줄 워크플로 자체의 '무성공'도 감시(cron 자동발견, 주중형 임계 4일/매일형 3일 — earnings 한 달 사각 재발 방지).
- Phase 2에선 heartbeats.json 나이 감시 섹션이 추가돼 캘린더/finalize 등 dated 산출 없는 잡 공백을 메움.

## Reads
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)
- [[store-heartbeats]] — heartbeats.json (Phase 2 워치독 인터페이스)

## Writes
- (none)

## Depends on
- [[infra-github]] — GitHub (정본 repo · Pages · Actions)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `.github/workflows/daily_health_check.yml`
- `execution/check_data_freshness.py`

## Alerts
⚠ stale 감지 → 텔레그램 (이 워크플로가 곧 경보원)
