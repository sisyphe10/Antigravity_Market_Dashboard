---
id: "page-featured"
name: "featured.html (Featured TOP)"
domain: "portfolio-wrap"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: "생성=Featured 잡(16:20/18:30/08:30)"
status: "active"
code:
  - "execution/create_featured_v2.py"
  - "execution/create_dashboard.py"
  - "execution/fetch_featured_news.py"
reads:
  - "store-featured-data"
  - "featured_news.json"
writes: []
depends_on:
  - "src-create-dashboard"
  - "bot-sisyphe"
  - "infra-headless-llm"
alerts: ""
---

# featured.html (Featured TOP)

**Domain:** 포트폴리오 · WRAP · **Type:** Page · **Runs on:** github · **Schedule (KST):** 생성=Featured 잡(16:20/18:30/08:30) · **Status:** active · **Project:** antigravity

KRX 거래대금/시총/상승률 TOP 종목 페이지.

- **v2 생성기로 전환(2026-08-05, 12.9MB→약 25KB transferred)**: featured.html이 이제 `create_featured_v2.py`로 렌더된다. 구 생성기는 `featured_data.json` 165일치(60,377행)를 통째로 인라인 임베드해 12.9MB였는데 화면은 하루치(약 260행)만 쓴다. v2는 데이터/HTML을 분리해 `featured_v2/`(manifest.json·series.json·daily/YYYY-MM-DD.json)에 두고 HTML은 셸만 남기며, 인사이트(연속 등장·신규 진입 등)를 생성기에서 사전계산한다. `featured_v2/` 산출물은 **git 미추적**(추적하면 다시 매일 수 MB씩 히스토리에 쌓임) — `publish_snapshot.sh` 화이트리스트로 ts.net 게시, 정본 nav를 붙여 스냅숏 컴포저가 수용. 구 생성기는 롤백용 `featured_legacy.html`을 계속 쓴다.
- 소스: Sisyphe-Bot Featured 잡(16:20 1차/18:30 2차/08:30 익일 복구)이 KIS 배치로 `featured_data.json`을 만들고 v2 생성기가 재생성.
- 20일 신고가는 별도 `newhigh_20d.json`(15:50 타이머).
- `fetch_featured_news.py`가 섹터별 뉴스를 LLM으로 종합 요약해 `featured_news.json`을 만든다. ★**2026-08-20 구독 headless 이관**([[infra-headless-llm]], `FEATURED_NEWS_LLM` 기본 `headless`·롤백 `api`) — 요약 실패는 빈 문자열이라 페이지는 요약 없이도 렌더된다.
- 18:30 2차가 etf.html도 함께 재생성.

## Reads
- [[store-featured-data]] — featured_data.json / newhigh_20d.json
- `featured_news.json`

## Writes
- (none)

## Depends on
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)
- [[bot-sisyphe]] — Sisyphe-Bot (펀드/일상 텔레그램 봇)
- [[infra-headless-llm]] — 구독 LLM 백엔드 (headless claude · codex 폴백)

## Code
- `execution/create_featured_v2.py`
- `execution/create_dashboard.py`
- `execution/fetch_featured_news.py`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/featured.html)
