---
id: "infra-github"
name: "GitHub (정본 repo · Pages · Actions)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "github"
schedule_kst: "상시"
status: "active"
code:
  - ".github/workflows/"
  - "scripts/safe_commit_push.sh"
reads: []
writes: []
depends_on: []
alerts: ""
---

# GitHub (정본 repo · Pages · Actions)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** github · **Schedule (KST):** 상시 · **Status:** active · **Project:** antigravity

생태계의 단일 정본(source of truth). `sisyphe10/Antigravity_Market_Dashboard` repo가 코드·데이터·산출 HTML을 모두 보관하고, GitHub Pages가 라이브 대시보드를 서빙하며, GitHub Actions가 스케줄 수집 잡의 컴퓨트 한 축을 담당한다.

- 모든 수집 잡은 산출물을 커밋→push하고, VM은 `*/5` git-pull로 이를 받아 동기화한다(단일 워킹트리 정합).
- push 레이스는 `scripts/safe_commit_push.sh`(fetch+merge+재시도)가 자가복구, xlsx 바이너리 충돌만 가드로 막는다.
- 실패해도 워크플로가 green일 수 있어(개별 시리즈 stale) 신선도 감시(`gha-daily-health-check`)가 별도로 존재한다.
- 운영 팁: `execution/**` push는 장중 `gha-daily-crawl`을 트리거하므로 커밋 메시지에 `[skip ci]` 필수.

## Reads
- (none)

## Writes
- (none)

## Depends on
- (none)

## Code
- `.github/workflows/`
- `scripts/safe_commit_push.sh`

## Links
- [라이브 대시보드](https://sisyphe10.github.io/Antigravity_Market_Dashboard/index.html)
