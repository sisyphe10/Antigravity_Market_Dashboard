# 한투(한국투자증권) 지속형(일반형) 출시 계획 — 2026-07-02 (목)

> 2026-07-01 사용자 확정 + 드라이런/코드 선반영 완료. **레지스트리 도입 후 첫 신규 증권사.**
> ★**완전 단독(group=None)** — 최종 목표는 4사 결합이나, 당분간 한투 포트가 3사와 달라 **수렴 과정** 필요 → 출시 시엔 단독. 자체 Order 카드 + 자체 "한투 이메일" 박스 + 개별 차트/수익률/AUM. 수렴 후 `group='GENERAL_OPEN'` 1줄로 편입(그때 4사 결합 자동).

## 0. ✅ 선반영 완료(2026-07-01) — 단독 일반형 이메일 인프라
`create_dashboard.py` renderEmailPanel 일반화 커밋됨: **group=None & ptype='general' 상품용 주문 이메일 박스** 생성 로직 추가(`__STANDALONE_GENERAL__` 주입 + `standalone_general_tabs()` 파생). 단독 일반형 0개면 inert(오늘 출력 불변, 회귀0 검증). codex:rescue 협업 설계·Node 구문검사 통과. → **내일 한투 엔트리만 넣으면 "한투 이메일" 박스 자동 생성.**

## 1. wrap_config.py 엔트리 (내일 추가 — ★BROKERS·PRODUCTS 동시)
```python
# BROKERS 에 추가 (DB 다음) — ★Product와 반드시 동시(안 그러면 brokerKey='zz'로 다운로드 맨 끝)
    Broker('한투', '#F58220', 40),

# PRODUCTS 일반형 3종 다음(DB 개방형 아래)에 추가 — group=None (단독)
    Product(broker='한투', nav_key='지속형', aum_name='지속형', ptype='general', kind_label='일반형',
            display='한투 지속형', base_price=1000.00, start_date='2026-07-02', ytd_base='2026-07-02',
            color='#F58220', advisory_template='자문지/라이프자산운용_한투 지속형 랩_2026.7.2.xlsx',
            group=None, keywords=('지속형', '한투 지속형')),
```
- GROUPS 변경 없음. GENERAL_OPEN은 3사 그대로 → "삼성 이메일" 단일박스 유지.
- ✦출시 직전 재확인: nav_key/aum_name(시트 상품명)='지속형' 맞는지, 색상 #F58220.

## 2. 자문지
`자문지/라이프자산운용_DB 개방형 랩 _2026.4.27.xlsx` 복사 → `자문지/라이프자산운용_한투 지속형 랩_2026.7.2.xlsx`. git 추적 필수.

## 3. 드라이런 검증(2026-07-01, push 안 함) — 한투 임시 투입 결과
- standalone_general_tabs() = [{display:'한투 지속형', broker:'한투'}]
- Order 카드 4개(3사결합 + NH5 + DB6 + **한투 지속형 단독**), 자문지 다운로드 한투 버튼(#F58220)
- STANDALONE_GENERAL 주입 populated, renderEmailPanel "한투 이메일" 박스 루프 배선 확인
- compliance/nateon에 한투 종목변경 포함(라벨 `[한투 지속형]`), 12개 인라인스크립트 Node 구문 OK

## 4. 이메일 동작(확정)
- 3사 결합 = 단일 "삼성 이메일" 박스(기존 그대로).
- 한투 = 별도 "한투 이메일" 박스(단일 changes 포맷). 컴플라이언스 통합본에 한투 포함(전 거래 보고). 네이트온에 `[한투 지속형]` 섹션 추가.
- 한투 탭 클릭 시: 이메일 텍스트(단일) + 컴플라이언스 통합본 + 네이트온(한투 단일 섹션).

## 5. 출시일 받을 정보
개시 AUM(원) · 종목/6자리코드/섹터/개시비중%(또는 Order 탭 직접 입력 후 finalize) · base_price(=1000 확정) · nav/aum 상품명 '지속형' 확정.

## 6. 출시 절차 (16:00~17:00 KST 배포 회피, origin 기준 격리 worktree)
①엔트리 2건(Broker+Product 동시) ②자문지 복사 ③`python execution/wrap_config.py` validate ④(개시 AUM 있으면) add_aum `2026-07-02/한투/일반형/<AUM원>` ⑤체인(create_portfolio_tables→create_dashboard; 데이터 있으면 calc_wrap_nav→returns 선행) ⑥wrap.html: 한투 단독 카드·"한투 이메일" 마커 확인 ⑦push([skip ci]) ⑧VM */5 pull 동기화 검증.

## 7. 출시 후 검증 체크리스트
- Order 카드: 3사결합 + NH5 + DB6 + **한투 지속형 단독 카드**
- Email: "한투 이메일" 박스 + 자문지 다운로드 한투 버튼(#F58220)
- AUM 표: 한투 지속형 개별 행(기존 안 가림)
- CHART/RETURN/monthly: 한투 지속형(주황) 개별 계열
- 텔레그램 /update: 한투 포함(데이터 채워진 뒤)
- validate 경고 0 (NEW/AUM 입력 후)

## 8. 수렴 후(추후) — 4사 결합 전환
한투 포트가 3사와 동일해지면 `group=None` → `group='GENERAL_OPEN'` 1줄 변경 → 결합명 '삼성 트루밸류 / NH Value ESG / DB 개방형 / 한투 지속형' 자동, "한투 이메일" 박스 사라지고 결합 단일 이메일로 흡수. (4사 결합 드라이런 검증됨: 하드코딩 갭 0.)
