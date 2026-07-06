# 목표전환형 랩 추가/제거 SOP

> ## ★★ 2026-06-25 단일 레지스트리로 전환됨 — 이 문서의 "14곳" 절차는 **레거시/폴백**
> 증권사·상품 정의가 **`execution/wrap_config.py` 1곳(BROKERS/PRODUCTS/GROUPS)** 으로 통합됐다.
> 이제 출시/청산 = **레지스트리 엔트리 1건** 추가/수정 → 8개 스크립트가 모든 dict/list(portfolio_config·ytd_base_dates·chart_series·broker_colors·PORTFOLIO_GROUPS·FIXED_PRODUCTS·ORDER_PORTFOLIOS·GENERAL 등)를 자동 파생.
> **실제 출시 절차·출시별 사전 엔트리는 `broker_onboarding/LAUNCH_PLAYBOOK.md` 를 따른다.**
> 페어/단독 구분은 `group` id 하나로 통일(NH/DB 페어=같은 group, 한투 단독=group=None). 신규 증권사도 `BROKERS` 1줄.
> 아래 "14곳" 표는 레지스트리가 무엇을 파생하는지 이해하거나, 레지스트리 우회 시 참고용으로만 둔다.

---

목표전환형 시리즈는 **운용 개시 → 목표달성 → 청산**을 반복하는 단기 랩 상품. (구) NH/DB가 페어로 동시 출시·청산됐다. 손댈 곳이 **8개 파일 ~14곳**에 흩어져 있어 한두 곳만 빠뜨려도 차트/표가 어긋났다 — 그래서 레지스트리로 통합했다(위 박스).

> 실행 커맨드: **`/목표전환형 생성 ...`** / **`/목표전환형 청산 ...`** (`.claude/commands/목표전환형.md`)

---

## ★ 누락 방지 1순위 규칙 — grep으로 전수 확인

줄 번호는 코드가 자라면서 계속 밀린다. **외우지 말고 직전 회차명을 grep해서 손댈 곳을 한 번에 찾는다.**

```bash
# 청산/추가 직전, 직전(또는 현재) 회차명으로 전 파일 스캔
git grep -n '목표전환형 5차' origin/main -- '*.py'
# create_dashboard.py 가 제일 위험(6곳) → 따로 한 번 더
git grep -n '목표전환형' origin/main -- 'execution/create_dashboard.py'
```

NH/DB 둘 다 처리했는지, 13곳이 다 잡혔는지 매칭한다.

---

## 손대야 하는 14곳 (현재 origin 기준, 줄 번호는 참고용)

| # | 파일 | 위치(변수) | 추가(생성) / 주석·제거(청산) |
|---|---|---|---|
| 1 | `calculate_wrap_nav.py` | `portfolio_config` (~L40) | `'목표전환형 N': {'base_price':1000.00,'start_date':'YYYY-MM-DD'}` |
| 2 | `calculate_returns.py` | `ytd_base_dates` (~L16) | `'목표전환형 N': 'YYYY-MM-DD'` (YTD=개시일) |
| 3 | `execution/create_dashboard.py` | `wrap_keywords` (~L377) | `'목표전환형 N'`, `'NH/DB 목표전환형 N'` |
| 4 | `execution/create_dashboard.py` | `chart_series` (~L2515) | `('NH 목표전환형 N','목표전환형 N')` |
| 5 | `execution/create_dashboard.py` | `chart_colors` (~L2527) | NH=`#0072CE` / DB=`#00854A` |
| 6 | `execution/create_dashboard.py` | `ORDER_PORTFOLIOS` (~L3779) | `jsonKey`(페어명) + **자문지 .xlsx 경로**(NH·DB 각 1줄) |
| 7 | `execution/create_dashboard.py` | `TARGET_TABS` (~L4094) | `'NH 목표전환형 N'` (목표전환형 이메일 양식 적용 탭) |
| 8 | `execution/create_dashboard.py` | 최종저장 `confirm` 문구 (~L4750) | 안내문 상품 목록 갱신 (일반형/DB N차/NH N호) |
| 9 | `execution/create_portfolio_tables.py` | `PORTFOLIO_DISPLAY_NAMES` (~L24) | `'목표전환형 N':'NH/DB 목표전환형 N'` |
| 10 | `execution/create_portfolio_tables.py` | `PORTFOLIO_GROUPS` 2번째 그룹 (~L347) | `sources` 추가 + `combined` 페어명 갱신 |
| 11 | `execution/daily_portfolio_report.py` | `nav_map`(L110)·`display_names`(L305)·**product 리스트 2곳**(L144,L317) | 매핑 + product 리스트는 'KOSPI' 앞에 |
| 12 | `execution/draw_wrap_charts.py` | `PORTFOLIO_NAMES` (~L40) | `'목표전환형 N':'NH/DB 목표전환형 N'` |
| 13 | `add_aum.py` | `ACTIVE_TARGET_TRANSFORM` (~L46) | `{'NH':'목표전환형 N호','DB':'목표전환형 N차'}` |
| 14 | `execution/create_contribution_data.py` | `portfolio_config` (~L44) | `'목표전환형 N': {'base_price':1000.00,'start_date':'YYYY-MM-DD'}` — calculate_wrap_nav와 동일. 청산=주석 → 기여도 탭 자동 제외. **단 별도 실행 필요**(아래 ★) |

