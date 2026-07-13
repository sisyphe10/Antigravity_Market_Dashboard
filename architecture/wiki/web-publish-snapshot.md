---
id: "web-publish-snapshot"
name: "개인 스냅숏 게시 (publish_snapshot.sh)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "vm_macmini"
schedule_kst: "잡 성공 훅 (여러 잡)"
status: "active"
code:
  - "scripts/publish_snapshot.sh"
  - "scripts/compose_personal_view.py"
  - "config/publish_manifest.txt"
reads: []
writes:
  - "~/srv/dashboard/releases + current"
depends_on:
  - "infra-vm-macmini"
alerts: "실패해도 잡 rc 무관 · 어떤 실패 경로에서도 기존 current 불훼손"
---

# 개인 스냅숏 게시 (publish_snapshot.sh)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** vm_macmini · **Schedule (KST):** 잡 성공 훅 (여러 잡) · **Status:** active · **Project:** antigravity

2026-07-11 신설. 잡 wrapper(`run_gha_job.sh`/`run_timer_job.sh`) 성공 직후 호출되어 repo 산출물을 개인 ts.net 대시보드로 게시하는 스냅숏 게시기. Caddy가 서빙하는 `~/srv/dashboard/current`의 유일한 writer.

- 동작: 화이트리스트 rsync(`*.html`/`*.json`/`*.csv`/`orders/`/`architecture/`/`charts/`, `.env`·`.git` 구조적 배제) → `releases/rel-<ts>` 새 세대 → 검증 → `current` 심링크 원자 교체(rename(2)). 어떤 실패에서도 기존 current는 안 깨진다.
- **개인용 가공(1.5단계, `compose_personal_view.py`)**: rsync 직후 새 릴리스 사본에서만 가공 — `wrap.html` 제거 + AoE 11페이지 topnav 재구성(Wiki·Invest(→/journal)·우측 Sisyphe 탭) + `~/srv/sisyphe_plain` 원본에서 Sisyphe 평문 3페이지(index/dashboard/journal)를 `current/sisyphe/`로 합성(2026-07-13 staticrypt 암호화 폐기, 테일넷 한정이라 암호 프롬프트 제거 목적). 검증(sisyphe 존재·staticrypt 0·역방향 nav) 실패 시 세대 폐기. repo 원본·GitHub(팀원용)은 불변.
- mkdir 원자 락(120s)으로 게시 직렬화. 실패해도 잡 rc에 영향 없음(호출측 `|| true`).
- 팀원용 공개 게시는 별도 경로([[web-publish-pages]], gh-pages).

## Reads
- (none)

## Writes
- `~/srv/dashboard/releases + current`

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)

## Code
- `scripts/publish_snapshot.sh`
- `scripts/compose_personal_view.py`
- `config/publish_manifest.txt`

## Alerts
⚠ 실패해도 잡 rc 무관 · 어떤 실패 경로에서도 기존 current 불훼손
