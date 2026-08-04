OpenAI Codex v0.146.0
--------
workdir: C:\Users\user\AppData\Local\Temp\claude\C--Users-user\84297c0c-4989-4e2c-91c5-6d39f00d6b2d\scratchpad
model: gpt-5.6-sol
provider: openai
approval: never
sandbox: read-only
reasoning effort: xhigh
reasoning summaries: none
session id: 019fcb80-8d13-7d60-a4ab-30436b350c6f
--------
user
# 설계 브리프 — AoE 대시보드 "Featured" 탭 소생

당신은 시니어 아키텍트다. 아래 브리프를 읽고 **대안 2~3개 + 트레이드오프 표 + 실패 모드 + 검증 계획 + 추천 1개**를 내라.
한국어로 답하라. 코드를 전부 쓰지 말고 설계와 핵심 diff 스케치 수준으로.

---

## 0. 시스템 컨텍스트

개인용 금융 대시보드 "Age of Emergence(AoE)". 헤드리스 Mac mini M4가 정본 서버.
- repo: `~/Antigravity_Market_Dashboard` (GitHub). 웹 게시는 Tailscale+Caddy로 `ts.net`에 스냅숏 발행(60초 간격).
- 대시보드 HTML은 전부 **파이썬 생성기 산출물**. `execution/create_dashboard.py` 가 index/market/**featured**/etf 등을 생성. **HTML 직접 수정 금지**(5분마다 `git checkout -- "*.html"` + pull 이 도는 트리라 미커밋 HTML은 소멸).
- 수집 잡은 launchd LaunchDaemon (`/Library/LaunchDaemons/com.antigravity.*`).
- 페이지 위계: 상단 nav(Watchlist / Market / Journal / Earnings / Wiki …) → Market 하위 서브탭(Series / **Featured** / 투자유의종목 / ETF / SEIBro).

## 1. 대상: Featured 탭 현황 (실측, 2026-08-04)

### 화면
- 탭 2개: **종목**(기본) / **특이사항**
- 종목 탭 = 표 7개 나열: 거래대금 TOP30, 거래대금/시총비율 TOP30, KOSPI 시총 TOP30, KOSDAQ 시총 TOP30, KOSPI 상승률 TOP30, KOSDAQ 상승률 TOP30, 신고가 종목(20일/120일/52주 3열)
- 특이사항 탭 = 신고가 종목을 WICS 섹터로 묶고 섹터별 뉴스 요약(Claude 생성)을 붙인 표 3개(20일/120일/52주)
- 상단에 기간 입력 2칸(시작·종료, 기본값 = 데이터 최종일). 실제로는 하루치만 보는 용도.

### 파이프라인
| 시각(KST) | 잡 | 내용 |
|---|---|---|
| 15:50 | launchd `com.antigravity.featured-kis` | `fetch_featured_data_kis.py` → `featured_data.json` 누적 + `newhigh_20d.json` 생성, 이어서 `enrich_newhigh_themes.py`(네이버뉴스+Claude Haiku로 종목별 `theme` 부여) |
| 16:00 | ra_sisyphe_bot | `newhigh_20d.json` 소비해 신고가 텔레그램 발송 |
| 16:20 | 봇 1차 | 재수집 + `create_dashboard.py` → featured.html 재생성 + commit/push |
| 18:30 | 봇 2차 | 종가정정·거래대금 확정 반영 재수집 + 재생성 |
| 08:30(익일) | 복구 잡 | 직전 거래일 데이터 없으면 재수집 |

### 데이터 파일
- `featured_data.json` — **12.7MB, 60,377행, 165일치(2025-12-26 ~ 2026-08-03) 전량 누적**. 레코드 스키마:
  `{"d":"2026-08-03","type":"newhigh_20d","rank":0,"name":"한컴","code":"030520","market":"KOSDAQ","trdval":2703683740,"mktcap":419518558400,"turnover":0,"chg":1.76,"price":17350}`
  `type` ∈ {absolute, turnover, kospi_cap, kosdaq_cap, kospi_chg, kosdaq_chg (각 하루 30행), newhigh_20d, newhigh_120d, newhigh_52w (rank:0, 가변 건수)}
- `newhigh_20d.json` — 20KB, 텔레그램 봇용 20일 신고가 상세(종목별 `theme` 필드 포함)
- `featured_news.json` — 15KB, `{date, summaries: {섹터명: "요약 텍스트(HTML <b> 포함)"}}`, 21개 섹터
- `kis_price_history.json` — 7MB, KIS 당일고가/종가 누적(2026-06-01~, 63일, 2703종목, 300일 보관)
- `stock_price_history.json` — 27.9MB, yfinance 과거 시드(246일, 2025-07-29~2026-07-31, 2853종목)

### 렌더링 방식 (핵심 문제)
`create_dashboard.py` 가 **`featured_data.json` 전량을 HTML에 인라인 임베드**한다:
```python
featured_json = json.dumps(featured_records, ensure_ascii=False)   # 12.7MB
...
featured_page = f"""... <script>
var raw = {featured_json};      # ← 60,377행이 HTML 안에 통째로
var wics = {wics_json};         # 종목코드→WICS 섹터 2,549건
var newsData = {news_json};
...
"""
with open('featured.html','w') as f: f.write(...)
```
결과: **featured.html = 12.9MB**(gzip 1.7MB). 브라우저 실측 decoded 12.6MB / DOMContentLoaded 485ms / load 723ms(로컬 tailnet). 화면은 **하루치(≈200행)만** 사용. 매일 2회 재생성 후 git commit → 과거 git 히스토리에 featured.html만 11GB 누적(현재는 gh-pages 분리로 main 추적 중단 상태).

### 신고가 판정 로직 (`fetch_featured_data_kis.py`)
```python
KIS_HIST_KEEP_DAYS = 300
NEWHIGH_DAYS = 20; NEWHIGH_120D_DAYS = 120; NEWHIGH_52W_DAYS = 252

def accumulate_kis_history(master, prices, date_disp):
    # 오늘 KIS 당일고가/종가를 kis_price_history.json에 누적 (거래일 여부 판정 없음!)
    st['highs'][date_disp] = p['high']
    st['closes'][date_disp] = p['price']
    dates = sorted(set(hist.get('dates', [])) | {date_disp})
    keep = set(dates[-KIS_HIST_KEEP_DAYS:])

def compute_newhigh_20d(master, prices, date_disp, now_iso):
    # 과거 고가 머지: 날짜별 KIS 우선, 없으면 yfinance
    past = {}
    for d, v in yf_h.items():
        if d < date_disp and v: past[d] = v
    for d, v in kis_h.items():
        if d < date_disp and v: past[d] = v
    dates_sorted = sorted(past)
    high = p['high']
    prev20  = max(past[d] for d in dates_sorted[-20:])
    prev120 = max(past[d] for d in dates_sorted[-120:])
    prev52  = max(past[d] for d in dates_sorted[-252:])
    is_20, is_120, is_52w = high > prev20, high > prev120, high > prev52
    # 달성 타입별 rank:0 레코드를 featured_data.json에 append
    # + out20(20일 신고가 상세)에 lookback / lookback_52w(실제 사용된 창 길이) 기록
```

