# 증권사·상품 출시 플레이북 (레지스트리 기반)

> 2026-06-25 인프라 리팩토링 완료 후 기준. **증권사/상품 추가 = `execution/wrap_config.py` 엔트리 추가 + 자문지 + Wrap_NAV.xlsx(NEW·AUM)**.
> 기존 "8개 파일 14곳 수정" SOP는 폐기 — 이제 1곳(레지스트리)이 모든 파생물을 생성한다.

## 공통 출시 절차
1. **`execution/wrap_config.py`** 편집:
   - 신규 증권사면 `BROKERS` 에 `Broker(code, color, order)` 1건.
   - `PRODUCTS` 에 `Product(...)` 1건 (`active=True`, `keep_in_nav=True`, `end_date=None`).
   - 페어로 묶어 표시할 상품끼리는 같은 `group` id (단독은 `group=None`).
2. **자문지/** 폴더에 `advisory_template` 파일 1개 (**필수 — None 금지**. 없으면 Email/Order 자문지 다운로드가 안 생김. 직전 회차 자문지 복사 → 회차명/날짜만 바꿔 경로 주입).
3. **Wrap_NAV.xlsx**: `NEW` 시트 종목(증권사/상품명=nav_key) + `AUM` 시트 개시 AUM(증권사/상품명=aum_name).
4. 검증: `python execution/wrap_config.py` (validate 경고 0 확인 — 개시일 도래 시 NEW/AUM/자문지 존재 강제 점검).
5. 체인 실행: `calculate_wrap_nav.py → calculate_returns.py → execution/create_portfolio_tables.py → execution/create_dashboard.py` + (기여도) `execution/create_contribution_data.py`.
6. `wrap.html` 마커 확인 → 푸시.

## 청산
해당 `Product`: `active=False` + `end_date='YYYY-MM-DD'` 기입. `keep_in_nav`는 청산 직후 한동안 `True` 유지(컬럼 완결), 충분히 지나면 `False`.
→ `EXCLUDED_PORTFOLIOS`·차트·Order 카드·AUM 표에서 자동 제외, `기준가/수익률/NEW/AUM` 데이터는 보존.

---

## ★ 출시별 사전 작성 엔트리 (개시 AUM·색상·자문지 파일명·상품명은 ✦표시 = 출시 직전 확인)

### 1) NH 목표전환형 5호 — 2026-06-29
```python
Product(broker='NH', nav_key='목표전환형 5호', aum_name='목표전환형 5호', ptype='target', kind_label='목표전환형',
        display='NH 목표전환형 5호', base_price=1000.00, start_date='2026-06-29', ytd_base='2026-06-29',
        color='#0072CE', advisory_template='자문지/✦NH5호자문지.xlsx',
        group='TT_2026Q3',          # ✦ NH5/DB6 동일포트면 페어 그룹, 별도 운용이면 group=None
        active=True, keep_in_nav=True),
```

### 2) DB 목표전환형 6차 — 2026-07-01
```python
Product(broker='DB', nav_key='목표전환형 6차', aum_name='목표전환형 6차', ptype='target', kind_label='목표전환형',
        display='DB 목표전환형 6차', base_price=1000.00, start_date='2026-07-01', ytd_base='2026-07-01',
        color='#00854A', advisory_template='자문지/✦DB6차자문지.xlsx',
        group='TT_2026Q3',          # ✦ NH5와 페어면 동일 group
        active=True, keep_in_nav=True),
```
**페어로 묶을 경우** `GROUPS` 에 추가:
```python
GROUPS = {
    'GENERAL_OPEN': {'use': '트루밸류'},
    'TT_2026Q3':    {'use': '목표전환형 5호'},   # 대표 nav_key (먼저 개시한 NH5)
}
```
→ 결합 표시 'NH 목표전환형 5호 / DB 목표전환형 6차' 자동, Order 카드 1개에 자문지 2개 자동.
- ✦ **확인 필요**: NH5호와 DB6차가 동일 종목/비중인가? (과거 페어는 동일포트라 묶었음). 다르면 각각 `group=None` 으로 분리.
- 6/29~6/30 사이엔 NH5만 활성 → 결합명이 'NH 목표전환형 5호' 단독으로 표시되다 7/1 DB6 합류 시 자동 확장(정상).

> ## ★★ 2026-07-02 한투 온보딩 실행 완료 (아래 3)·4) 초안은 이 박스 기준으로 대체됨)
> - `BROKERS` += `Broker('한투', '#F58220', 40)`. **지속형**(general, `nav_key='지속형'`, base 1000, 7/2 개시)은
>   포트 수렴 전이라 **단독(group=None)** — GENERAL_OPEN 합류는 수렴 후 검토. AUM 입력 유형=`지속형`.
> - **성과모집형 1차**(target, `nav_key='성과모집형 1차'`, 7/8 개시)를 **사전 등록** (Order 카드 선노출,
>   데이터·차트는 개시일부터). display='한투 성과모집형 1차'. AUM 입력 유형=`성과형`.
> - **자문지 양식**: `Product.advisory_format='kis'` — 한투 전용 채움 로직(`fillKisAdvisory`, R4~/A~H/소수 비중/
>   합계행 SUM 재작성). 템플릿 = `자문지/한국투자 가치도약랩(라이프자산)_20260702.xlsx`(지속형) /
>   `...(성과모집형 1차)_20260708.xlsx`(성과모집형). 다운로드 파일명 `_YYYYMMDD` 오늘 날짜 치환.
> - ★ **한투는 매 라운드 신규 템플릿 확보 필수** (NH/DB처럼 템플릿 재사용·회차 문자열 치환 구조가 아님).
> - ★ **매매 라벨 '비중축소'는 예시 파일에 미등장(유추 매핑)** — 첫 축소 주문 발송 전 육안 확인.
> - ★ **target 판별이 substring('목표전환형')에서 레지스트리 기준으로 교체됨** (create_dashboard AUM 표·누적차트,
>   daily_portfolio_report PNG 분류). 새 소비자 코드에서 substring 판별 금지 — `wrap_config.target_*()` 사용.
> - ★ **성과모집형 개시 주문은 7/8 당일 입력** 권장 (finalize가 저장일 날짜로 NEW 행을 쓰므로 조기 입력 시 개시일 전 날짜로 기록됨).

### 3) 한투 지속형(일반형) — 2026-07-02  ★신규 증권사 (→ 위 박스로 실행 완료)
`BROKERS` 에 추가:
```python
Broker('한투', '#✦색상', 40),   # ✦ 한투(한국투자증권) 브랜드 색 (예: KIS 오렌지 #F58220) 확인
```
`PRODUCTS` 에 추가:
```python
Product(broker='한투', nav_key='✦지속형컬럼명', aum_name='✦지속형AUM명', ptype='general', kind_label='✦일반형',
        display='한투 지속형', base_price=✦1000.00, start_date='2026-07-02', ytd_base='2026-07-02',
        color='#✦색상', advisory_template='자문지/✦한투지속형자문지.xlsx',
        group='GENERAL_OPEN',       # 사용자 결정: 개방형 3종과 합산 그룹 합류
        active=True, keep_in_nav=True),
```
→ 결합 표시가 '삼성 트루밸류 / NH Value ESG / DB 개방형 / 한투 지속형' 으로 자동 확장. broker_colors·BROKER_ORDER·Order 카드 templates/newSheetTargets·GENERAL 문자열·이메일 정렬 전부 자동.
- ✦ **확인 필요**:
  - `nav_key`(기준가/NEW 시트 컬럼명) & `aum_name`(AUM 시트 상품명) — NH처럼 다를 수 있음. 동일하면 같게.
  - `kind_label` = add_aum 입력 시 칠 **유형** 문자열. 기존 일반형 입력은 `일반형` → 일관성 위해 `일반형` 권장(표시명만 '한투 지속형'). 별도 `지속형`으로 칠 거면 `kind_label='지속형'`.
  - `base_price` 개시 기준가 (개방형 3종은 과거 환산값, 신규는 보통 1000 또는 별도 산정).
  - `GENERAL_OPEN` 합류 전제 = 동일포트. 한투 지속형이 다른 종목이면 `group=None`(별도 표시)로.

### 4) 한투 목표전환형 — 2026-07-08  ★단독 시리즈
```python
Product(broker='한투', nav_key='✦한투목표전환형1호', aum_name='✦한투목표전환형1호', ptype='target', kind_label='목표전환형',
        display='한투 목표전환형 1호', base_price=1000.00, start_date='2026-07-08', ytd_base='2026-07-08',
        color='#✦한투색', advisory_template='자문지/✦한투목표전환형자문지.xlsx',
        group=None,                 # 단독 — 페어 아님
        active=True, keep_in_nav=True),
```
→ `group=None` 이라 개별 차트 계열·개별 Order 카드·개별 AUM 행으로 자동 표시. AUM 누적차트도 `'목표전환형'` substring 동적 처리로 '한투 목표전환형 (누적)' 자동 생성.
- ✦ **★함정 — nav_key 충돌 주의**: 기존 NH/DB 청산분에 `'목표전환형 1호'`(NH 1호)·`'목표전환형 2호'`… 가 이미 있음. 한투가 `'목표전환형 1호'` 를 쓰면 **기준가 컬럼 충돌 + validate() 중복 에러**. → 한투 target의 `nav_key`/`aum_name`/`기준가 컬럼`/`NEW·AUM 상품명`을 **'한투 목표전환형 1호'처럼 증권사 구분 가능하게** 명명할 것. (display는 어차피 '한투 목표전환형 1호'.)
- add_aum: 한투 목표전환형 AUM 입력 유형은 `성과형` (resolve_product가 ACTIVE_TARGET_TRANSFORM['한투'] 로 매핑) — `active_target_transform()` 가 자동 포함.

---

## 검증 체크리스트 (각 출시 후)
- `python execution/wrap_config.py` → validate 경고 0, 파생물 육안 확인.
- `wrap.html`: `data-series="<display>"`, AUM 표 행, Order 카드(`var ORDER_PORTFOLIOS`), 결합명(`var GENERAL`) 에 신규 상품 반영.
- 전 .py `compile()`.
- 회귀: 기존 상품 차트/표/색상 불변.

---

## ★★ 2026-06-29 NH5 출시에서 발견·보완한 누락 지점 (다음 출시 전 반드시 검증)

레지스트리("출시 = 엔트리 1건")가 대부분 파생하지만, **청산기에 GENERAL(일반형) 전용으로 하드코딩된 소비자**가 남아 신규 출시가 조용히 누락될 수 있다. NH 목표전환형 5호 출시 때 아래가 빠져 사후 보완했다.

### 1) `advisory_template` 은 필수 — None 금지
- `advisory_template=None` 이면 **Email 탭 "자문지 다운로드" 버튼 + Order 탭 다운로드가 아예 생성되지 않는다** (`order_portfolios()` templates=[] → `renderEmailPanel` dlItems 비어있음).
- 다운로드는 ExcelJS가 템플릿(.xlsx)을 fetch → 입력된 주문데이터(B/C/D/E/F/G/H/I 행)로 채우고 B2 "목표전환형 N호"를 pfName 숫자로 자동 치환한다. **포맷 스켈레톤만 있으면 됨** → 직전 회차 자문지를 복사해 `..._목표전환형 N호_YYYY.M.D.xlsx` 로 두고 경로 주입 (자문지 파일은 git 추적·Pages 서빙됨).
- "Order 탭 직접 입력" 운용이어도 advisory_template은 필요하다(다운로드/이메일 첨부용).

### 2) `create_dashboard.py` 의 GENERAL-전용 하드코딩 (레지스트리 미연동 → 복원함)
- `renderEmailPanel` / `buildComplianceEmailText`: 청산커밋 `e31c9f10`이 GENERAL 단독 stub으로 남겨, active 목표전환형 이메일/네이트온/컴플라이언스가 안 떴다. → `wrap_config.target_tabs()`로 주입되는 `__TARGET_TABS__` 순회로 일반화 복원(`buildOrderEmailText`/`buildOrderNateonText`/`buildNateonReasonLines`는 이미 일반화돼 있었음). 향후 페어(DB6 등) 추가 시 박스 자동 증가.
- `create_aum_table`: 상단 표가 `max_date` 단일 스냅샷이라 **신규 상품(다른 날짜)이 기존 상품을 가렸다**. → `active_aum_names = fixed_products() ∪ active_target_transform()` 필터로 변경(각 상품의 최신 AUM 행, 청산분 제외). AUM은 매일이 아니라 주기적 입력이라 상품별 날짜가 다를 수 있으므로 이게 정답.

### 3) 정상(수정 불필요)이나 확인할 것
- 텔레그램 `/update`·`/portfolio`·일간리포트: `report_*` 파생 + portfolio_data.json 동적 순회 → **NEW 종목·기준가 데이터만 채워지면 자동 포함**(코드 무버그). 출시 당일 종가 전 안 보이는 건 데이터 부재(정상).
- ★ `daily_portfolio_report.py` `get_portfolio_holdings`: **PNG 종목표 target 슬롯이 단일 변수**라 active 목표전환형 2개 이상(예: NH5 + DB6차 동시 active)이면 1개만 PNG에 나온다. 텍스트 수익률/기준가는 둘 다 정상. → **DB 6차(7/1) 출시 전 키별 리스트 누적으로 보완 필요.**

### 4) 목표전환형 출시일(개시일) calculate_wrap_nav 가드
- 신규 포트 + 새 거래일 없음(장 시작 전/주말) 조합에서 빈 `df_change`(RangeIndex) ≤ Timestamp 비교 크래시가 있었다 → `if df_change.empty:` graceful exit로 수정(`34f8a754`). finalize_orders.yml의 calculate_wrap_nav가 출시 당일 장중에도 안전.

## 출시 후 필수 검증 체크리스트 (라이브 wrap.html + 텔레그램)
1. **Order 탭**: 신규 상품 카드 (`data-pf="<display>"`).
2. **Email 탭**: 자문지 다운로드 버튼(advisory_template) + 목표전환형이면 "`<broker>` 이메일" 박스 렌더.
3. **PORTFOLIO/CHART/RETURN**: 신규 상품 (NEW 종목·기준가 채워진 뒤).
4. **AUM 표**: 신규 상품 행 + **기존 상품도 전부 보임**(active 필터 확인).
5. **텔레그램 /update**: 신규 상품 표/수익률.
6. **calculate_wrap_nav**: 장중/주말 크래시 없음(graceful exit).

## ★★ 2026-06-29 표시 규칙 확정: 목표전환형 = 항상 단독(group=None)
목표전환형 랩은 회차마다 출시일이 달라 **절대 페어로 묶지 않고 개별/단독 표시**(NH·DB·한투 전부). group=None. 일반형(개방형)만 결합(GENERAL_OPEN, 한투 지속형 합류). → 위 "NH5/DB6 페어"·"TT_2026Q3"·"페어로 묶을 경우" 안내는 **폐기**. DB6 출시 상세는 broker_onboarding/DB6_LAUNCH_PLAN.md.

### Order 탭 이메일 기준선(2026-06-29 정비)
- 첫 주문: loadOrder가 is_today_new(오늘 첫 편입) 종목의 변경전=0 → 신규편입 표시.
- 추가 주문: 기존 additionalOrder()(추가주문 버튼 배선됨)가 변경후→변경전 스냅샷 → 2차 이메일은 증분만. is_today_new 하드마킹은 제거됨(추가주문 후 1차분 오표시 방지).
