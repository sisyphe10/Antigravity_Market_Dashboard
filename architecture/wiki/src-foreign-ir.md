---
id: "src-foreign-ir"
name: "해외 기업 IR/뉴스룸 (sources/foreign_ir.py)"
domain: "news-research"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "07:30 / 20:00 (ra-sisyphe)"
status: "active"
code:
  - "execution/sources/foreign_ir.py"
  - "foreign_ir_sources.json"
reads:
  - "foreign_ir_sources.json"
writes:
  - "store-sources-state"
depends_on:
  - "src-generic-pipeline"
  - "infra-telegram"
alerts: ""
---

# 해외 기업 IR/뉴스룸 (sources/foreign_ir.py)

**Domain:** 뉴스 · 리서치 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 07:30 / 20:00 (ra-sisyphe) · **Status:** active · **Project:** antigravity

해외 기업 IR/뉴스룸 ~134곳을 폴링해 신규 릴리스를 Haiku 한글요약으로 발송(07:30/20:00 KST).

- 403=핑거프린트 회전. 사각지대=월요일 다이제스트. "없음"은 침묵.
- 사이트 개편 복구: 커스텀 fetcher(_CUSTOM_FETCHERS, 예 Coveo/RSS), id체계 바뀌면 state 시딩 필수.
- **텐센트(0700) 사각지대 복구(2026-08-10)**: `financial-news.html`이 ~7/30부터 `financial-reports`로 리다이렉트되며 **17회 연속 무수집**. 후속 목록 `investor-news`는 제목을 `<p class='entry-title'>`로 내보내 날짜 앵커 기반 범용 추출기가 0건을 반환하고, RSS는 빈 WP 댓글 피드·wp-json은 401이라 표준 경로가 전부 막혔다 → `_fetch_tencent_investor_news` 커스텀 fetcher(`article.investor-news-item` 카드) 추가 + `foreign_ir_sources.json`의 `ir_url` 교체. ★**"조용한 0건"은 실패로 잡히지 않는다** — 이 사각지대를 드러내는 장치는 월요일 다이제스트뿐이다.
- 소스 목록 `foreign_ir_sources.json`.

## Reads
- `foreign_ir_sources.json`

## Writes
- [[store-sources-state]] — sources_state/ + kna_state.json

## Depends on
- [[src-generic-pipeline]] — Generic Source Pipeline (execution/sources/)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `execution/sources/foreign_ir.py`
- `foreign_ir_sources.json`