## 2. 실측 진단 (사용자가 "사실상 죽어 있다"고 표현한 상태)

확인된 결함:

1. **주말·휴일 행 오염 (확정 버그)** — 2026-06-02 KRX→KIS 컷오버 이후 **거래일 가드가 없다.** `featured_data.json`에 토·일 날짜 17건이 랭킹 30행씩 그대로 기록되고(전일 값 중복), 더 심각하게는 `kis_price_history.json`에도 주말이 누적된다(6/1~8/3 = 64일 중 63일 기록 = 사실상 매 캘린더데이). 그 결과 **`dates_sorted[-20:]`이 실제로는 약 14거래일**만 커버 → 20일 신고가 과다판정. 120/252 창도 같은 비율로 축소.
2. **12.6MB 단일 HTML** — 위 렌더링 방식. 165일치를 전량 임베드하는데 UI는 하루치만 쓴다. 매일 계속 커진다.
3. **특이사항 탭 요약 어긋남** — 섹터 요약을 20일/120일/52주 표에 **그대로 재사용**한다. 실측 예: 120일 신고가 섹터 "내구소비재와의류"는 종목이 `오로라` 1개뿐인데, 붙은 요약은 아모레퍼시픽홀딩스·쿠쿠홀딩스 서술(= 20일 신고가 11종목 기준 요약). 표에 없는 종목을 설명한다.
4. **18:30 2차 수집이 15:50 enrich 산출을 덮어쓴다** — 15:50 로그는 "테마 부여 완료: 46/79종목"인데 디스크의 `newhigh_20d.json`(18:30 갱신본)은 `theme` 필드 **0건**. 16:00 봇은 이미 발송 후라 피해 없지만, 이후 소비자는 테마를 못 본다.
5. **인사이트 부재** — 표 7개 나열뿐. 해석·연결(워치리스트 보유 종목 하이라이트, 전일 대비 신규 진입/이탈, 연속 등장, 섹터 쏠림) 없음. 기간 입력칸이 있으나 시계열을 쓰는 화면이 없다.

**정정 사항(중요)**: 신고가 3종 건수가 1~2월(월 1,700건대) → 8월(1건대)로 급감한 것은 **버그가 아니다.** 초기엔 yfinance 시드가 얕아 120일/52주 룩백 창이 실제로는 20~30일밖에 안 돼 **과다판정**된 것이고, 히스토리가 깊어지며(현재 2,703종목 중 2,609종목이 240일+ 확보) 정상값으로 수렴한 것이다. 다만 종목별 히스토리 깊이가 48~252일로 제각각인데 화면은 이를 **표시하지 않는다**(판정 신뢰도 미공개).

## 3. 브리프 4칸 (사용자 확정)

**a. 완료 기준** — **테스트 페이지까지.** 기존 `featured.html`은 무손상 유지한 채 새 안을 별도 테스트 페이지로 만들어 승인받는 데까지. nav 배선·라이브 교체는 승인 후 별건.

**b. 방향(사용자 선택)** — **"수리 + 경량 재설계"**. 즉 ①위 결함 수리를 먼저 하고 ②그 위에 데이터/HTML 분리(JSON fetch)와 상단 요약 블록을 얹는다. **2단계로 나눠 각각 되돌리기 가능해야 한다.**

**c. 사용자가 지목한 통증 3가지** — (i) 열어봐도 볼 게 없다 (ii) 읽어도 인사이트가 없다 (iii) 무겁다·느리다

**d. 데이터 출처** — 신규 수집 불필요. 기존 `featured_data.json` / `newhigh_20d.json` / `featured_news.json` / `kis_price_history.json` / WICS 섹터맵 / 워치리스트(별도 서비스 `quoteboard/server.py`, KIS multprice 463종목)로 충분. 과거 시계열 백필이 필요하면 `featured_data.json` 165일치가 이미 있다.

**e. 되돌리기 위험** — 있음. ①`featured_data.json` 스키마는 텔레그램 봇 등 기존 소비자가 있음(파괴적 변경 금지, 추가만) ②주말 행 정리는 **과거 데이터 삭제**를 수반할 수 있음(백업 필수) ③`create_dashboard.py`는 다른 페이지도 생성하므로 공통 함수 손대면 파급 ④ts.net 게시 스냅숏 화이트리스트(`publish_snapshot.sh`/`publish_pages.sh`)에 새 JSON을 넣지 않으면 라이브에서 404 — 페이지가 fetch하는 대상이 늘면 화이트리스트도 함께 갱신해야 함.

## 4. 제약 (반드시 지킬 것)

- 맥미니가 정본 — 로컬에서 개발해 scp 금지, 맥미니에서 직접 수정하고 **한 SSH 세션에서 즉시 commit+push**(5분 내 미커밋이면 소멸)
- `execution/**` 커밋은 커밋 메시지에 `[skip ci]` 필수
- 16:00~17:00 KST 배포 금지
- git은 rebase 금지, merge 사용
- 새 페이지는 **테스트 페이지 먼저**, 승인 후 nav 배선
- 페이지에 설명문·안내문구 넣지 말 것(사용자 규칙). 표는 가운데 정렬·순검정 텍스트
- 숫자 표기: %는 소수점 첫째자리, 금액은 억원 단위 `NN조 N,NNN억원`, 분기는 `1Q26`

## 5. 요구 산출물

