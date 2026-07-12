---
id: "page-architecture"
name: "architecture.html (아키텍처)"
domain: "ops-infra"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: "생성=21:40 (architecture-daily)"
status: "active"
code:
  - "architecture.html"
  - "architecture/registry.json"
  - "execution/create_architecture.py"
reads:
  - "architecture/registry.json"
writes: []
depends_on:
  - "timer-architecture-daily"
alerts: ""
---

# architecture.html (아키텍처)

**Domain:** 운영 · 인프라 · **Type:** Page · **Runs on:** github · **Schedule (KST):** 생성=21:40 (architecture-daily) · **Status:** active · **Project:** antigravity

생태계 아키텍처를 보여주는 페이지. **registry 기반 자동 생성물** — `architecture/wiki/*.md` 코퍼스가 단일 출처이고, `rebuild_registry_from_wiki.py`가 registry.json을, `create_architecture.py`가 architecture.html(+wiki/INDEX.md)을 재생성한다. **직접 수정 금지.**

- 매일 밤 [[timer-architecture-daily]](21:40, claude 헤드리스)가 최근 변경을 위키에 반영하고 registry·html을 재생성해 push → 수동 동기화 부담이 해소됐다.
- 컴포넌트(봇/잡/페이지/데이터) 추가·변경은 위키 .md를 고쳐야 도식도·타임라인·위키가 함께 갱신된다.

## Reads
- `architecture/registry.json`

## Writes
- (none)

## Depends on
- [[timer-architecture-daily]] — 아키텍처 자동 최신화 타이머 (21:40, claude 헤드리스)

## Code
- `architecture.html`
- `architecture/registry.json`
- `execution/create_architecture.py`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/architecture.html)