> ⚠️ **create_dashboard.py 함정**: #4 `chart_series` 외에 **`create_wrap_returns_table`의 `items` 리스트(~L3596)도 별도**로 회차 튜플을 가짐 (RETURN 표). 텍스트는 동일(`('NH 목표전환형 N','목표전환형 N')`)하니 grep 시 2곳 다 잡아 둘 다 처리.
>
> ★ **#14 재생성**: create_contribution_data.py는 표준 체인(calculate_wrap_nav→calculate_returns→create_portfolio_tables→create_dashboard)에 **없음**. 청산/생성 후 `python execution/create_contribution_data.py` 별도 실행 → `contribution_data.json` 재생성·커밋 (wrap.html 기여도 탭이 런타임 fetch). GHA `daily_crawl.yml`이 매일 자동 실행하므로 코드만 push해도 다음날 수렴하지만, 즉시 반영하려면 직접 실행.

**청산 전용 추가 작업** (생성 시엔 없음):
- `execution/create_portfolio_tables.py` `EXCLUDED_PORTFOLIOS` 집합(~L35)에 회차명 **추가**
- `calculate_wrap_nav.py` 상단 **완료 이력 주석 블록**(~L13)에 한 줄 추가

**건드리지 않는 것**:
- `_build...` **NH 1호 전용 차트**(create_dashboard.py ~L2790)는 historical 하드코딩 → 신규/청산 회차와 무관.
- AUM 표·누적 AUM 차트는 `'목표전환형'` substring으로 동적 처리 → 회차별 매핑 불필요.
- (구) AUM **입력** 패널(`create_aum_section`의 `AUM_PRODUCTS`)은 **2026-06-19 제거됨** → 더 이상 touchpoint 아님.

---

## 포트폴리오 그룹 (`PORTFOLIO_GROUPS`, create_portfolio_tables.py)

동일 종목/비중을 공유하는 포트폴리오를 한 묶음으로 표시하는 정의:
```python
PORTFOLIO_GROUPS = [
    { 'sources': ['트루밸류','Value ESG','개방형 랩'], 'combined': '삼성 트루밸류 / NH 다이내믹 밸류 / DB 개방형', 'use': '트루밸류' },  # 일반형(영구)
    { 'sources': ['목표전환형 5차','목표전환형 4호'], 'combined': 'NH 목표전환형 4호 / DB 목표전환형 5차', 'use': '목표전환형 5차' },  # 단기 랩(현재 페어)
]
```
- 새 페어 출시: `sources`에 두 회차 추가 + `combined` 페어명 갱신.
- 청산: `sources`에서 제거(또는 `EXCLUDED_PORTFOLIOS`로 차단).
- `ORDER_PORTFOLIOS`의 `jsonKey`는 `combined`와 정확히 일치해야 한다 (`portfolio_data.json` 키).

---

## 입력 받을 정보 (생성 시 사용자 확인)

1. **상품명**: `목표전환형 N호`(NH) / `목표전환형 N차`(DB) — Wrap_NAV.xlsx 컬럼명 그대로
2. **표시명**: `NH 목표전환형 N호`, `DB 목표전환형 N차`
3. **운용 개시일**(YYYY-MM-DD), **개시 AUM**(억원)
4. **색상**: NH `#0072CE` / DB `#00854A`
5. **자문지 템플릿 파일명** (`자문지/` 폴더)

---

## 🟢 생성(운용 개시) 워크플로

### Step 1. 데이터 (`Wrap_NAV.xlsx`)
- `NEW` 시트(보통 사용자): `날짜, 증권사, 상품명, 업종, 코드, 종목, 비중` 종목별 1행. 비중합 ≤100(나머지 현금).
- `AUM` 시트(Claude): 개시일 행 `{날짜=Timestamp, 증권사, 상품명, AUM=원 단위 정수}`.
- `기준가`/`수익률`은 자동 생성.

### Step 2. 코드 13곳 활성 항목 추가 (위 표)
- `자문지/` 폴더에 새 자문지 템플릿 .xlsx 1개 추가(6번이 가리키는 경로). R6 헤더 + R7~ 종목(F=변경전, G=변경후, H=주문구분, I=추천사유).

### Step 3. 실행 (의존 체인 순서 엄수)
```bash
PYTHONIOENCODING=utf-8 python calculate_wrap_nav.py
PYTHONIOENCODING=utf-8 python calculate_returns.py
PYTHONIOENCODING=utf-8 python execution/create_portfolio_tables.py
PYTHONIOENCODING=utf-8 python execution/create_dashboard.py
```
- 개시일이 주말/공휴일이면 calculate_wrap_nav가 데이터 못 만들 수 있음 → 다음 거래일 재실행.
- KST 15시 이전이면 당일 미반영(검증 실패 경고 무시 가능, 16시 이후 재실행).