1. **대안 2~3개** (예: 최소수리형 / 데이터-HTML 분리형 / 브리핑 재설계형 — 더 나은 축이 있으면 자유롭게)
2. **트레이드오프 표** (작업량·위험·통증(i)(ii)(iii) 해소도·되돌리기 용이성)
3. **결함 1~4의 구체 수리 방안** — 특히
   - 거래일 가드를 어디에 둘 것인가(수집 진입점 / 히스토리 누적 / 둘 다), 이미 오염된 과거 주말 행 17일치와 `kis_price_history.json` 주말 항목을 어떻게 처리할 것인가(삭제 vs 무시 필터, 백필 재계산 필요 여부)
   - 12.6MB 문제: 데이터-HTML 분리 시 파일 분할 전략(일자별 샤딩 / 최근 N일 + 아카이브 / 타입별)과 게시 화이트리스트 영향
   - 특이사항 탭 요약 어긋남을 스키마로 막는 방법
   - 15:50 enrich 산출이 18:30에 덮어써지는 문제의 해법(순서 변경 / 머지 / 별도 파일)
4. **"인사이트가 없다"에 대한 구체 제안** — 하루치 랭킹표에서 무엇을 더 뽑아낼 수 있나. 165일치 시계열이 이미 있다는 점을 활용할 것(예: 연속 등장 일수, 신규 진입/이탈, 섹터 쏠림 추이). 남발하지 말고 **실제로 매일 볼 만한 것 3~5개**로 좁혀라.
5. **실패 모드** (이 설계가 망가지는 시나리오)
6. **검증 계획** (라이브 실측 기준으로)
7. **추천 1개** + 예상 규모(파일 수·작업 시간)

codex
## 결론

추천은 **대안 B: 거래일 정합성 수리 → 일자별 JSON 샤딩 → 서버 측 인사이트 사전계산 → `featured_preview.html` 테스트 페이지**입니다.

핵심 원칙은 다음과 같습니다.

- 기존 `featured.html`의 URL·탭·nav는 유지합니다.
- HTML을 직접 수정하지 않고 별도 생성기에서 테스트 페이지를 만듭니다.
- `featured_data.json` 스키마는 삭제·변경하지 않고 필드 추가만 허용합니다.
- 브라우저가 165일 원본을 읽지 않게 하고, 선택한 하루와 작은 시계열 요약만 읽게 합니다.
- 1단계 수리와 2단계 재설계를 별도 커밋으로 만들어 각각 되돌릴 수 있게 합니다.

---

## 1. 대안

| 대안 | 구성 | 작업량 | 위험 | (i) 볼 것 없음 | (ii) 인사이트 없음 | (iii) 무거움 | 되돌리기 |
|---|---|---:|---:|---:|---:|---:|---:|
| A. 최소수리형 | 거래일·요약·테마 버그 수리, 최신 하루만 HTML 인라인 | 1~1.5일 | 낮음 | △ | △ | ◎ | ◎ |
| **B. 일자 샤드 + 사전계산 브리핑** | 수리 후 일자별 JSON, 작은 시계열, 상단 4개 인사이트 | **2~3일** | 중간 | **◎** | **◎** | **◎** | **◎** |
| C. 최근 20일 번들 + 월별 아카이브 | 최근 데이터는 묶어서 받고 브라우저에서 분석 | 2~2.5일 | 중간 | ○ | ○ | ○ | ○ |

A는 빠르지만 기간 입력과 165일 이력을 사실상 버립니다. C는 파일 수가 적지만 최초 payload가 다시 1~2MB대로 커지고 분석 로직이 브라우저에 집중됩니다. B가 현재 정적 스냅숏 구조와 가장 잘 맞습니다.

`type`별 분할은 권하지 않습니다. 하루를 표시하기 위해 7개 이상의 파일을 받아야 하고 각 파일이 다시 165일치로 커지기 때문입니다.

---

## 2. 추천안의 2단계 구조

### 1단계: 정확성 수리

별도 커밋으로 다음만 고칩니다.

- KRX 거래일 가드
- 과거 비거래일 오염 정리
- 신고가 룩백 재판정
- 뉴스 요약의 기간·종목 집합 결속
- 테마 enrichment 영속화
- 기존 소비자 호환성 테스트

기존 페이지의 구조와 nav는 건드리지 않습니다. 데이터 오류 수정으로 표시값이 달라질 수는 있지만 기존 탭과 기능은 유지합니다.

### 2단계: 경량 재설계

새 생성기에서 다음을 만듭니다.

```text
featured_preview.html
data/featured-v2/
  manifest.json
  series.json
  watchlist.json
  daily/
    2026-08-03.json
    ...
```

- `manifest.json`: 최신 거래일, 사용 가능한 날짜, 스키마 버전, 날짜별 revision
- `series.json`: 165일의 작은 집계 시계열
- `watchlist.json`: 현재 워치리스트 코드와 기준 시각
- `daily/YYYY-MM-DD.json`: 해당 하루의 7개 표, 신고가 상세, 정확히 결속된 요약, 사전계산 인사이트

기본 화면은 `manifest + series + watchlist + 하루 shard`만 받습니다. 브라우저가 12.7MB 원본을 직접 읽는 일은 없습니다.

기간 입력은 다음처럼 실제 기능을 갖게 합니다.

- 종료일: 아래 랭킹표의 기준일
- 시작일~종료일: 상단 추이·비교 블록의 범위
- 테이블을 위해 여러 날짜 shard를 받지 않고 `series.json`만 필터링

---

## 3. 결함별 수리 방안

### 결함 1: 주말·휴일 오염

거래일 가드는 **수집 진입점과 데이터 변경 함수 양쪽**에 둬야 합니다.

```python
target_date = resolve_krx_session(job_mode, now_kst)

if not krx_calendar.is_session(target_date):
    return SKIPPED

assert_quote_date_matches(target_date)

def accumulate_kis_history(..., date_disp):
    if not krx_calendar.is_session(date_disp):
        raise NonTradingDayWrite(date_disp)
```

추가로 기존 오염이 남아 있어도 판정에 들어가지 않도록 읽기 단계에서도 필터링합니다.

```python
past = {
    d: high for d, high in merged_history.items()
    if d < target_date and krx_calendar.is_session(d)
}
```

운영 정책은 다음과 같습니다.

- 예정된 주말·휴일 실행은 정상 `SKIPPED`
- 거래일인데 KIS 기준일이 다르면 실패 처리하고 기존 파일 유지
- 08:30 복구 잡은 단순히 어제를 쓰지 않고 `previous_session(now)` 사용
- 15:50·16:20·18:30 재수집은 `(date, type)` 파티션 교체 방식으로 멱등화

#### 과거 데이터 정리

“필터만 적용”이나 “즉시 삭제” 중 하나만 택하지 않고 둘 다 순서대로 합니다.

