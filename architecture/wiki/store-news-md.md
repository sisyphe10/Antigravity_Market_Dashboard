---
id: "store-news-md"
name: "뉴스 소스 아카이브 md (~/datalake/news/)"
domain: "news-research"
project: "antigravity"
type: "store"
runs_on: "vm_macmini"
schedule_kst: "소스 폴링 시 (아카이브 훅)"
status: "active"
code:
  - "execution/sources/archive.py"
  - "datalake/backfill_news.py"
reads: []
writes: []
depends_on:
  - "src-generic-pipeline"
alerts: ""
---

# 뉴스 소스 아카이브 md (~/datalake/news/)

**Domain:** 뉴스 · 리서치 · **Type:** Store · **Runs on:** vm_macmini · **Schedule (KST):** 소스 폴링 시 (아카이브 훅) · **Status:** active · **Project:** antigravity

2026-08-05 신설. [[bot-ra-sisyphe]]의 각 소스 잡([[src-generic-pipeline]])이 fetch 직후 `execution/sources/archive.py`를 호출해 게시글 1건을 md 1개로 영속화하는 아카이브 코퍼스. 이 코퍼스가 [[daemon-datalake-webui]] 위키 검색·운용보고서의 뉴스 DB가 된다.

- 경로: `~/datalake/news/<source>/<연도>/<YYYYMMDD>_<id>.md` — post id 기준 멱등(존재 시 skip). frontmatter = source/label/id/title/category/date/url/archived_at.
- **텔레그램 발송과 완전 분리·append-only** — 아카이브는 모든 예외를 삼키고 로그만 남겨 **발송을 절대 깨지 않는다**(멱등이라 재실행 안전).
- 소급 백필은 `datalake/backfill_news.py`(일회성·멱등, 존재 파일 skip으로 재개): kna는 목록 전체 순회(로그인 시 미국 본문 포함), trendforce는 wp-json 페이지네이션, semianalysis는 RSS 최근분, foreign_ir는 제목·링크만.
- [[daemon-datalake-webui]] `wiki_tools.py`의 SEARCH_ROOTS에 `news`가 등재돼 `#태그`·자연어 문답이 이 코퍼스를 훑는다.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-generic-pipeline]] — Generic Source Pipeline (execution/sources/)

## Code
- `execution/sources/archive.py`
- `datalake/backfill_news.py`