### Step 4. 검증 (`wrap.html` grep, 4개 다 나와야 함)
- `data-series="NH 목표전환형 N"` (CHART 사이드바)
- `class="rt-name">NH 목표전환형 N` (RETURN 테이블)
- `<td>NH</td><td>목표전환형 N</td>` (AUM 테이블)
- `portfolio-title">NH 목표전환형 N` (PORTFOLIO 종목 테이블)
- 모든 .py `compile()` syntax 검증.

### Step 5. Push + 라이브 검증
- 코드(.py) + 재생성 HTML + Wrap_NAV.xlsx push → 라이브 wrap.html에서 마커 재확인.

---

## 🔴 청산(목표달성/상환) 워크플로

### Step 1. 시점 — ★장 마감 후
- **반드시 당일 최종 NAV 산출(~16:00~16:30 KST) 이후** 진행. 목표 도달 당일에 전일값으로 동결하면 청산수익률이 부정확.
- 거래일 = 개시일~청산일 양끝 포함 영업일 수. **청산일 = `기준가` 시트 마지막 기록일.**

### Step 2. 코드 13곳 처리 (삭제 아님 — 이력 보존)
- ★ **#1 `calculate_wrap_nav.py` portfolio_config는 주석 금지 → `'end_date':'청산일'` 부여.**
  (주석 처리하면 `combine_first`가 컬럼을 마지막 계산값에서 동결시켜 청산 직전 1~2일 NAV가 누락 →
  대시보드 회차별 AUM '거래일'이 과소표시. end_date를 주면 컬럼이 청산일까지 완결되고 이후 미계산.
  엔진이 end_date를 인지하도록 `incomplete_portfolios`·`pf_calc_dates`·최종검증 3곳 보강됨.
  2026-06-23 DB5차/NH4호 사고 → 근본수정.)
- 2·9·11·12·13: 활성 줄 → `# … # 완료 (YYYY-MM-DD 청산, +N%)`
- 3·4·5: 해당 항목 제거/주석
- 6·7·8: `ORDER_PORTFOLIOS` 페어 제거 + `TARGET_TABS` 비우기 + confirm 문구 일반형만으로
- 10: `PORTFOLIO_GROUPS` sources에서 제거
- **EXCLUDED_PORTFOLIOS(~L35)에 회차명 추가**
- `calculate_wrap_nav.py` 상단 이력 블록에 한 줄: `# [N호 NH 목표전환형] 개시 ~ 청산 / 청산 기준가 1,0XX.XX (+N% 목표달성)`
- `add_aum.py` ACTIVE_TARGET_TRANSFORM: 해당 증권사 줄 주석 (이후 그 전환형 AUM 입력은 에러나야 정상)

### Step 3. 데이터 보존 (★사용자 명시 지시)
- `Wrap_NAV.xlsx`의 `기준가 / 수익률 / NEW / AUM` 시트는 **전부 그대로 둔다.** 화면에서만 빠지고 기록은 남는다.
- AUM 표는 EXCLUDED 필터 없지만, 청산 다음 영업일 AUM엔 그 상품이 없어 최신 날짜 기준 자동으로 표에서 빠진다.

### Step 4. 실행·검증·Push (생성과 동일 체인)
- 재생성 후 `wrap.html`에서 해당 회차 마커 **0** + 잔존 상품 정상 확인 → push → 라이브 검증.

---

## 실행 환경·안전 수칙

- **로컬 작업트리는 오염/divergeed** → 항상 **origin/main 기준 격리 worktree**에서 작업: `git worktree add --detach /c/agdeploy_wt origin/main` (★`C:\Users\user` 밖이어야 함). [[project_antigravity_local_safe_push]]
- ★★**시크릿 스캔 훅 함정**: worktree가 추가 작업디렉토리로 잡히면 그 안의 `execution/kis_token.py`가 스캔 범위에 들어와 **모든 텍스트 응답이 차단**된다(stop_secret_scan.ps1). 대응: worktree 생성 직후 또는 push 완료 후, **텍스트 응답을 내기 전에** `rm -f /c/agdeploy_wt/execution/kis_token.py` (코드 재생성에는 불필요). [[feedback_large_dump_secret_match]]
- Push는 fast-forward 우선, origin 진행 시 `git merge --no-edit origin/main` 후 재푸시. `[skip ci]`로 장중 무거운 daily_crawl 기동 회피(단, `.claude/**`만 바뀌면 daily_crawl 트리거 안 됨).
- 배포 금지창 **16:00~17:00 KST**(VM cron race) — VM 배포(deploy.sh) 시. 순수 push는 무관하나 라이브 검증 타이밍 유의. [[feedback_bot_deploy_safety]]
- 로컬 시계 9h 오차 가능 → 시각 판단은 VM `TZ=Asia/Seoul date`로.

## 참고 커밋·임계값
- 추가: `7ced629e`(1호), `ca48b432`(2차), `f808da21`(1호 차트/색상)
- 제거: `43869e39`(1호+2차 동시 제거 페어 패턴)
- 청산 임계값(명목, 수수료·성과급 차감 전): **NH 6.5% / DB 7.5%** [[project_antigravity_target_transform_thresholds]]
- 청산 이력: [[project_wrap_liquidation_history]]