1. 원본 파일과 SHA-256을 repo 밖 백업 디렉터리에 보관
2. dry-run으로 제거할 날짜·행·종목별 history key 목록 생성
3. 런타임 필터를 먼저 배포
4. 검증 후 비거래일 데이터를 물리적으로 제거
5. 임시 파일에 쓴 뒤 원자적 rename
6. 제거한 레코드만 담은 역변환 journal도 보관

정리 대상은 다음과 같습니다.

- `featured_data.json`: 모든 비거래일의 모든 `type` 레코드
- `kis_price_history.json`:
  - 상위 `dates`
  - 종목별 `highs[date]`
  - 종목별 `closes[date]`

Git 과거 히스토리는 이번 작업에서 재작성하지 않습니다.

#### 백필 재계산

- 6개 TOP30 랭킹: 실제 거래일 데이터는 바꿀 필요 없음
- 신고가 20/120/252: 최초 오염일 이후 실제 거래일을 재판정해야 함
- 외부 재수집은 불필요하며, 정리된 KIS/yfinance history로 처리 가능

비거래일 중복을 제거하면 룩백이 14거래일에서 20거래일처럼 길어져 기준 고가는 같거나 높아집니다. 따라서 수정 후 신고가 집합은 기존 집합의 부분집합이어야 합니다. 기존 신고가 레코드를 재검사해 과다판정만 제거하면 되며, 원칙적으로 누락 종목을 새로 복원할 필요는 없습니다. 이 부분은 마이그레이션 불변식으로 검사합니다.

각 신고가 레코드에는 호환 가능한 추가 필드를 둡니다.

```json
{
  "lookback_used": 238,
  "lookback_target": 252,
  "history_complete": false
}
```

화면에는 문장 대신 `238/252`처럼 짧은 “이력” 열로 표시합니다.

---

### 결함 2: 12.6MB 단일 HTML

추천 분할 단위는 **일자별 shard**입니다.

하루 데이터는 현재 평균 약 77KB이고, 상세·인사이트를 더해도 통상 100~200KB 안에 머물 가능성이 높습니다. 과거 165일을 사용하는 계산은 생성기에서 수행하고 결과만 shard에 넣습니다.

```json
{
  "schema": 2,
  "date": "2026-08-03",
  "revision": "sha256-prefix",
  "tables": {
    "absolute": [],
    "turnover": [],
    "kospi_cap": []
  },
  "newhigh": {
    "20d": {},
    "120d": {},
    "52w": {}
  },
  "insights": {}
}
```

15:50와 18:30 사이의 혼합 파일을 막기 위해:

- 모든 JSON을 임시 파일로 생성 후 atomic rename
- shard를 먼저 게시하고 `manifest.json`을 마지막에 게시
- shard 내부 `revision`과 manifest revision이 다르면 브라우저가 짧게 재시도
- `manifest.json`은 `no-cache`, 과거 날짜 shard는 장기 캐시 가능

게시 스크립트 두 곳 모두 명시적으로 수정해야 합니다.

```text
featured_preview.html
data/featured-v2/manifest.json
data/featured-v2/series.json
data/featured-v2/watchlist.json
data/featured-v2/daily/**
```

`publish_snapshot.sh`와 `publish_pages.sh` 중 하나만 수정된 상태는 배포 실패로 간주합니다.

---

### 결함 3: 특이사항 요약 어긋남

요약을 단순히 `date + sector`로 저장하지 않고 다음 네 항목에 결속합니다.

- 기준일
- 신고가 기간: `20d`, `120d`, `52w`
- WICS 섹터
- 실제 표에 들어간 종목 코드 집합의 hash

```json
{
  "date": "2026-08-03",
  "horizon": "120d",
  "sector": "내구소비재와의류",
  "member_codes": ["..."],
  "members_hash": "7f31...",
  "text": "..."
}
```

렌더러는 현재 표의 코드 집합으로 hash를 다시 계산합니다.

```python
show_summary = (
    summary.date == table.date
    and summary.horizon == table.horizon
    and summary.sector == table.sector
    and summary.members_hash == hash(table.codes)
)
```

하나라도 다르면 다른 기간의 설명을 재사용하지 않고 빈 칸으로 둡니다. 잘못된 설명보다 누락이 낫습니다.

18:30에 구성 종목이 바뀌면 변경된 `(기간, 섹터)`만 재요약합니다. hash가 동일하면 기존 결과를 캐시 재사용합니다. 기존 `featured_news.json`은 유지하고 V2 스키마를 별도 파일 또는 추가 `scopes` 필드로 제공해야 합니다.

Claude 결과의 `<b>` HTML은 V2에서 그대로 `innerHTML`에 넣지 않고 구조화된 텍스트로 저장해 escape 후 렌더링하는 편이 안전합니다.

---

### 결함 4: 18:30 수집이 테마를 덮어씀

단순히 실행 순서만 바꾸는 것으로는 부족합니다. 18:30에 신고가 구성 자체가 달라질 수 있기 때문입니다.

추천 구조는 core·sidecar·호환 출력의 분리입니다.

```text
newhigh_20d_core.json     # 수집 결과, theme 없음
newhigh_themes.json       # date+code별 enrichment 영속 저장
newhigh_20d.json          # 위 둘을 합친 기존 소비자용 materialized view
```

`newhigh_themes.json` 예:

```json
{
  "2026-08-03": {
    "030520": {
      "theme": "...",
      "generated_at": "...",
      "input_hash": "...",
      "model": "..."
    }
  }
}
```

각 수집 순서는 다음과 같습니다.

```text
fetch core
→ 기존 sidecar와 머지
→ 누락·변경 종목만 enrich
→ sidecar atomic write
→ newhigh_20d.json materialize
```

15:50 테마는 18:30에도 유지되고, 18:30 신규 진입 종목만 추가 enrich됩니다. enrich가 실패하더라도 기존 종목의 테마는 보존되고 신규 종목만 빈 값으로 남습니다. 텔레그램 봇은 계속 기존 `newhigh_20d.json`을 읽으므로 계약 변경이 없습니다.

---

## 4. 매일 볼 만한 인사이트 4개

상단에 설명문 없이 네 개의 요약 블록만 둡니다.

| 블록 | 계산 | 표시 예 |
|---|---|---|
| 신고가 온도 | 20/120/252일 건수, 직전 20거래일 중앙값, 충분한 이력 비율 | `20일 31 · 중앙값 18 · 완전이력 94%` |
| 신규 진입·이탈 | 직전 거래일 대비 각 TOP30 집합 차이와 순위 변화 | `거래대금 신규 6 · 이탈 6 · 최대 +18위` |
| 워치리스트 레이더 | 현재 워치리스트와 랭킹·신고가 교집합 | `관심 9 · 신규 3 · 4일 연속 2` |
| 섹터 쏠림 | 20일 신고가 상위 WICS 섹터 비중과 최근 5거래일 중앙값 변화 | `반도체 28% · +11%p` |

