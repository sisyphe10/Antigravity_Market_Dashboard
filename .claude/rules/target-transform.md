# 목표전환형 랩 추가/제거 SOP

목표전환형 시리즈는 운용 개시 → 목표달성 → 청산을 반복하는 단기 랩 상품. 매번 동일한 9개 파일 매핑이 필요해서 이 문서로 표준화.

## 입력 받을 정보 (사용자에게 확인)

추가 시 반드시 확인할 4가지:
1. **상품명**: 예) `목표전환형 2호` (Wrap_NAV.xlsx 컬럼명 그대로)
2. **표시명**: 예) `NH 목표전환형 2호` (대시보드/텔레그램 표기)
3. **운용 개시일**: 예) `2026-04-29`
4. **운용 개시 AUM**: 예) `237억원` → 23,700,000,000원
5. **색상**: NH = `#0072CE`, DB = (별도, 1차/2차 케이스 참고)

## 추가 워크플로 (운용 개시)

### Step 1. Wrap_NAV.xlsx 데이터 (사용자 + Claude 협업)

**사용자 작업** (대개 먼저 완료):
- `NEW` 시트: `날짜, 증권사, 상품명, 업종, 코드, 종목, 비중` 형식으로 종목 입력 + push
  - 종목별 한 행. 예: `2026-04-29, NH, 목표전환형 2호, 반도체, 5930, 삼성전자, 10`
  - 비중 합계 ≤ 100% (현금 비중 = 100 - 합계)

**Claude 작업**:
- `AUM` 시트에 행 추가: `날짜=운용 개시일, 증권사=NH/DB, 상품명, AUM=원 단위 정수`
  ```python
  new_row = pd.DataFrame([{
      '날짜': pd.Timestamp('YYYY-MM-DD'),
      '증권사': 'NH',  # 또는 'DB'
      '상품명': '목표전환형 N호',
      'AUM': N_억 * 100_000_000,
  }])
  ```
- `기준가` 시트는 calculate_wrap_nav.py가 자동 생성 (Step 3에서)

### Step 2. 코드 9곳 매핑 추가

| # | 파일 | 위치 | 추가 내용 |
|---|---|---|---|
| 1 | `calculate_wrap_nav.py` | `portfolio_config` 딕셔너리 | `'목표전환형 N호': {'base_price': 1000.00, 'start_date': 'YYYY-MM-DD'}` |
| 2 | `calculate_returns.py` | `ytd_base_dates` 딕셔너리 | `'목표전환형 N호': '운용 개시일'` (YTD = 운용 개시일) |
| 3 | `execution/create_dashboard.py` | `wrap_keywords` 리스트 (~L205) | `'목표전환형 N호'`, `'NH 목표전환형 N호'` |
| 4 | `execution/create_dashboard.py` | `chart_series` (`_build_wrap_chart_section`, ~L810) | `('NH 목표전환형 N호', '목표전환형 N호')` |
| 5 | `execution/create_dashboard.py` | `chart_colors` 딕셔너리 (~L817) | `'NH 목표전환형 N호': '#0072CE'` |
| 6 | `execution/create_dashboard.py` | `create_wrap_returns_table()` items (~L1560) | `('NH 목표전환형 N호', '목표전환형 N호')` |
| 7 | `execution/create_portfolio_tables.py` | `PORTFOLIO_DISPLAY_NAMES` (~L21) | `'목표전환형 N호': 'NH 목표전환형 N호'` |
| 8 | `execution/daily_portfolio_report.py` | `nav_map` (~L71) + `display_names` (~L208) + product list 2곳 (~L100, L214) | 각각 매핑 + 'KOSPI' 앞에 추가 |
| 9 | `execution/draw_wrap_charts.py` | `PORTFOLIO_NAMES` (~L40) | `'목표전환형 N호': 'NH 목표전환형 N호'` |

### Step 3. 실행 순서 (의존 체인)

```bash
# 1. 기준가 시트 자동 갱신 (신규 컬럼 자동 감지)
PYTHONIOENCODING=utf-8 python calculate_wrap_nav.py

# 2. 수익률 시트 갱신
PYTHONIOENCODING=utf-8 python calculate_returns.py

# 3. portfolio_data.json 갱신
PYTHONIOENCODING=utf-8 python execution/create_portfolio_tables.py

# 4. HTML 재생성 (wrap, market, index 등 동시)
PYTHONIOENCODING=utf-8 python execution/create_dashboard.py
```

### Step 4. 검증 (verify_before_done 룰)

