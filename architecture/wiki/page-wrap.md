---
id: "page-wrap"
name: "wrap.html (WRAP 대시보드)"
domain: "portfolio-wrap"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: "생성=여러 잡"
status: "active"
code:
  - "execution/create_dashboard.py"
  - "execution/wrap_config.py"
reads:
  - "store-portfolio-data"
  - "store-contribution-data"
  - "store-orders-pending"
writes: []
depends_on:
  - "src-create-dashboard"
  - "src-create-portfolio-tables"
  - "src-create-contribution-data"
alerts: ""
---

# wrap.html (WRAP 대시보드)

**Domain:** 포트폴리오 · WRAP · **Type:** Page · **Runs on:** github · **Schedule (KST):** 생성=여러 잡 · **Status:** active · **Project:** antigravity

랩 상품 운용 대시보드. Dashboard/공시/Order/AUM/수수료/기여도 탭 묶음. 자문사 실무의 중심 화면.

- **독립 페이지화(2026-07-12, 'Life WRAP' 리브랜드)**: 팀원 전용 페이지로 분리 — 개인 탭을 nav에서 제거하고, 탭 축을 뒤집어(탭 상단, 섹션 TOC 좌측) 탭별 컨텍스추얼 사이드바를 둔다. **팀원 공개는 gh-pages 전용**([[web-publish-pages]]) — 개인 대시보드([[web-caddy]] ts.net)에는 이 페이지가 빠지고 대신 Sisyphe 탭이 들어간다.
- PORTFOLIO 종목표·수익률·차트는 `portfolio_data.json`+`Wrap_NAV.xlsx` 계산 산출을 소비.
- Order 탭: 임시저장(회색, `orders/pending_orders.json`)→최종저장(초록, finalize 트리거). 기여도 탭은 `contribution_data.json` 런타임 fetch. 주문 접수는 웹(wrap.html→GitHub Contents API) 유지 — 별도 주문봇 스캐폴드는 폐기됐다.
- 증권사·상품 정의는 단일 레지스트리(`execution/wrap_config.py`)에서 파생.
- `create_dashboard.py` 생성. finalize/recalc가 주 재생성원.

## Reads
- [[store-portfolio-data]] — portfolio_data.json
- [[store-contribution-data]] — contribution_data.json
- [[store-orders-pending]] — orders/ (pending_orders · aum_pending)

## Writes
- (none)

## Depends on
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)
- [[src-create-portfolio-tables]] — 포트폴리오 표 생성 (create_portfolio_tables.py)
- [[src-create-contribution-data]] — 기여도 데이터 (create_contribution_data.py)

## Code
- `execution/create_dashboard.py`
- `execution/wrap_config.py`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/wrap.html)
