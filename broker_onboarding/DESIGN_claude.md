# 확장형 증권사 온보딩 — Claude 독립 설계안

> 사용자 결정(2026-06-25): ① 단일 레지스트리(확장형) ② 한투 일반형 = 합산 그룹 합류 ③ 인프라 지금 + 상품은 출시일.
> codex 독립 설계와 취합해 최종 확정 예정.

## 1. 레지스트리 위치·형식 — `execution/wrap_config.py` (Python 모듈)
근거:
- `execution/config.py` 공유 설정 모듈 선례 존재 → 컨벤션 일치(규칙 8).
- 소비자 8개 전부 Python → JSON 파싱 불필요. 모듈에 **파생 헬퍼 함수**를 함께 둘 수 있음(JSON은 불가).
- import 경로: execution/ 스크립트는 `import wrap_config` 직행(sys.path[0]=execution). root 스크립트(calculate_wrap_nav·calculate_returns·add_aum)는 `sys.path.insert(0, .../execution)` 후 import — calculate_wrap_nav는 **이미** L249에서 추가. 나머지 2개는 2줄 부트스트랩 추가.
- create_dashboard.py가 emit하는 **JS(ORDER_PORTFOLIOS·GENERAL·BROKER_ORDER)**: py 레지스트리에서 `json.dumps`로 직렬화해 주입 → JS도 단일 출처화.

## 2. 스키마
```python
# execution/wrap_config.py
BROKERAGES = [
    {"code": "삼성", "color": "#1428A0", "order": 0},
    {"code": "NH",   "color": "#0072CE", "order": 1},
    {"code": "DB",   "color": "#00854A", "order": 2},
    {"code": "한투", "color": "#____",   "order": 3},   # 색 출시 전 확정
]

# 상품 1건 = 1 엔트리. 증권사/상품 추가 = 여기 append (+자문지 템플릿 파일 1개)
PRODUCTS = [
  {
    "nav_key":   "Value ESG",        # 기준가/수익률/NEW 시트 컬럼·상품명 (데이터 조인 키)
    "aum_name":  "다이내믹밸류",       # ★AUM 시트 '상품명' (nav_key와 다를 수 있음 — NH 사례 검증 필요)
    "broker":    "NH",
    "type":      "general",          # general | target
    "display":   "NH Value ESG",     # 표/차트 표시명
    "base_price": 1980.49,
    "start_date": "2025-12-30",
    "end_date":   None,              # 청산 시 'YYYY-MM-DD'
    "ytd_base":   "2025-12-30",
    "color":      "#0072CE",         # 차트 계열색 (기본=broker color)
    "advisory_template": "자문지/라이프자산운용_라이프 다이내믹밸류_일반형 _2026.4.27.xlsx",
    "group":      "GENERAL_OPEN",    # 결합 그룹 id (None=단독 표시)
    "active":     True,
  },
  # ... 삼성 트루밸류, DB 개방형 랩 ...
]

# 결합 그룹: 동일 종목/비중을 공유해 한 줄로 표시
GROUPS = {
  "GENERAL_OPEN": {"use": "트루밸류"},   # combined명은 멤버 broker order로 자동 생성
}
```

### ★ 페어/단독 일반화 — 핵심 설계
"NH/DB 페어"라는 특수 개념을 없애고 **`group` id 하나**로 통합:
- 일반형 3사(→4사 한투): 모두 `group="GENERAL_OPEN"`. combined = "삼성 트루밸류 / NH Value ESG / DB 개방형 / 한투 ○○" 자동.
- NH 5호 + DB 6차: 동일 포트면 같은 `group="TARGET_xxxx"`. combined = "NH 목표전환형 5호 / DB 목표전환형 6차" 자동.
- 한투 목표전환형 단독: `group=None` → 개별 표시(PORTFOLIO_GROUPS else 분기). 페어 강제 없음.
- 그룹 멤버 수 1·2·3·4 무관 — `combined_display(group)`가 broker order 정렬로 생성.

### ★ 데이터 정합성 — 실측 확정 (2026-06-25, Wrap_NAV.xlsx)
- **NH만 nav_key≠aum_name 확정**: AUM 시트=`다이내믹밸류`, NEW/기준가/수익률=`Value ESG`. 삼성(트루밸류)·DB(개방형 랩)는 일치. 목표전환형은 전부 일치(`N호`/`N차`).
  → 레지스트리는 **nav_key/aum_name 분리 필드** 필수.
- **소비자별 표시 라벨 상이(확정)**: chart_series는 `'NH Value ESG'`(L2612), 월별수익률 표는 `'NH 다이내믹밸류 일반형'`(L3554). → `display`(canonical) + 선택적 `monthly_label` 필드.
- **수익률 표 큐레이션 상이(확정)**: `create_wrap_returns_table`(L3693)은 일반형 중 **`삼성 트루밸류` 1개만**(그룹 대표, 3종 동일수익률) + 활성 target. 월별표(L3551)는 일반형 3종 개별. → 헬퍼가 소비자별 선택 로직을 각각 캡슐화(`monthly_returns_products()` vs `wrap_returns_items()`).
- chart_series/chart_colors에는 KOSPI(`#000000`)·KOSDAQ(`#666666`) 벤치마크 포함 — 레지스트리 파생 시 벤치마크 상수 합류.
- 현재 활성 일반형 3종만(목표전환형 전부 청산). AUM 최신 2026-06-24: 삼성 538억 / NH 135억 / DB 188억.