- [ ] `wrap.html`에서 다음이 모두 보이는지 grep:
  - `data-series="NH 목표전환형 N호"` (CHART 사이드바)
  - `class="rt-name">NH 목표전환형 N호` (RETURN 테이블)
  - `<td>NH</td><td>목표전환형 N호</td><td>N억</td>` (AUM 테이블)
  - `<h3 class="portfolio-title">NH 목표전환형 N호` (PORTFOLIO 종목 테이블)
- [ ] 모든 파일 syntax 검증 (`compile()`)

### Step 5. Push + VM 동기화

```bash
git add Wrap_NAV.xlsx calculate_*.py execution/*.py featured.html market.html portfolio_data.json universe.html wrap.html
git commit -m "Add NH 목표전환형 N호 (운용 개시 YYYY-MM-DD, N억원)"
git push origin main

# VM 동기화 (deploy.sh 또는 직접)
ssh ubuntu@VM 'cd /home/ubuntu/Antigravity_Market_Dashboard && git fetch origin main && git reset --hard origin/main && sudo systemctl restart sisyphe-bot'
```

## 제거 워크플로 (운용 종료)

목표 달성 또는 청산 시. 참고: `43869e39` 커밋 패턴.

### Step 1. portfolio_config / 매핑 주석 처리

각 파일에서 추가 시 들어간 매핑을 **주석으로 변경** (삭제 아님 — 이력 보존):

```python
# calculate_wrap_nav.py
# '목표전환형 N호': {'base_price': 1000.00, 'start_date': 'YYYY-MM-DD'},  # N호 완료 (목표달성, YYYY-MM-DD 청산)

# calculate_returns.py
# '목표전환형 N호': 'YYYY-MM-DD',  # 완료

# create_portfolio_tables.py
# '목표전환형 N호': 'NH 목표전환형 N호',  # 완료
EXCLUDED_PORTFOLIOS = {..., '목표전환형 N호'}  # 추가

# daily_portfolio_report.py
# 'NH 목표전환형 N호': '목표전환형 N호',  # 완료

# draw_wrap_charts.py
# '목표전환형 N호': 'NH 목표전환형 N호',  # 완료
```

### Step 2. create_dashboard.py 매핑 4곳 제거

- `wrap_keywords`: `'목표전환형 N호'`, `'NH 목표전환형 N호'` 제거
- `chart_series`: 해당 튜플 제거
- `chart_colors`: 해당 키 제거
- `create_wrap_returns_table()` items: 해당 튜플 제거

### Step 3. 청산 정보 메모 (`calculate_wrap_nav.py` 상단)

```python
# ── 완료된 목표전환형 이력 ───────────────────────────────
# [N호 NH 목표전환형] YYYY-MM-DD ~ YYYY-MM-DD
#   시작 기준가: 1,000.00 / 청산 기준가: ~1,XXX.XX (N% 목표달성)
# ─────────────────────────────────────────────────────────
```

### Step 4. 실행 + Push

```bash
python execution/create_portfolio_tables.py  # portfolio_data.json에서 자동 제외
python execution/create_dashboard.py
git commit -m "Remove completed portfolio: NH 목표전환형 N호 (목표달성 YYYY-MM-DD)"
git push
# VM 동기화
```

`Wrap_NAV.xlsx`의 `기준가/수익률/NEW/AUM` 시트는 **건드리지 않음** (역사 데이터 보존).

## 자주 하는 실수 / 주의사항

- 매핑 9곳 중 하나라도 빠지면 표시 누락 발생. **체크리스트로 전수 확인**.
- AUM 시트는 `날짜` 컬럼이 datetime 타입이어야 함 (`pd.Timestamp` 사용).
- 운용 개시일이 거래일 아니면(주말/공휴일) calculate_wrap_nav.py가 데이터 못 만들 수 있음 → 다음 거래일에 다시 실행.
- KST 15시 이전이면 당일 데이터 미반영 → "검증 실패" 경고는 무시 가능 (다음 16시 이후 다시 실행하면 채워짐).
- `wrap_keywords`는 substring 매칭이라 다른 컬럼에 영향 가능. 새 명칭 추가 시 기존 컬럼명과 충돌 없는지 확인.

## 참고 커밋

- 추가 패턴: `7ced629e` (1호 추가), `ca48b432` (2차 추가), `f808da21` (1호 차트 추가)
- 제거 패턴: `43869e39` (1호+2차 동시 제거)
- 색상 변경: `f808da21`에 1호 색상 결정 흔적
