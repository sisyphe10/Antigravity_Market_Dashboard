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
- **Monthly Returns 표(2026-08-09)**: Download 왼쪽에 Copy 버튼(클립보드 PNG, [[src-create-dashboard]] 캡처 헬퍼 공용). 진행 연도 YTD 행에 연도 라벨을 명시 — 기본값 `-`가 찍혀 '- YTD'로 보이던 표기 수정. 연도/월 라벨 셀 배경을 `#262b32`로 상향.
- **DATA '최근 업데이트' 배지 + upd 퀵필터(2026-08-17)**: 사이드바 ★ 칼럼이 즐겨찾기 외에 **최근 7일 안에 실제로 새 관측이 들어온 시리즈**를 에메랄드그린(`#4ade80`) ★로 표시한다(`.cmb-star.upd`, title=갱신일). 대상 주기는 처음 Monthly 이상(rank≥2)이었다가 **당일 사용자 확정으로 Weekly 포함(rank≥1)** — 주간물은 주기 특성상 배지가 거의 상시 점등될 수 있음을 감수한 선택. 즐겨찾기 시안(`.on`)이 CSS 뒤에 와 항상 우선한다. 짝을 이뤄 사이드바 퀵필터 줄에 두 번째 ★ 버튼(`data-qv="upd"`)이 생겨 배지 점등분만 추려 볼 수 있고, 두 ★ 버튼은 **항상 채움색**(watchlist=시안 / update=에메랄드)으로 식별하고 선택 상태는 테두리+볼드로 구분한다(다크 게시본 대응은 [[web-publish-snapshot]]).
- **DATA 사이드 표 폭 고정(2026-08-17)**: 퀵필터로 행을 숨길 때마다 `table-layout:auto`가 칼럼·호스트 폭을 재계산해 표가 미세하게 움직이던 문제(실측 817→803px)를 `cmbFreezeSideLayout()`으로 고정 — 전 행이 보이는 자연 상태에서 실측한 뒤 폭을 colgroup에 박고 `fixed`로 전환, 테이블·호스트 폭도 px로 못박는다. 재측정은 **필터가 없을 때만**(숨은 행 기준 폭이 박히는 것 방지) 리사이즈·폰트 로드·탭 표시(ResizeObserver) 시점에 수행. ★함정: `fixed`에서는 `display:none`인 Unit 칼럼이 col 매핑을 한 칸 밀어 Chg가 0px로 붕괴 → **보이는 칼럼 순서로 압축 배정**해야 한다. auto 유지 대안 2종은 실측 폐기(colgroup 최소폭=Chrome auto가 col width 무시 / th 지정폭=여분 폭 재분배가 콘텐츠 의존이라 ±2px 잔여 드리프트). 5차 시도만에 드리프트 0 확정.
- **DATA 차트 y축 정렬(2026-08-21)**: ① 눈금 자릿수를 끝값 라벨과 같은 밴드로 패딩(MLC 64Gb 축 = 6.2/9.0/15.0/…/61.7, SLC 2Gb 축 = 1.90/…/4.93 — 종전엔 `9`·`3` 처럼 정수 눈금이 섞였다). ② 좌 y축 폭을 60px로 고정(clamp-up)해 시리즈를 갈아끼워도 플롯 좌변이 흔들리지 않게 하고, 라벨-축선 간격은 5px. 늘어난 축 폭을 상쇄하려 차트 카드(`cmbChartCard`) **좌측 패딩만 20→10px**(나머지 세 변 20px 유지). 규격 정본은 [[src-chart-core]](`view.yUniformWidth`) — DATA가 이 옵션의 유일한 소비자다.
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
