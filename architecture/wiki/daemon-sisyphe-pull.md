---
id: "daemon-sisyphe-pull"
name: "Sisyphe repo 클론 서빙 (시간당 pull)"
domain: "ops-infra"
project: "antigravity"
type: "watcher"
runs_on: "vm_macmini"
schedule_kst: "매시 (1h)"
status: "active"
code:
  - "launchd/web/com.antigravity.sisyphe-pull.plist"
reads:
  - "ext-sisyphe"
writes:
  - "~/srv/sisyphe_repo"
depends_on:
  - "infra-vm-macmini"
  - "ext-sisyphe"
alerts: ""
---

# Sisyphe repo 클론 서빙 (시간당 pull)

**Domain:** 운영 · 인프라 · **Type:** Watcher · **Runs on:** vm_macmini · **Schedule (KST):** 매시 (1h) · **Status:** active · **Project:** antigravity

2026-07-11 신설. Sisyphe 개인 대시보드(가계부·운동·투자일지)를 통합 서빙하려고 그 repo를 `~/srv/sisyphe_repo`에 클론해 두고 시간당 최신화하는 launchd 데몬(`com.antigravity.sisyphe-pull`, StartInterval=3600).

- 동작: `git -C ~/srv/sisyphe_repo pull --ff-only --quiet`. RunAtLoad=true.
- `/sisyphe/*`로 서빙되는 개인 페이지(Journal·Weekly·Memento·Ledger)의 상류 원본 — 2026-07-16 'Sisyphe' 전용 탭이 해체되고 각 페이지가 AoE topnav 탭으로 승격된 뒤로도 소스는 이 클론이다([[ext-sisyphe]]). **AoE 기본 화면인 `memento.html`도 여기서 온다** → 이 pull이 멈추면 첫 화면이 낡는다.
- pull-only ff-only라 레이스 없음. 계산 잡 아님(catch-up 대상 아님).

## Reads
- [[ext-sisyphe]] — Sisyphe 가계부/운동 대시보드 + 투자일지 시트

## Writes
- `~/srv/sisyphe_repo`

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)
- [[ext-sisyphe]] — Sisyphe 가계부/운동 대시보드 + 투자일지 시트

## Code
- `launchd/web/com.antigravity.sisyphe-pull.plist`
