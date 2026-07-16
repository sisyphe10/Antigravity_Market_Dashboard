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
- **개인용 가공(1.5단계, `compose_personal_view.py`)**: rsync 직후 새 릴리스 사본에서만 가공 — `wrap.html` 제거 + AoE topnav 재구성 + `~/srv/sisyphe_plain` 원본에서 Sisyphe 평문 페이지를 `current/sisyphe/`로 합성(2026-07-13 staticrypt 암호화 폐기, 테일넷 한정이라 암호 프롬프트 제거 목적). 주입은 기존 fragment를 먼저 제거하고 다시 넣는 정규화 방식이라 재실행에 멱등. 검증 실패 시 `exit 1` → 세대 폐기. repo 원본·GitHub(팀원용)은 불변.
- **2026-07-16 Sisyphe 구역 해체**: 별도 'Sisyphe' 탭·아이보리 강조·웜톤 바·←AoE 필을 걷어내고 **단일 AoE topnav로 전 페이지 통일**. 탭 순서 = 좌 `Watchlist · Market · Journal · Weekly · Memento · Ledger` / 우(`margin-left:auto`) `Wiki · Architecture`. 합성 대상은 평문 4페이지(index/dashboard/journal/**memento**)로 늘었고, Sisyphe 페이지의 topnav는 AoE 세트로 통째 교체(해당 탭 active)된다.
  - `Invest` → **`Journal`**로 개명 + `Weekly`를 딥링크(`journal.html#weekly`) 별도 탭으로 분리. 해시에 따라 nav active를 Journal↔Weekly로 바꾸고 페이지 서브탭까지 동기화하는 스크립트를 주입.
  - `/sisyphe/index.html`은 **Memento 리다이렉트 스텁**으로 격하 — AoE 기본 화면이 `memento.html`이 됐다([[web-caddy]]).
  - `wrap.html`은 팀 페이지라 **AoE 다크 nav 적용 대상에서 제외**(원래의 라이트 nav 유지, [[page-wrap]]) — 이 트리에서 게시되진 않지만 nav 주입 규칙이 갈린다.
  - ★**nav 주입은 스냅숏 안의 정적 파일까지만 닿는다**: 리버스 프록시로 붙는 두 데몬 페이지([[daemon-watchlist-quoteboard]] `/watchlist/` · [[daemon-datalake-webui]] `/wiki/`)는 스냅숏을 거치지 않아 **각자 topnav 마크업 사본을 들고 있고 손으로 맞춰야 한다**. 즉 AoE nav의 생산자는 이 합성기 하나가 아니라 `create_dashboard.py`·`create_architecture.py`·두 데몬 정적파일까지 여러 곳 — 탭을 추가·개명하면 전부 훑어야 어긋나지 않는다.
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
