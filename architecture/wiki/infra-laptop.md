---
id: "infra-laptop"
name: "작업용 노트북 (ASUS Vivobook, Windows)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "laptop"
schedule_kst: "상시"
status: "active"
code:
  - "watch_wrap_nav.py"
  - "scripts/local_safe_push.py"
  - "scripts/auto_pull.ps1"
reads: []
writes: []
depends_on:
  - "infra-github"
alerts: ""
---

# 작업용 노트북 (ASUS Vivobook, Windows)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** laptop · **Schedule (KST):** 상시 · **Status:** active · **Project:** antigravity

사용자의 편집·운영 워크스테이션(Windows 11, i9-13900H). Wrap_NAV.xlsx 편집, 대시보드 코드 작성, 배포 트리거의 사람 손이 닿는 지점.

- `watch_wrap_nav.py` 워처가 상시 떠서 Wrap_NAV.xlsx 저장을 감지→merge→push한다.
- 로컬 워킹트리는 오염/분기되기 쉬워, 라이브 재생성은 origin 기준 격리 worktree 또는 GHA `workflow_dispatch`로 하는 것이 원칙(로컬 수동 merge/push 금지).
- Chrome 경로로 HTML 미리보기(Edge 아님).

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[infra-github]] — GitHub (정본 repo · Pages · Actions)

## Code
- `watch_wrap_nav.py`
- `scripts/local_safe_push.py`
- `scripts/auto_pull.ps1`
