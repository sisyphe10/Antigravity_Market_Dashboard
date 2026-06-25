# 증권사 온보딩 — 코드 감사 & 확장형 설계 근거

> 목적: 한투(한국투자증권) 추가를 계기로, **증권사 추가 = 설정 1곳만 수정**하는 확장형 구조로 전환.
> 미래에 또 다른 증권사가 추가될 수 있음(사용자 명시, 2026-06-25). 한투를 첫 소비자로 삼아 설계.

## 깨지는 전제 2개
1. **일반형 = NH/DB/삼성 3사 고정** (다이내믹밸류·개방형 랩·트루밸류)
2. **목표전환형 = NH/DB 항상 페어** (동시 출시·청산)

한투는 ① 지속형(일반형) 신규 → 전제1 붕괴, ② 목표전환형 **단독 시리즈** → 전제2 붕괴.

## 출시 일정 (today 2026-06-25)
- NH 목표전환형 5호 — 6/29 (페어성, 기존 SOP)
- DB 목표전환형 6차 — 7/1 (페어성, 기존 SOP)
- 한투 지속형(일반형) — 7/2 (★신규 증권사)
- 한투 목표전환형 — 7/8 (★단독 시리즈)

---

## 터치포인트 (파일별, 줄번호는 근사 — 적용 시 git grep 재확인)

### 분류
- 🟢 **단순 추가** (dict/list 엔트리) — 증권사 추가 시 1줄
- 🟡 **구조적** (그룹·페어·JS 하드코딩 문자열) — 설계 판단 필요
- ✅ **이미 동적/한투 대응됨** — 변경 불필요

| 파일 | 위치(변수) | 분류 | 비고 |
|---|---|---|---|
| `calculate_wrap_nav.py` | `portfolio_config` (~L40) | 🟢 | base_price+start_date. 청산 시 end_date |
| `calculate_returns.py` | `ytd_base_dates` (~L12) | 🟢 | YTD=개시일 |
| `execution/create_contribution_data.py` | `portfolio_config` (~L44) | 🟢 | calculate_wrap_nav와 동일값. 별도 실행 |
| `execution/create_portfolio_tables.py` | `PORTFOLIO_DISPLAY_NAMES` (L21) | 🟢 | 상품명→표시명 |
| `execution/create_portfolio_tables.py` | `EXCLUDED_PORTFOLIOS` (L35) | 🟢 | 청산 시 추가 |
| `execution/create_portfolio_tables.py` | `PORTFOLIO_GROUPS` (L371) | 🟡 | 일반형 합산 그룹·페어. 매칭은 느슨(검증됨) |
| `execution/create_dashboard.py` | `wrap_keywords` (~L380) | 🟢 | 카테고리 인식 |
| `execution/create_dashboard.py` | `chart_series`+`chart_colors` (~L2610) | 🟢 | 차트 계열·색 |
| `execution/create_dashboard.py` | `products` (월별수익률, ~L3539) | 🟢 | |
| `execution/create_dashboard.py` | `products` (수익률표, ~L3696) | 🟢 | SOP 함정: chart_series와 별개 2번째 |
| `execution/create_dashboard.py` | `broker_colors` ×2 (L3061, L3279) | 🟡→🟢 | AUM 표·누적차트 색. 로직은 동적(검증됨), 색만 추가 |
| `execution/create_dashboard.py` | `ORDER_PORTFOLIOS` (L3878) | 🟡 | Order 탭 카드 + 자문지 경로 + newSheetTargets |
| `execution/create_dashboard.py` | `BROKER_ORDER` JS (~L4065) | 🟢 | Email 정렬 {삼성:0,NH:1,DB:2} |
| `execution/create_dashboard.py` | `GENERAL` JS 하드코딩 ×4 (L4057/4168/4209/4285) | 🟡 | **제일 취약**: 일반형 결합명 문자열 |
| `execution/create_dashboard.py` | `TARGET_TABS` (~L4167) | 🟡 | 목표전환형 이메일 양식 탭 |
| `execution/daily_portfolio_report.py` | `nav_map`(L110)·`display_names`(L305)·product리스트×2(L144,L317) | 🟢 | 텔레그램 리포트 |
| `execution/draw_wrap_charts.py` | `PORTFOLIO_NAMES` (~L40) | 🟢 | matplotlib 차트 |
| `add_aum.py` | `FIXED_PRODUCTS` (L39) | 🟢 | (증권사,일반형)→상품명 |
| `add_aum.py` | `ACTIVE_TARGET_TRANSFORM` (L45) | 🟢 | (증권사)→활성 회차명 |
| `add_fee_revenue.py` | `BROKERS`,`broker_order` | ✅ | 한투 이미 포함 |
| `execution/create_dashboard.py` | `_REV_BROKER_ORDER`(L5295)·JS(L5329) | ✅ | 한투 이미 포함 |

### 검증된 핵심 사실
- **AUM 표/누적 AUM 차트는 `str.contains('목표전환형')` 동적** → 단독 한투 목표전환형도 자동 편입. broker_colors만 색 보강 필요.
- **PORTFOLIO_GROUPS 매칭은 느슨** → 단독 상품은 `else`로 빠져 개별 표시(정상 작동). 합산은 sources에 추가할 때만.
- **GENERAL 결합명은 JS 4곳에 동일 문자열 하드코딩** → 일반형 그룹 구성이 바뀌면 4곳 동기 수정 필요(단일 출처 부재가 근본 취약점).
- 목표전환형 "페어 강제" 로직 코드 부재 → 단독 시리즈는 대부분 무변경 동작. Order 카드/이메일 GENERAL만 인지 필요.

---

## 확장형 설계 방향 (초안 — codex 설계와 취합 예정)
**단일 출처 레지스트리** 도입: 증권사·상품 정의를 1곳(JSON 또는 py 모듈)에 두고 8개 스크립트가 읽음.
증권사 추가 = 레지스트리 1엔트리(+자문지 템플릿 1개). 분산된 dict/list는 레지스트리에서 파생 생성.

### 안전 분리 (출시 4건이 13일 내 → 파이프라인 조기 파손 위험)
- **인프라 리팩토링(지금)**: 레지스트리 도입 + 8스크립트 전환. **상품 추가 없이** 재생성 → 기존 HTML/JSON과 **바이트 동일** 회귀검증.
- **상품 추가(각 출시일)**: 레지스트리 1엔트리 + 자문지 + NEW시트 + AUM → 체인 실행.
- 데이터 없는 미래 상품을 미리 넣으면 NAV 계산이 깨질 수 있으므로 **분리 필수**.
