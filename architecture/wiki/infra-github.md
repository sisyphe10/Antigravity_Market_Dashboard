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

생태계의 단일 정본(source of truth). `sisyphe10/Antigravity_Market_Dashboard` repo가 코드·데이터를 보관하고, GitHub Actions가 (컷오버 전) 스케줄 수집 잡의 컴퓨트 한 축을 담당했다. 컴퓨트는 2026-07-11 맥미니로 이관([[infra-vm-macmini]]).

- **main = 소스·데이터만 (2026-07-12)**: git 비대화 대응으로 main은 **생성 대시보드 HTML 8종 추적을 중단**했다. 게시는 브랜치로 분리 — 팀원 WRAP은 `gh-pages`([[web-publish-pages]]), 개인 대시보드는 맥미니 ts.net([[web-caddy]]).
- **GitHub Pages = 팀원 WRAP 전용으로 축소**: `wrap.html` + wrap이 fetch하는 데이터(JSON + orders/)만 게시, 루트(`/`)는 wrap 리다이렉트. 개인 페이지는 공개 안 함.
- 모든 수집 잡은 산출물을 커밋→push하고, 맥미니는 `*/5` git-pull로 받아 동기화한다(단일 워킹트리 정합).
- push 레이스는 `scripts/safe_commit_push.sh`(fetch+merge+재시도)가 자가복구, xlsx 바이너리 충돌만 가드로 막는다. **push 성공 훅에서 [[web-publish-pages]]를 호출**해 gh-pages를 갱신한다.
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
- [팀원 WRAP (gh-pages)](https://sisyphe10.github.io/Antigravity_Market_Dashboard/wrap.html)