행 단위에는 다음만 보강합니다.

- `신규`
- 전일 대비 순위 `+7`
- 연속 등장 `4일`
- 최근 20거래일 등장 `12/20`
- 신고가 이력 `238/252`
- 워치리스트 표시

섹터 표본이 5종목 미만이면 “쏠림” 판단은 하지 않고 단순 건수만 표시합니다. 작은 표본에서 100% 같은 과장된 지표가 생기는 것을 막기 위해서입니다.

CSS와 숫자 formatter는 V2 범위 안에만 두고 다른 페이지 공통 함수를 변경하지 않습니다. 모든 표는 가운데 정렬·검정 텍스트로 유지하고, 퍼센트는 소수점 첫째자리, 금액은 `12조 3,450억원` 형식으로 고정합니다.

---

## 5. 핵심 파일 변경 스케치

공통 생성기를 크게 손대지 않는 구성이 안전합니다.

```diff
 execution/fetch_featured_data_kis.py
+ 거래일 진입 가드
+ history 쓰기 가드
+ 과거 history 거래일 필터
+ date/type 멱등 교체
+ lookback_used/lookback_target 추가

 execution/enrich_newhigh_themes.py
+ newhigh_themes.json sidecar
+ 누락분 delta enrich
+ newhigh_20d.json materialize

+ execution/repair_featured_history.py
+ execution/create_featured_v2.py
+ execution/featured_calendar.py
+ tests/test_featured_*.py

 publish_snapshot.sh
 publish_pages.sh
+ featured-v2 산출물 화이트리스트

+ featured_preview.html          # 생성물
+ data/featured-v2/**
```

`create_dashboard.py`의 공통 함수는 건드리지 않고, 필요하면 기존 Featured 전용 분기만 최소 수정합니다. 테스트 페이지는 별도 생성기가 만드는 편이 파급 범위가 작습니다.

---

## 6. 실패 모드

| 실패 시나리오 | 결과 | 방어 |
|---|---|---|
| KRX 휴장 캘린더가 오래됨 | 거래일을 건너뛰거나 휴일을 기록 | 캘린더와 KIS 기준일 이중 확인, 불일치 시 fail-closed |
| 15:50와 18:30 작업이 겹침 | 파일 일부 혼합·테마 소실 | 단일 lock, run ID, atomic rename |
| manifest와 shard 게시 시점 불일치 | 최신 페이지가 구버전 데이터 사용 | shard 먼저, manifest 마지막, revision 검증 |
| 화이트리스트 누락 | ts.net에서 JSON 404 | 두 게시 스크립트 계약 테스트 |
| 18:30 종목 변경 후 요약 재생성 실패 | 잘못된 종목 설명 가능 | members hash 불일치 시 요약 미표시 |
| 워치리스트 서비스 중단 | 교집합 블록 실패 | 마지막 성공 snapshot 사용, 나머지 화면은 정상 렌더 |
| 정리 스크립트가 정상 거래일을 삭제 | 과거 데이터 손실 | dry-run, 세션 목록 검토, 백업·역변환 journal |
| 이력이 짧은 신규 상장주 | 52주 신고가처럼 과대 해석 | `lookback_used/target` 노출 |
| Claude 텍스트에 HTML 삽입 | 레이아웃 파손 또는 XSS | plain text 저장, DOM escape |
| 브라우저 날짜를 UTC로 파싱 | KST 날짜 하루 이동 | 날짜를 문자열 키로 처리, `new Date("YYYY-MM-DD")` 금지 |
| 5분 checkout 잡과 충돌 | 미커밋 작업 소멸 | 작은 원자 커밋, 같은 SSH 세션에서 즉시 push |

---

## 7. 검증 계획

### 데이터 정합성

- `featured_data.json`의 모든 `d`가 KRX session인지 검사
- `kis_price_history.json`의 모든 날짜 key가 session인지 검사
- 완료된 거래일의 TOP30 유형은 코드·rank 중복 없이 30건인지 검사
- 주말·공휴일을 끼운 20/120/252 세션 단위 테스트
- 정리 후 신고가 집합이 정리 전 신고가 집합의 부분집합인지 확인
- 제거된 신고가를 날짜·기간별 audit CSV로 남김
- 기존 텔레그램 파서 fixture가 추가 필드를 무시하고 정상 동작하는지 검사
- `15:50 fetch → enrich → 18:30 fetch` 재현 후 기존 theme 보존 확인
- 요약 hash를 의도적으로 틀리게 해 화면에서 표시되지 않는지 검사

### 생성·게시

- manifest가 참조하는 모든 shard의 존재·schema·revision 확인
- 두 publish 스크립트로 별도 staging 디렉터리에 게시 후 링크 검증
- `featured_preview.html`에서 과거·최신 거래일 각각 표 대조
- 15:50와 18:30 revision이 정상 교체되는지 확인
- 기존 `featured.html` URL, 탭, nav의 회귀 테스트
- nav에는 테스트 페이지를 연결하지 않음

### 라이브 실측 기준

동일 tailnet에서 cold cache 5회 기준으로 잡습니다.

- 초기 decoded 전송량: **500KB 이하**
- 단일 JSON: **250KB 이하**
- 기존 12.7MB `featured_data.json` 네트워크 요청: **0회**
- DOMContentLoaded 중앙값: **250ms 이하**
- load 중앙값: **500ms 이하**, p95 **800ms 이하**
- 모든 V2 요청 HTTP 200, JSON Content-Type 정상
- 표·요약의 날짜, horizon, 종목 hash 100% 일치
- 가운데 정렬·검정 텍스트·숫자 형식 스냅숏 검사
- 한 번의 15:50→16:00→16:20→18:30 전체 운영 주기 관찰

배포는 16:00~17:00을 피하고, `git pull --no-rebase` 또는 merge만 사용합니다. 단계별 커밋 예시는 다음처럼 분리합니다.

```text
fix(featured): enforce trading sessions and preserve enrichment [skip ci]
feat(featured): add sharded preview dashboard [skip ci]
```

---

## 8. 예상 규모

추천안 B 기준입니다.

- 소스·설정·테스트: 약 **9~12개 파일** 변경 또는 추가
- 게시 산출물:
  - HTML 1개
  - manifest/series/watchlist 3개
  - 일자 shard 최대 약 165개
