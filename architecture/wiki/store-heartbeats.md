---
id: "store-heartbeats"
name: "heartbeats.json (Phase 2 워치독 인터페이스)"
domain: "ops-infra"
project: "antigravity"
type: "store"
runs_on: "github"
schedule_kst: "각 GHA 잡 성공 시"
status: "planned"
code: []
reads: []
writes: []
depends_on:
  - "launchd-gha-phase2"
alerts: ""
---

# heartbeats.json (Phase 2 워치독 인터페이스)

**Domain:** 운영 · 인프라 · **Type:** Store · **Runs on:** github · **Schedule (KST):** 각 GHA 잡 성공 시 · **Status:** planned · **Project:** antigravity

맥미니 Phase 2에서 각 GHA 잡 wrapper가 성공 직후 `{"<잡>": epoch}`를 upsert하는 liveness 파일.

- 목적: repo 밖 산출(earnings-calendar-sync)·비시계열(finalize-orders)처럼 신선도 감시 사각인 잡의 '살아있음'을 커버.
- 소비자: `check_data_freshness`의 heartbeat 나이 감시 섹션(patch, A14/A15). HEARTBEAT_JOBS에 없는 잡은 침묵.
- **planned**: Phase 2 wrapper 활성 후 채워짐. 현재는 아직 정착 안 됨(REGISTRY_NOTES 참조).

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[launchd-gha-phase2]] — GHA 잡 흡수 layer (launchd Phase 2 초안)

## Code
- (none)
