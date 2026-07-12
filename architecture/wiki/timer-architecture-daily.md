---
id: "timer-architecture-daily"
name: "아키텍처 자동 최신화 타이머 (21:40, claude 헤드리스)"
domain: "ops-infra"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "21:40 매일"
status: "active"
code:
  - "launchd/timers/com.antigravity.architecture-daily.plist"
  - "scripts/update_architecture_daily.sh"
reads: []
writes:
  - "page-architecture"
depends_on:
  - "infra-vm-macmini"
  - "infra-github"
  - "page-architecture"
alerts: "FAIL → notify_sisyphe_failure.sh architecture-daily → 텔레그램"
---

# 아키텍처 자동 최신화 타이머 (21:40, claude 헤드리스)

**Domain:** 운영 · 인프라 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 21:40 매일 · **Status:** active · **Project:** antigravity

2026-07-12 신설. 매일 밤 21:40 KST 최근 변경을 읽어 아키텍처 위키를 자동 최신화하는 launchd 타이머(`com.antigravity.architecture-daily` → `update_architecture_daily.sh`). 이 컴포넌트 자신도 위키가 기술하는 실체다.

- ★**전용 클론**(`~/srv/arch_updater/repo`)에서 실행 — 프로덕션 트리의 `reset --hard`/5분 pull cron과 worktree 경합을 원천 차단. push는 이 클론에서 직접, 프로덕션·ts.net 반영은 git-pull cron(원격발 publish 훅)이 5분 내 자동 수행.
- 흐름: 클론 최신화 → 최근 변경 요약(기본 26h, `ARCH_SINCE`/catch-up은 `ARCH_MAX_TURNS` 상향) → `claude -p`가 **`architecture/wiki/`만** 편집(허용목록 가드로 그 외 변경 전부 폐기) → `rebuild_registry_from_wiki.py`로 registry 재생성 → `create_architecture.py`로 architecture.html 재생성 → `[skip ci]` 커밋 + push(fetch-merge 재시도 3회).
- claude는 월클럭 워치독(기본 30분, `ARCH_WALL_SEC`)과 `--max-turns`(기본 40)로 제한. 데이터 블록 내 텍스트는 비신뢰(프롬프트 주입 격리).

## Reads
- (none)

## Writes
- [[page-architecture]] — architecture.html (아키텍처)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)
- [[infra-github]] — GitHub (정본 repo · Pages · Actions)
- [[page-architecture]] — architecture.html (아키텍처)

## Code
- `launchd/timers/com.antigravity.architecture-daily.plist`
- `scripts/update_architecture_daily.sh`

## Alerts
⚠ FAIL → notify_sisyphe_failure.sh architecture-daily → 텔레그램