- 이후 매일 실질적으로 변경되는 shard는 당일 파일 1개
- 작업 시간:
  - 1단계 수리·마이그레이션: **6~8시간**
  - 2단계 테스트 페이지·인사이트·게시: **10~14시간**
  - 합계 **16~22시간**, 이후 실제 거래일 1회 운영 관찰

따라서 **대안 B를 2개 독립 커밋으로 구현하고 `featured_preview.html`까지만 게시**하는 것을 추천합니다. 승인이 나기 전에는 nav 배선과 기존 `featured.html` 교체를 하지 않습니다.
tokens used
24,332
## 결론

추천은 **대안 B: 거래일 정합성 수리 → 일자별 JSON 샤딩 → 서버 측 인사이트 사전계산 → `featured_preview.html` 테스트 페이지**입니다.

핵심 원칙은 다음과 같습니다.

- 기존 `featured.html`의 URL·탭·nav는 유지합니다.
- HTML을 직접 수정하지 않고 별도 생성기에서 테스트 페이지를 만듭니다.
- `featured_data.json` 스키마는 삭제·변경하지 않고 필드 추가만 허용합니다.
- 브라우저가 165일 원본을 읽지 않게 하고, 선택한 하루와 작은 시계열 요약만 읽게 합니다.
- 1단계 수리와 2단계 재설계를 별도 커밋으로 만들어 각각 되돌릴 수 있게 합니다.

---

## 1. 대안

| 대안 | 구성 | 작업량 | 위험 | (i) 볼 것 없음 | (ii) 인사이트 없음 | (iii) 무거움 | 되돌리기 |
|---|---|---:|---:|---:|---:|---:|---:|
| A. 최소수리형 | 거래일·요약·테마 버그 수리, 최신 하루만 HTML 인라인 | 1~1.5일 | 낮음 | △ | △ | ◎ | ◎ |
| **B. 일자 샤드 + 사전계산 브리핑** | 수리 후 일자별 JSON, 작은 시계열, 상단 4개 인사이트 | **2~3일** | 중간 | **◎** | **◎** | **◎** | **◎** |
| C. 최근 20일 번들 + 월별 아카이브 | 최근 데이터는 묶어서 받고 브라우저에서 분석 | 2~2.5일 | 중간 | ○ | ○ | ○ | ○ |

A는 빠르지만 기간 입력과 165일 이력을 사실상 버립니다. C는 파일 수가 적지만 최초 payload가 다시 1~2MB대로 커지고 분석 로직이 브라우저에 집중됩니다. B가 현재 정적 스냅숏 구조와 가장 잘 맞습니다.

`type`별 분할은 권하지 않습니다. 하루를 표시하기 위해 7개 이상의 파일을 받아야 하고 각 파일이 다시 165일치로 커지기 때문입니다.

---

## 2. 추천안의 2단계 구조

### 1단계: 정확성 수리

별도 커밋으로 다음만 고칩니다.

- KRX 거래일 가드
- 과거 비거래일 오염 정리
- 신고가 룩백 재판정
- 뉴스 요약의 기간·종목 집합 결속
- 테마 enrichment 영속화
- 기존 소비자 호환성 테스트

기존 페이지의 구조와 nav는 건드리지 않습니다. 데이터 오류 수정으로 표시값이 달라질 수는 있지만 기존 탭과 기능은 유지합니다.

### 2단계: 경량 재설계

새 생성기에서 다음을 만듭니다.

```text
featured_preview.html
data/featured-v2/
  manifest.json
  series.json
  watchlist.json
  daily/
    2026-08-03.json
    ...
```

- `manifest.json`: 최신 거래일, 사용 가능한 날짜, 스키마 버전, 날짜별 revision
- `series.json`: 165일의 작은 집계 시계열
- `watchlist.json`: 현재 워치리스트 코드와 기준 시각
- `daily/YYYY-MM-DD.json`: 해당 하루의 7개 표, 신고가 상세, 정확히 결속된 요약, 사전계산 인사이트

기본 화면은 `manifest + series + watchlist + 하루 shard`만 받습니다. 브라우저가 12.7MB 원본을 직접 읽는 일은 없습니다.

기간 입력은 다음처럼 실제 기능을 갖게 합니다.

- 종료일: 아래 랭킹표의 기준일
- 시작일~종료일: 상단 추이·비교 블록의 범위
- 테이블을 위해 여러 날짜 shard를 받지 않고 `series.json`만 필터링

---

## 3. 결함별 수리 방안

### 결함 1: 주말·휴일 오염

거래일 가드는 **수집 진입점과 데이터 변경 함수 양쪽**에 둬야 합니다.

```python
target_date = resolve_krx_session(job_mode, now_kst)

if not krx_calendar.is_session(target_date):
    return SKIPPED

assert_quote_date_matches(target_date)

def accumulate_kis_history(..., date_disp):
    if not krx_calendar.is_session(date_disp):
        raise NonTradingDayWrite(date_disp)
```

추가로 기존 오염이 남아 있어도 판정에 들어가지 않도록 읽기 단계에서도 필터링합니다.

```python
past = {
    d: high for d, high in merged_history.items()
    if d < target_date and krx_calendar.is_session(d)
}
```

운영 정책은 다음과 같습니다.

- 예정된 주말·휴일 실행은 정상 `SKIPPED`
- 거래일인데 KIS 기준일이 다르면 실패 처리하고 기존 파일 유지
- 08:30 복구 잡은 단순히 어제를 쓰지 않고 `previous_session(now)` 사용
- 15:50·16:20·18:30 재수집은 `(date, type)` 파티션 교체 방식으로 멱등화

#### 과거 데이터 정리

“필터만 적용”이나 “즉시 삭제” 중 하나만 택하지 않고 둘 다 순서대로 합니다.

1. 원본 파일과 SHA-256을 repo 밖 백업 디렉터리에 보관
2. dry-run으로 제거할 날짜·행·종목별 history key 목록 생성
3. 런타임 필터를 먼저 배포
4. 검증 후 비거래일 데이터를 물리적으로 제거
5. 임시 파일에 쓴 뒤 원자적 rename
6. 제거한 레코드만 담은 역변환 journal도 보관

정리 대상은 다음과 같습니다.

- `featured_data.json`: 모든 비거래일의 모든 `type` 레코드
- `kis_price_history.json`:
  - 상위 `dates`
  - 종목별 `highs[date]`
  - 종목별 `closes[date]`

Git 과거 히스토리는 이번 작업에서 재작성하지 않습니다.

#### 백필 재계산