## 3. 파생 헬퍼 API (소비자가 호출)
```python
active()                      # active=True 상품 리스트
by_key(nav_key)               # 단건
brokerages_ordered()          # order 정렬
broker_color(code)            # → hex (없으면 #888)
combined_display(group_id)    # "A / B / C" (broker order)
group_members(group_id)       # 상품 리스트
group_use(group_id)           # 대표 nav_key

# 분산 구조 대체 파생물
portfolio_config()            # {nav_key:{base_price,start_date[,end_date]}}  (general+target active)
ytd_base_dates()              # {nav_key: ytd_base}
display_names()               # {nav_key: display}  (그룹은 combined로 override)
chart_series()                # [(display_or_combined, nav_key)] 중복 그룹 1회
chart_colors()                # {display: color}
broker_colors()               # {broker: color}
wrap_keywords()               # [display, nav_key, aum_name ...] 카테고리 인식용
fixed_products()              # {(broker,'일반형'): nav_key|aum_name}  ← add_aum
active_target_transform()     # {broker: nav_key}  type=target & active  ← add_aum
excluded_portfolios()         # 비활성(과거 청산) nav_key 집합
monthly_returns_products()    # [(label, nav_key)]  KOSPI/KOSDAQ + general
order_portfolios()            # ORDER_PORTFOLIOS 구조 (그룹 카드 + target 카드 각각)
general_combined_name()       # GENERAL 단일 문자열 (JS 4곳 대체)
target_tabs()                 # 활성 target display 리스트
portfolio_names()             # draw_wrap_charts {nav_key: display}
nav_map()                     # daily_portfolio_report {display: nav_key}
```

## 4. 소비자별 치환 (≈20 터치포인트)
| 파일 | 기존 하드코딩 | 치환 |
|---|---|---|
| calculate_wrap_nav.py | portfolio_config | `wrap_config.portfolio_config()` |
| calculate_returns.py | ytd_base_dates | `ytd_base_dates()` |
| create_contribution_data.py | portfolio_config | `portfolio_config()` |
| create_portfolio_tables.py | PORTFOLIO_DISPLAY_NAMES / EXCLUDED / PORTFOLIO_GROUPS | `display_names()` / `excluded_portfolios()` / GROUPS 파생 |
| create_dashboard.py | wrap_keywords / chart_series / chart_colors / broker_colors×2 / products×2 / ORDER_PORTFOLIOS / GENERAL×4 / BROKER_ORDER / TARGET_TABS | 각 헬퍼 |
| daily_portfolio_report.py | nav_map / display_names / product 리스트×2 | `nav_map()` / `display_names()` |
| draw_wrap_charts.py | PORTFOLIO_NAMES | `portfolio_names()` |
| add_aum.py | FIXED_PRODUCTS / ACTIVE_TARGET_TRANSFORM | `fixed_products()` / `active_target_transform()` |

## 5. GENERAL 단일 출처화
JS 4곳 `var GENERAL = '...'` → create_dashboard가 `GENERAL = wrap_config.general_combined_name()`을 1회 계산해 JS에 `const GENERAL = {json.dumps};`로 주입, 4곳이 동일 const 참조. 한투 합류 시 자동 갱신.

## 6. 회귀검증 (인프라 전환 = 동작 불변 증명)
활성 상품 집합이 그대로(3사 일반형, target 0)이므로 **파생물이 기존 리터럴과 동일**해야 함.
1. **단위 동등성**: `assert chart_series() == [('삼성 트루밸류','트루밸류'),('NH Value ESG','Value ESG'),('DB 개방형','개방형 랩')]` 식으로 모든 헬퍼 출력 == 기존 하드코딩 리터럴. (별도 test 스크립트)
2. **산출물 diff**: 전환 전 `wrap.html`/`portfolio_data.json` 스냅샷 → 전환 후 재생성 → **config 파생 라인(차트 계열·색·ORDER_PORTFOLIOS·GENERAL·AUM 색)만 추출 비교**해 동일 확인(타임스탬프·라이브 시세 라인 제외).
3. 4개 마커 grep 유지 + 전 .py `compile()`.

## 7. 시퀀싱
- **지금**: wrap_config.py 작성(현 활성 3사만) → 8스크립트 전환 → 동등성·diff 검증 → 커밋. **상품 무추가**.
- **6/29 NH 5호 / 7/1 DB 6차**: target 엔트리 append(group 공유 여부=동일포트면 페어 그룹) + 자문지 + NEW + AUM → 체인.
- **7/2 한투 지속형**: general 엔트리 append(group=GENERAL_OPEN) + 한투 color 확정 + 자문지 + NEW + AUM → 체인. ★combined명 4사로 자동 확장 확인.
- **7/8 한투 목표전환형**: target 엔트리 append(group=None 단독) + 자문지 + NEW + AUM → 체인.
- 미래 상품 미리 넣지 않음(데이터 없는 상품 NAV 파손 회피).

## 8. 미해결·리스크
- NH aum_name/nav_key 불일치 실측(§2 함정).
- target 페어를 group으로 묶을 때 `use`(대표 포트) 선정 — 동일 종목/비중 전제 깨지면 분리.
- ORDER_PORTFOLIOS의 자문지 경로·newSheetTargets는 출시 전 파일/매핑 확정 필요(인프라 단계엔 현 3사 자문지 그대로 재현).
- create_dashboard.py가 거대(8500+줄) → 전환 시 grep 재확인으로 누락 0.
