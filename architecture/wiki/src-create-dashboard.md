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
  - "hotel_adr.csv"
writes:
  - "page-index"
  - "page-market"
  - "page-wrap"
  - "page-universe"
  - "page-seibro"
  - "page-featured"
  - "page-etf"
depends_on:
  - "src-calculate-returns"
  - "src-create-portfolio-tables"
  - "src-chart-core"
alerts: ""
---

# 대시보드 생성기 (create_dashboard.py)

**Domain:** 운영 · 인프라 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 체인 말단 (여러 잡) · **Status:** active · **Project:** antigravity

생태계의 중앙 렌더러(550KB). dataset.csv·portfolio_data.json·각종 json/db를 읽어 대부분의 라이브 HTML을 한 번에 생성한다.

- 생성: index/market/wrap/universe/seibro/featured_legacy/etf 7개 페이지(각 섹션 빌더가 직접 write — 등록표 방식 아님, 아래 실측 정정 참조).
- 거의 모든 GHA/VM 잡의 마지막 스텝으로 호출됨 → 데이터가 바뀌면 여기서 화면에 반영.
- 상단 네비·다크/WRAP 팔레트·Pretendard·캡처 JS는 execution/nav_style.py 정본에서 import (2026-07-26 통일 — 수동 미러링 폐지).
- 차트 렌더 JS는 [[src-chart-core]] `chart_core/dist/aoe_chart.js` 를 빌드타임 인라인 임베드 (2026-08-02, `_load_aoe_core_js()` — 모듈 로드 시 sha 검증, 부재/불일치는 기동 치명 실패). `AOE_CHART_LEGACY=1` 이면 동결 렌더러(execution/legacy_chart_renderers.py)로 롤백.
- **표·차트 Copy 버튼(클립보드 PNG, 2026-08-09)**: Download 왼쪽에 Copy(청록 `#0891b2`) 버튼을 병설. 캡처 헬퍼(`downloadElementImage`·`_univCapture`)에 `{blob:true}` 옵션을 추가해 동일 html2canvas 결과를 Blob으로 되돌리고, `navigator.clipboard.write`에는 **Promise 상태의 Blob**을 그대로 넘겨 클릭 제스처를 유지한다(await로 Blob을 먼저 받아 write 하면 브라우저가 사용자 제스처 소실로 거부). ClipboardItem 미지원 브라우저는 alert 안내, 성공/실패는 버튼 라벨(`Copied ✓`/`Copy failed`, 1.5초 후 복원)로 표시. 소비 화면 = [[page-market]] Monthly Returns · [[page-universe]] 3탭 · [[page-universe-lab]] 3패널.
- **DATA 업데이트 추적 상태를 산출물 자신에 실어 나름(2026-08-17)**: '최근 업데이트' 배지([[page-market]])는 시리즈별 마지막 유효 관측(날짜·값)과 그 값이 바뀐 날을 기억해야 하는데, 별도 상태 파일·잡 수정 없이 **직전 `market.html`에 임베드된 `<script id="cmbUpdState" type="application/json">`를 읽어 비교하고 새 상태를 다시 임베드**하는 방식을 택했다. 수집 잡들이 어차피 market.html을 커밋하고 잡 시작이 `reset --hard`라 상태가 자연히 최신 origin본을 따라간다(별도 정본을 두면 오히려 어긋난다). 파싱 실패는 경고 후 무배지 진행, 첫 빌드(상태 없음)는 전량 무배지로 시작해 다음 변동부터 점등 — 즉 **배지는 재생성 이력에 의존하는 파생 정보**이지 데이터 정본이 아니다.
- 수정 시 전체 페이지 재생성 후 일관성 확인.
- ★**생성 목록 실측 정정(2026-08-17)**: 이 스크립트가 실제로 파일로 쓰는 것은 **`market` · `index` · `wrap` · `universe` · `seibro` · `featured_legacy` · `etf` 7개뿐**이다(소스의 `open(...,'w')` 전수). 종전 문서가 적던 "PAGES 등록표 기반 일괄 생성"은 실체가 없다.
  - `universe_lab.html` — 생성기 소스에 문자열조차 없다. 손으로 유지하는 정적 페이지([[page-universe-lab]]).
  - `hotels.html` — 마찬가지로 쓰지 않는다. 이 스크립트가 `hotel_adr.csv`를 읽긴 하지만 용도는 **도시별 ADR 평균을 빌드타임에 dataset으로 inject해 [[page-market]] DATA 차트의 `Hotel {city}` 시리즈로 띄우는 것**(호텔 리스트는 사이드바 title 툴팁)이지 [[page-hotels]] 생성이 아니다. 그 페이지는 수집 은퇴([[timer-hotel-adr]]) 이후 동결된 정적 HTML.
  - `featured.html`의 정본 생성기도 2026-08-05부터 `create_featured_v2.py`이고 이쪽은 구 `featured_legacy.html`만 쓴다([[page-featured]]).
  - → **생성기를 고쳤다고 이 3개 페이지가 따라오지 않는다.** 양식·nav 규격을 바꿀 때 자동 전파 범위는 위 7개까지다.

## Reads
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)
- [[store-portfolio-data]] — portfolio_data.json
- [[store-contribution-data]] — contribution_data.json
- [[store-etf-db]] — etf_data.db (ETF 구성종목 SQLite)
- [[store-universe-json]] — universe.json / universe_history.json
- `kodex_sectors.json`
- `hotel_adr.csv`

## Writes
- [[page-index]] — index.html (랜딩)
- [[page-market]] — market.html (마켓 대시보드)
- [[page-wrap]] — wrap.html (WRAP 대시보드)
- [[page-universe]] — universe.html (Universe)
- [[page-seibro]] — seibro.html (SEIBro)
- [[page-featured]] — featured.html (Featured TOP)
- [[page-etf]] — etf.html (ETF 구성종목)

## Depends on
- [[src-calculate-returns]] — 수익률 계산 (calculate_returns.py)
- [[src-create-portfolio-tables]] — 포트폴리오 표 생성 (create_portfolio_tables.py)
- [[src-chart-core]] — AoE 차트 코어 (chart_core/aoe_chart.js)

## Code
- `execution/create_dashboard.py`