- 6개 TOP30 랭킹: 실제 거래일 데이터는 바꿀 필요 없음
- 신고가 20/120/252: 최초 오염일 이후 실제 거래일을 재판정해야 함
- 외부 재수집은 불필요하며, 정리된 KIS/yfinance history로 처리 가능

비거래일 중복을 제거하면 룩백이 14거래일에서 20거래일처럼 길어져 기준 고가는 같거나 높아집니다. 따라서 수정 후 신고가 집합은 기존 집합의 부분집합이어야 합니다. 기존 신고가 레코드를 재검사해 과다판정만 제거하면 되며, 원칙적으로 누락 종목을 새로 복원할 필요는 없습니다. 이 부분은 마이그레이션 불변식으로 검사합니다.

각 신고가 레코드에는 호환 가능한 추가 필드를 둡니다.

```json
{
  "lookback_used": 238,
  "lookback_target": 252,
  "history_complete": false
}
```

화면에는 문장 대신 `238/252`처럼 짧은 “이력” 열로 표시합니다.

---

### 결함 2: 12.6MB 단일 HTML

추천 분할 단위는 **일자별 shard**입니다.

하루 데이터는 현재 평균 약 77KB이고, 상세·인사이트를 더해도 통상 100~200KB 안에 머물 가능성이 높습니다. 과거 165일을 사용하는 계산은 생성기에서 수행하고 결과만 shard에 넣습니다.

```json
{
  "schema": 2,
  "date": "2026-08-03",
  "revision": "sha256-prefix",
  "tables": {
    "absolute": [],
    "turnover": [],
    "kospi_cap": []
  },
  "newhigh": {
    "20d": {},
    "120d": {},
    "52w": {}
  },
  "insights": {}
}
```

15:50와 18:30 사이의 혼합 파일을 막기 위해:

- 모든 JSON을 임시 파일로 생성 후 atomic rename
- shard를 먼저 게시하고 `manifest.json`을 마지막에 게시
- shard 내부 `revision`과 manifest revision이 다르면 브라우저가 짧게 재시도
- `manifest.json`은 `no-cache`, 과거 날짜 shard는 장기 캐시 가능

게시 스크립트 두 곳 모두 명시적으로 수정해야 합니다.

```text
featured_preview.html
data/featured-v2/manifest.json
data/featured-v2/series.json
data/featured-v2/watchlist.json
data/featured-v2/daily/**
```

`publish_snapshot.sh`와 `publish_pages.sh` 중 하나만 수정된 상태는 배포 실패로 간주합니다.

---

### 결함 3: 특이사항 요약 어긋남

요약을 단순히 `date + sector`로 저장하지 않고 다음 네 항목에 결속합니다.

- 기준일
- 신고가 기간: `20d`, `120d`, `52w`
- WICS 섹터
- 실제 표에 들어간 종목 코드 집합의 hash

```json
{
  "date": "2026-08-03",
  "horizon": "120d",
  "sector": "내구소비재와의류",
  "member_codes": ["..."],
  "members_hash": "7f31...",
  "text": "..."
}
```

렌더러는 현재 표의 코드 집합으로 hash를 다시 계산합니다.

```python
show_summary = (
    summary.date == table.date
    and summary.horizon == table.horizon
    and summary.sector == table.sector
    and summary.members_hash == hash(table.codes)
)
```

하나라도 다르면 다른 기간의 설명을 재사용하지 않고 빈 칸으로 둡니다. 잘못된 설명보다 누락이 낫습니다.

18:30에 구성 종목이 바뀌면 변경된 `(기간, 섹터)`만 재요약합니다. hash가 동일하면 기존 결과를 캐시 재사용합니다. 기존 `featured_news.json`은 유지하고 V2 스키마를 별도 파일 또는 추가 `scopes` 필드로 제공해야 합니다.

Claude 결과의 `<b>` HTML은 V2에서 그대로 `innerHTML`에 넣지 않고 구조화된 텍스트로 저장해 escape 후 렌더링하는 편이 안전합니다.

---

### 결함 4: 18:30 수집이 테마를 덮어씀

단순히 실행 순서만 바꾸는 것으로는 부족합니다. 18:30에 신고가 구성 자체가 달라질 수 있기 때문입니다.

추천 구조는 core·sidecar·호환 출력의 분리입니다.

```text
newhigh_20d_core.json     # 수집 결과, theme 없음
newhigh_themes.json       # date+code별 enrichment 영속 저장
newhigh_20d.json          # 위 둘을 합친 기존 소비자용 materialized view
```

`newhigh_themes.json` 예:

```json
{
  "2026-08-03": {
    "030520": {
      "theme": "...",
      "generated_at": "...",
      "input_hash": "...",
      "model": "..."
    }
  }
}
```

각 수집 순서는 다음과 같습니다.

```text
fetch core
→ 기존 sidecar와 머지
→ 누락·변경 종목만 enrich
→ sidecar atomic write
→ newhigh_20d.json materialize
```

15:50 테마는 18:30에도 유지되고, 18:30 신규 진입 종목만 추가 enrich됩니다. enrich가 실패하더라도 기존 종목의 테마는 보존되고 신규 종목만 빈 값으로 남습니다. 텔레그램 봇은 계속 기존 `newhigh_20d.json`을 읽으므로 계약 변경이 없습니다.

---

## 4. 매일 볼 만한 인사이트 4개

상단에 설명문 없이 네 개의 요약 블록만 둡니다.

| 블록 | 계산 | 표시 예 |
|---|---|---|
| 신고가 온도 | 20/120/252일 건수, 직전 20거래일 중앙값, 충분한 이력 비율 | `20일 31 · 중앙값 18 · 완전이력 94%` |
| 신규 진입·이탈 | 직전 거래일 대비 각 TOP30 집합 차이와 순위 변화 | `거래대금 신규 6 · 이탈 6 · 최대 +18위` |
| 워치리스트 레이더 | 현재 워치리스트와 랭킹·신고가 교집합 | `관심 9 · 신규 3 · 4일 연속 2` |
| 섹터 쏠림 | 20일 신고가 상위 WICS 섹터 비중과 최근 5거래일 중앙값 변화 | `반도체 28% · +11%p` |

행 단위에는 다음만 보강합니다.

- `신규`
- 전일 대비 순위 `+7`
- 연속 등장 `4일`
- 최근 20거래일 등장 `12/20`
- 신고가 이력 `238/252`
- 워치리스트 표시

