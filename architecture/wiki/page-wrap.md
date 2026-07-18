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

- **독립 페이지화(2026-07-12, 'Life WRAP' 리브랜드)**: 팀원 전용 페이지로 분리 — 개인 탭을 nav에서 제거하고, 탭 축을 뒤집어(탭 상단, 섹션 TOC를 탭별 컨텍스추얼 사이드바로) 배치했다. **팀원 공개는 gh-pages 전용**([[web-publish-pages]]) — 개인 대시보드([[web-caddy]] ts.net)에서는 `compose_personal_view.py`가 이 페이지를 아예 제거한다([[web-publish-snapshot]]).
- **좌측 사이드바 폐지 → 가로 스트립 3단(2026-07-18)**: AoE Market 폼에 맞춰 nav를 3단 가로 밴드로 재배치했다. ① **54px 브랜드 바**(`.wrap-topnav`, `Life WRAP` 브랜드 + 우측 `Updated`만), ② **42px 필 스트립**(`.wrap-strip`, sticky) — 5개 WRAP 탭(dashboard/order/공시/기여도/수수료)이 72px topnav에서 이 스트립으로 이동, ③ 스트립 아래 **섹션 TOC**(구 좌측 `.wrap-sidebar`) — 좌측 고정 레일에서 **가로 중앙정렬 사각 필 버튼 줄**로 바뀌었다(`display:flex/flex-wrap`, `공시` 탭은 숨김). 섹션 TOC의 스크롤스파이/그룹전환 **JS는 불변**(레이아웃 CSS만 교체), 본문 좌측 오프셋도 224px→24px로 해제. 
- ★**AoE 다크 nav 통일에서 제외(2026-07-16)**: 개인 뷰 전 페이지가 단일 AoE 다크 topnav로 통일될 때 **wrap.html만 원래의 라이트 nav(흰 배경+알약 탭)를 유지**한다 — 팀원용 페이지라 개인 뷰의 nav 재구성 대상이 아니라는 정책 결정. 생성기의 다크 `TOP_NAV_CSS`를 `.wrap-topnav` 스코프에서 되돌리는 방식이라, **nav 스타일을 손댈 때 이 갈래를 깨기 쉽다**(브랜드 바·스트립·섹션 TOC sticky·스크롤스파이 기준선이 서로 물려 있음).
- PORTFOLIO 종목표·수익률·차트는 `portfolio_data.json`+`Wrap_NAV.xlsx` 계산 산출을 소비(최상위 `_` prefix 메타 키 규약은 [[store-portfolio-data]]).
- **CHART 자가복구 2중 안전망(2026-07-16)**: 이 페이지는 비밀번호 게이트(`pw-hidden`) 뒤에 있어 **차트가 숨겨진 상태(height 0)에서 생성되면 축 눈금이 퇴화한 채 굳는다**(Chart.js). ① 250ms×40회(10초) 가시성 폴링 — 캔버스가 실제 표시되는 순간 `resize()+update('none')` 1회. ② 폴링 10초를 넘겨 비밀번호를 늦게 푸는 경우를 폴링이 놓치므로, `checkPw()` 성공 경로가 `_wrapHealKick()`을 직접 호출. 폴링=best-effort·시간제한, unlock 콜백=이벤트 기반 확정 트리거로 서로를 메운다.
  - ★사고 사례: nav 스타일 커밋(`1733fdca`)이 **stale 워킹트리로 파일을 통째 덮어써 3분 전의 unlock heal-kick을 조용히 삭제** → `1e4c1732`로 재적용. 자동 커밋 잡이 상시 도는 프로덕션 트리에서 오래된 트리 기반 전체 덮어쓰기가 무관한 수정을 되돌리는 알려진 실패 모드다.
- Order 탭: 임시저장(회색, `orders/pending_orders.json`)→최종저장(초록, finalize 트리거). 기여도 탭은 `contribution_data.json` 런타임 fetch. 주문 접수는 웹(wrap.html→GitHub Contents API) 유지 — 별도 주문봇 스캐폴드는 폐기됐다.
- **Order 통합 매트릭스(2026-07-13)**: 포트별 카드 → 합집합 행(종목)×포트 열 매트릭스 VIEW로 개편. 7개 개별 컬럼은 `wrap_config.order_matrix_columns()`로 동적 생성, 개별키 실저장, 일반형 동기화 토글(삼성 트루밸류 컬럼 정렬), cash row 포함. pending 스키마·save/finalize/email/excel 계층은 불변(VIEW 층만 교체). 정본 디자인은 은퇴한 test 페이지에서 1:1 이식.
- **매트릭스 입력 보조(2026-07-14)**: 일반형에 이어 **전환형 동기화** 토글 추가(`syncToggle`/`syncToggleTarget` 2개 병렬) — 같은 그룹 열에 값을 일괄 전파. Tab 네비게이션은 동기화가 켜진 그룹의 **대표 열 1개만 순회**(`_mtxTabStops`)하고 추천사유는 별도 체인 — 수십 종목×7포트 수기 입력의 키 이동 부담을 줄인다.
- **ORDER 롤오버 게이트(2026-07-14)**: '변경전' 기준선은 D-1(`weight_prev`)이나, `portfolio_data.json`의 `_price_asof`가 오늘보다 이르면(16:00 재생성 전 오전) 어제 확정분을 baseline으로 흡수해 변경 없음(검정)으로 표시(`_orderSnapshotStale`). 자정을 넘긴 확정 주문이 이튿날 오전까지 '변동'으로 남던 것을 해소.
- **Email 탭 발송 요청(2026-07-13)**: [컴플 메일]/[증권사 메일] 2버튼 각자 모달, 첨부 base64 생성(900KB 가드)+미리보기(하이웍스 실서명 HTML). [메일 발송 요청]이 `orders/email_send_request.json`을 Contents API로 기록 → [[timer-advisory-emails]] 60초 폴러가 하이웍스 SMTP로 발송. (컴플라이언스 선발송 게이팅은 사용자 지시로 제거.)
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
