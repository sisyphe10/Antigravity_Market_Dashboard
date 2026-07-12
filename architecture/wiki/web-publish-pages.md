---
id: "web-publish-pages"
name: "gh-pages 게시 (publish_pages.sh, 팀 WRAP 전용)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "vm_macmini"
schedule_kst: "push 성공 훅 / 원격변경 훅"
status: "active"
code:
  - "scripts/publish_pages.sh"
reads:
  - "page-wrap"
  - "store-portfolio-data"
  - "store-contribution-data"
  - "store-orders-pending"
writes:
  - "infra-github"
depends_on:
  - "infra-github"
  - "page-wrap"
alerts: "실패해도 잡 rc 무관 · 다음 게시에서 재시도"
---

# gh-pages 게시 (publish_pages.sh, 팀 WRAP 전용)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** vm_macmini · **Schedule (KST):** push 성공 훅 / 원격변경 훅 · **Status:** active · **Project:** antigravity

2026-07-12 신설. GitHub Pages를 **팀원 WRAP 전용**으로 축소하며 도입된 `gh-pages` 브랜치 단일 writer. main에서 생성 대시보드 HTML 추적을 중단(git 비대화 대응)하고, 게시물은 이 브랜치로만 내보낸다.

- 호출: `safe_commit_push.sh` push 성공 훅 + `git_pull.sh` 원격발 변경 훅. 맥 전용(GHA 러너에선 조용히 스킵).
- 게시 대상 = `wrap.html` + wrap이 fetch하는 데이터(`portfolio_data.json`·`contribution_data.json`·`disclosures.json`·`stock_master.json` + `orders/*.json`)만. 개인 대시보드(index/market/featured/etf…)는 공개 안 함 → 개인 뷰는 ts.net([[web-caddy]]).
- 루트(`/`)는 `wrap.html`로 즉시 리다이렉트(개인 랜딩 미노출).
- ★rsync 금지(실측): `--delete`는 매니페스트 축소 미반영, `--delete-excluded`는 `.git` 파괴 → "전체 비우고 명시 복사"가 결정적. 커밋 수 임계(3000) 초과 시에만 orphan squash 재생성.
- 게시 전용 clone(`~/srv/pages_publisher/repo`)에서만 gh-pages를 만짐(운영 checkout과 완전 분리).

## Reads
- [[page-wrap]] — wrap.html (WRAP 대시보드)
- [[store-portfolio-data]] — portfolio_data.json
- [[store-contribution-data]] — contribution_data.json
- [[store-orders-pending]] — orders/ (pending_orders · aum_pending)

## Writes
- [[infra-github]] — GitHub (정본 repo · Pages · Actions)

## Depends on
- [[infra-github]] — GitHub (정본 repo · Pages · Actions)
- [[page-wrap]] — wrap.html (WRAP 대시보드)

## Code
- `scripts/publish_pages.sh`

## Alerts
⚠ 실패해도 잡 rc 무관 · 다음 게시에서 재시도
