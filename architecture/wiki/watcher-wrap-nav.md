---
id: "watcher-wrap-nav"
name: "Wrap_NAV 워처 (watch_wrap_nav.py)"
domain: "ops-infra"
project: "antigravity"
type: "watcher"
runs_on: "laptop"
schedule_kst: "상시"
status: "active"
code:
  - "watch_wrap_nav.py"
  - "scripts/merge_wrap_nav.py"
  - "scripts/local_safe_push.py"
reads:
  - "store-wrap-nav-xlsx"
writes:
  - "store-wrap-nav-xlsx"
depends_on:
  - "store-wrap-nav-xlsx"
  - "gha-recalc-wrap-nav"
alerts: ""
---

# Wrap_NAV 워처 (watch_wrap_nav.py)

**Domain:** 운영 · 인프라 · **Type:** Watcher · **Runs on:** laptop · **Schedule (KST):** 상시 · **Status:** active · **Project:** antigravity

노트북에서 상시 떠서 `Wrap_NAV.xlsx` 저장을 감지하면 3-way merge 후 origin으로 push하는 워처. 사용자가 엑셀에서 NAV/AUM/NEW 시트를 편집·저장하면 자동으로 라이브에 반영되는 손잡이.

- 전용 clone(sync_and_push) + HOLD 프로토콜 + 5분 자가복구 구조로 로컬↔origin 반복 분기를 근본 억제.
- push는 `merge_wrap_nav.py`의 xlsx 3-way 병합을 태워 바이너리 충돌을 회피.
- 운영 원칙: 로컬 수동 merge/push 금지 — 편집만 하고 origin 확인 후 deploy.sh만.
- 로그 `watch_wrap_nav.log`, PID `watch_wrap_nav.pid`.

## Reads
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)

## Writes
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)

## Depends on
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)
- [[gha-recalc-wrap-nav]] — Recalculate Wrap NAV (xlsx push 트리거)

## Code
- `watch_wrap_nav.py`
- `scripts/merge_wrap_nav.py`
- `scripts/local_safe_push.py`
