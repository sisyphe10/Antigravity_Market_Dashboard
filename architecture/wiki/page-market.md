---
id: "page-market"
name: "market.html (마켓 대시보드)"
domain: "market-global"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: "생성=여러 잡"
status: "active"
code:
  - "execution/create_dashboard.py"
reads:
  - "store-dataset-csv"
  - "store-roc-history"
  - "monthly_returns.json"
writes: []
depends_on:
  - "src-create-dashboard"
alerts: ""
---

# market.html (마켓 대시보드)

**Domain:** 해외 · 매크로 · **Type:** Page · **Runs on:** github · **Schedule (KST):** 생성=여러 잡 · **Status:** active · **Project:** antigravity

시장 데이터 허브. Monthly Returns 표 + Indices/MARKET 동적 차트 + DATA 섹션(ECOS/FRED/KRX/원자재/capex 등 시계열 사이드바).

- DATA 탭 사이드바 3칼럼(Update/Group/Data) 정렬+엑셀필터, 주기 자동판정, 행배경 틴트. 2026-07-16부터 **Data 서브탭이 첫 탭이자 기본값**.
- 소스: `dataset.csv`(대부분 시계열), `monthly_returns.json`.
- `create_dashboard.py` 생성. dataset.csv를 쓰는 거의 모든 잡이 재생성.
- 2026-07-16 **DATA 차트 포맷 표준화**(다수 커밋): Y축 상단 단위 주석 + 눈금은 숫자만, 축 min/max 항상 라벨링에 눈금 8개 상한, 자릿수 밴드별 소수 자리 통일(10 미만 2dp / 1000 미만 1dp / 이상 정수), 금액 시계열 단위 환산(억원→조원, 달러 계열→$억/$B), log 스케일은 5–95% 로그공간 패딩, 우측 패딩=실측 라벨폭+12px. 16:9 비율·굵은 선·norm/log 토글 버튼. Indices/WRAP 차트도 같은 표준으로 retrofit.
- '파생·수급' 그룹(삼성전자·SK하이닉스 파생·수급 + VKOSPI 13종)은 [[src-deriv-daily]]가 적재.
- **RoC² 서브패널(2026-07-29~30)**: DATA 차트에 이격도 패널과 같은 규격으로 보조 캔버스를 추가해 '변화율의 변화율'(기간말 리샘플→RoC¹→전기 차분 %p→3기간 스무딩, RoC¹ 정의는 시리즈 성격에 따라 3갈래)을 표시. 메인+이격도+RoC² 3면 세로 합성·십자선 동기. YoY lag 12개월+MA3 요구로 dataset.csv 12개월 이력만으론 부족한 지수·환율 등은 [[store-roc-history]](월말 백필 `roc_history.csv`)로 보충하고, 판독성이 검증된 화이트리스트 시리즈(`datalake/score_roc2.py` 점수)만 노출. 주기(월/주) 버튼 가용성은 데이터 충분성에 따라 자동 판정.
- DATA 사이드바 별표 즐겨찾기(2026-07-20)는 ts.net에서 [[daemon-watchlist-quoteboard]]의 `/stars` 엔드포인트(`market_stars.json`)에 **서버 저장**돼 기기 간 공유되고, 데몬에 못 닿는 환경(GitHub Pages)에서는 localStorage로 폴백.

## Reads
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)
- [[store-roc-history]] — roc_history.csv (RoC² 월말 백필)
- `monthly_returns.json`

## Writes
- (none)

## Depends on
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)

## Code
- `execution/create_dashboard.py`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/market.html)
