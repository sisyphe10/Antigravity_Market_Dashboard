---
id: "daemon-git-pull"
name: "repo 동기화 (git-pull */5)"
domain: "ops-infra"
project: "antigravity"
type: "watcher"
runs_on: "vm_macmini"
schedule_kst: "*/5분"
status: "active"
code:
  - "launchd/system/git_pull.sh"
  - "launchd/system/com.antigravity.git-pull.plist"
reads:
  - "infra-github"
writes: []
depends_on:
  - "infra-github"
  - "infra-vm-macmini"
alerts: "연속 12회 실패 → notify_sisyphe_failure.sh git-pull → 텔레그램 (맥미니 버전)"
---

# repo 동기화 (git-pull */5)

**Domain:** 운영 · 인프라 · **Type:** Watcher · **Runs on:** vm_macmini · **Schedule (KST):** */5분 · **Status:** active · **Project:** antigravity

5분마다 워킹트리를 origin과 동기화하는 봇·타이머의 생명선. 현재는 VM crontab(`*/5 git checkout -- "*.html"; git pull origin main`), 맥미니에선 launchd `com.antigravity.git-pull`(StartInterval=300)로 동등 이전.

- `git checkout -- "*.html"`가 핵심: 봇이 HTML을 계속 재생성해 dirty하면 pull이 영구 abort → 먼저 discard 후 fast-forward.
- pull-only라 push 레이스 없음(각 잡이 자기 safe_commit_push). 성공은 침묵.
- 맥미니 버전은 연속 실패 12회(=1h)에 텔레그램 1회 경보 + 쿨다운. catch-up 대상 아님(계산 잡 아님).
- 과거 사고: VM pull cron이 봇 미커밋 HTML로 abort→push job 연쇄실패 → `checkout -- *.html; pull`로 견고화.

## Reads
- [[infra-github]] — GitHub (정본 repo · Pages · Actions)

## Writes
- (none)

## Depends on
- [[infra-github]] — GitHub (정본 repo · Pages · Actions)
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)

## Code
- `launchd/system/git_pull.sh`
- `launchd/system/com.antigravity.git-pull.plist`

## Alerts
⚠ 연속 12회 실패 → notify_sisyphe_failure.sh git-pull → 텔레그램 (맥미니 버전)
