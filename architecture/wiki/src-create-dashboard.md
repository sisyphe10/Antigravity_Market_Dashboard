---
id: "src-create-dashboard"
name: "대시보드 생성기 (create_dashboard.py)"
domain: "ops-infra"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "체인 말단 (여러 잡)"
status: "active"
code:
  - "execution/create_dashboard.py"
reads:
  - "store-dataset-csv"
  - "store-portfolio-data"
  - "store-contribution-data"
  - "store-etf-db"
  - "store-universe-json"
  - "kodex_sectors.json"
writes:
  - "page-index"
  - "page-market"
  - "page-wrap"
  - "page-universe"
  - "page-universe-lab"
  - "page-seibro"
  - "page-featured"
  - "page-hotels"
  - "page-etf"
depends_on:
  - "src-calculate-returns"
  - "src-create-portfolio-tables"
alerts: ""
---

# 대시보드 생성기 (create_dashboard.py)

**Domain:** 운영 · 인프라 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 체인 말단 (여러 잡) · **Status:** active · **Project:** antigravity

생태계의 중앙 렌더러(550KB). dataset.csv·portfolio_data.json·각종 json/db를 읽어 대부분의 라이브 HTML을 한 번에 생성한다.

- 생성: index/market/wrap/universe/universe_lab/seibro/featured/hotels/etf 페이지(등록표 PAGES 기반).
- 거의 모든 GHA/VM 잡의 마지막 스텝으로 호출됨 → 데이터가 바뀌면 여기서 화면에 반영.
- 상단 탭바/폰트(Pretendard)/UI 규칙의 단일 정의처. architecture.html은 이 헬퍼를 수동 미러링해야 함.
- 수정 시 전체 페이지 재생성 후 일관성 확인.

## Reads
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)
- [[store-portfolio-data]] — portfolio_data.json
- [[store-contribution-data]] — contribution_data.json
- [[store-etf-db]] — etf_data.db (ETF 구성종목 SQLite)
- [[store-universe-json]] — universe.json / universe_history.json
- `kodex_sectors.json`

## Writes
- [[page-index]] — index.html (랜딩)
- [[page-market]] — market.html (마켓 대시보드)
- [[page-wrap]] — wrap.html (WRAP 대시보드)
- [[page-universe]] — universe.html (Universe)
- [[page-universe-lab]] — universe_lab.html (Universe Lab)
- [[page-seibro]] — seibro.html (SEIBro)
- [[page-featured]] — featured.html (Featured TOP)
- [[page-hotels]] — hotels.html (호텔 ADR, 동결)
- [[page-etf]] — etf.html (ETF 구성종목)

## Depends on
- [[src-calculate-returns]] — 수익률 계산 (calculate_returns.py)
- [[src-create-portfolio-tables]] — 포트폴리오 표 생성 (create_portfolio_tables.py)

## Code
- `execution/create_dashboard.py`