섹터 표본이 5종목 미만이면 “쏠림” 판단은 하지 않고 단순 건수만 표시합니다. 작은 표본에서 100% 같은 과장된 지표가 생기는 것을 막기 위해서입니다.

CSS와 숫자 formatter는 V2 범위 안에만 두고 다른 페이지 공통 함수를 변경하지 않습니다. 모든 표는 가운데 정렬·검정 텍스트로 유지하고, 퍼센트는 소수점 첫째자리, 금액은 `12조 3,450억원` 형식으로 고정합니다.

---

## 5. 핵심 파일 변경 스케치

공통 생성기를 크게 손대지 않는 구성이 안전합니다.

```diff
 execution/fetch_featured_data_kis.py
+ 거래일 진입 가드
+ history 쓰기 가드
+ 과거 history 거래일 필터
+ date/type 멱등 교체
+ lookback_used/lookback_target 추가

 execution/enrich_newhigh_themes.py
+ newhigh_themes.json sidecar
+ 누락분 delta enrich
+ newhigh_20d.json materialize

+ execution/repair_featured_history.py
+ execution/create_featured_v2.py
+ execution/featured_calendar.py
+ tests/test_featured_*.py

 publish_snapshot.sh
 publish_pages.sh
+ featured-v2 산출물 화이트리스트

+ featured_preview.html          # 생성물
+ data/featured-v2/**
```

`create_dashboard.py`의 공통 함수는 건드리지 않고, 필요하면 기존 Featured 전용 분기만 최소 수정합니다. 테스트 페이지는 별도 생성기가 만드는 편이 파급 범위가 작습니다.

---

## 6. 실패 모드

| 실패 시나리오 | 결과 | 방어 |
|---|---|---|
| KRX 휴장 캘린더가 오래됨 | 거래일을 건너뛰거나 휴일을 기록 | 캘린더와 KIS 기준일 이중 확인, 불일치 시 fail-closed |
| 15:50와 18:30 작업이 겹침 | 파일 일부 혼합·테마 소실 | 단일 lock, run ID, atomic rename |
| manifest와 shard 게시 시점 불일치 | 최신 페이지가 구버전 데이터 사용 | shard 먼저, manifest 마지막, revision 검증 |
| 화이트리스트 누락 | ts.net에서 JSON 404 | 두 게시 스크립트 계약 테스트 |
| 18:30 종목 변경 후 요약 재생성 실패 | 잘못된 종목 설명 가능 | members hash 불일치 시 요약 미표시 |
| 워치리스트 서비스 중단 | 교집합 블록 실패 | 마지막 성공 snapshot 사용, 나머지 화면은 정상 렌더 |
| 정리 스크립트가 정상 거래일을 삭제 | 과거 데이터 손실 | dry-run, 세션 목록 검토, 백업·역변환 journal |
| 이력이 짧은 신규 상장주 | 52주 신고가처럼 과대 해석 | `lookback_used/target` 노출 |
| Claude 텍스트에 HTML 삽입 | 레이아웃 파손 또는 XSS | plain text 저장, DOM escape |
| 브라우저 날짜를 UTC로 파싱 | KST 날짜 하루 이동 | 날짜를 문자열 키로 처리, `new Date("YYYY-MM-DD")` 금지 |
| 5분 checkout 잡과 충돌 | 미커밋 작업 소멸 | 작은 원자 커밋, 같은 SSH 세션에서 즉시 push |

---

## 7. 검증 계획

### 데이터 정합성

- `featured_data.json`의 모든 `d`가 KRX session인지 검사
- `kis_price_history.json`의 모든 날짜 key가 session인지 검사
- 완료된 거래일의 TOP30 유형은 코드·rank 중복 없이 30건인지 검사
- 주말·공휴일을 끼운 20/120/252 세션 단위 테스트
- 정리 후 신고가 집합이 정리 전 신고가 집합의 부분집합인지 확인
- 제거된 신고가를 날짜·기간별 audit CSV로 남김
- 기존 텔레그램 파서 fixture가 추가 필드를 무시하고 정상 동작하는지 검사
- `15:50 fetch → enrich → 18:30 fetch` 재현 후 기존 theme 보존 확인
- 요약 hash를 의도적으로 틀리게 해 화면에서 표시되지 않는지 검사

### 생성·게시

- manifest가 참조하는 모든 shard의 존재·schema·revision 확인
- 두 publish 스크립트로 별도 staging 디렉터리에 게시 후 링크 검증
- `featured_preview.html`에서 과거·최신 거래일 각각 표 대조
- 15:50와 18:30 revision이 정상 교체되는지 확인
- 기존 `featured.html` URL, 탭, nav의 회귀 테스트
- nav에는 테스트 페이지를 연결하지 않음

### 라이브 실측 기준

동일 tailnet에서 cold cache 5회 기준으로 잡습니다.

- 초기 decoded 전송량: **500KB 이하**
- 단일 JSON: **250KB 이하**
- 기존 12.7MB `featured_data.json` 네트워크 요청: **0회**
- DOMContentLoaded 중앙값: **250ms 이하**
- load 중앙값: **500ms 이하**, p95 **800ms 이하**
- 모든 V2 요청 HTTP 200, JSON Content-Type 정상
- 표·요약의 날짜, horizon, 종목 hash 100% 일치
- 가운데 정렬·검정 텍스트·숫자 형식 스냅숏 검사
- 한 번의 15:50→16:00→16:20→18:30 전체 운영 주기 관찰

배포는 16:00~17:00을 피하고, `git pull --no-rebase` 또는 merge만 사용합니다. 단계별 커밋 예시는 다음처럼 분리합니다.

```text
fix(featured): enforce trading sessions and preserve enrichment [skip ci]
feat(featured): add sharded preview dashboard [skip ci]
```

---

## 8. 예상 규모

추천안 B 기준입니다.

- 소스·설정·테스트: 약 **9~12개 파일** 변경 또는 추가
- 게시 산출물:
  - HTML 1개
  - manifest/series/watchlist 3개
  - 일자 shard 최대 약 165개
- 이후 매일 실질적으로 변경되는 shard는 당일 파일 1개
- 작업 시간:
  - 1단계 수리·마이그레이션: **6~8시간**
  - 2단계 테스트 페이지·인사이트·게시: **10~14시간**
  - 합계 **16~22시간**, 이후 실제 거래일 1회 운영 관찰

따라서 **대안 B를 2개 독립 커밋으로 구현하고 `featured_preview.html`까지만 게시**하는 것을 추천합니다. 승인이 나기 전에는 nav 배선과 기존 `featured.html` 교체를 하지 않습니다.
