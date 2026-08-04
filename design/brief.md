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
