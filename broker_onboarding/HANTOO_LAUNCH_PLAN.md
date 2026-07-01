# 한투(한국투자증권) 지속형(일반형) 출시 계획 — 2026-07-02 (목)

> 2026-07-01 사용자 확정 + 드라이런 검증 완료. **레지스트리 도입 후 첫 신규 증권사.**
> ✅ 4사 결합(동일 포트) — GENERAL_OPEN 합류. 드라이런서 하드코딩 갭 0 확인.
> 출시일 필수 작업: ①엔트리 2건(Broker+Product) ②자문지 ③NEW/AUM(개시 데이터).

## 1. wrap_config.py 엔트리 (확정)
```python
# BROKERS 에 추가 (DB 다음)
    Broker('한투', '#F58220', 40),

# PRODUCTS 일반형 3종 다음(DB 개방형 아래)에 추가
    # 한투 지속형(일반형) — 2026-07-02 개시. GENERAL_OPEN 합류(동일 포트, 4사 결합).
    Product(broker='한투', nav_key='지속형', aum_name='지속형', ptype='general', kind_label='일반형',
            display='한투 지속형', base_price=1000.00, start_date='2026-07-02', ytd_base='2026-07-02',
            color='#F58220', advisory_template='자문지/라이프자산운용_한투 지속형 랩_2026.7.2.xlsx',
            group='GENERAL_OPEN', keywords=('지속형', '한투 지속형')),
```
- GROUPS 변경 없음(GENERAL_OPEN use='트루밸류' 유지). nav_key '지속형' 충돌 없음.
- ✦출시 직전 재확인: nav_key/aum_name(시트 상품명)이 '지속형'이 맞는지(NH처럼 nav≠aum 분리면 수정), 색상 #F58220.

## 2. 자문지
`자문지/라이프자산운용_DB 개방형 랩 _2026.4.27.xlsx` 복사 → `자문지/라이프자산운용_한투 지속형 랩_2026.7.2.xlsx`. git 추적 필수.

## 3. 드라이런 검증 결과 (2026-07-01, push 안 함)
자동 파생 전부 정상:
- 결합명 자동 확장 → `삼성 트루밸류 / NH Value ESG / DB 개방형 / 한투 지속형` (GENERAL·portfolio-title·ORDER 카드 등 5+곳)
- Order 카드: 4 templates + 4 newSheetTargets / 자문지 다운로드 한투 버튼(#F58220, 맨 뒤 정렬)
- BROKER_CODES/ORDER/COLOR, 수수료 매출 REV_BROKER_ORDER = 4사 데이터 파생
- chart_series·chartColors·monthly_returns(개별행)·fixed_products((한투,일반형):지속형) 반영
- wrap_returns/report는 그룹 대표(트루밸류)라 한투 중복 없음
- compliance 이메일 = GENERAL+TARGET_TABS 데이터 파생(한투 포함), 3사 하드코딩 없음
- 체인 크래시 0

## 4. ⚠️ 사용자 확인 필요 (도메인)
**일반형 결합 주문 이메일은 단일 "삼성 이메일" 박스**로만 나감(기존 3사 설계 그대로). 4사 전달은 자문지 다운로드 버튼(4개)이 담당. → 한투도 이 방식(결합 1이메일 + 한투 자문지 다운로드)으로 충분한지, 아니면 **한투 전용 주문 이메일 박스**가 필요한지 확인. (필요 시 renderEmailPanel의 GENERAL 단일 박스 → 증권사별 분기 코드 변경 — 기존 3사에도 영향이라 신중.)

## 5. 출시일 받을 정보
개시 AUM(원) · 종목/6자리코드/섹터/개시비중%(또는 Order 탭 직접 입력 후 finalize) · base_price(=1000 확정) · nav/aum 상품명 '지속형' 확정.

## 6. 출시 절차 (16:00~17:00 KST 배포 회피, origin 기준 격리 worktree)
①엔트리 2건 ②자문지 복사 ③`python execution/wrap_config.py` validate ④(개시 AUM 있으면) add_aum `2026-07-02/한투/일반형/<AUM원>` ⑤체인(create_portfolio_tables→create_dashboard; 데이터 있으면 calc_wrap_nav→returns 선행) ⑥wrap.html 4사 결합·한투 카드 마커 확인 ⑦push([skip ci]) ⑧VM */5 pull 동기화 검증.

## 7. 출시 후 검증 체크리스트
- Order 카드: **4사 결합 카드**(templates 4) + NH5 + DB6 + Email
- Email 자문지 다운로드 4버튼 마지막이 한투(#F58220)
- AUM 표: 한투 지속형 행 + 4사 합산(기존 3사 안 가림)
- CHART/RETURN/monthly: 한투 지속형(주황) 개별 계열
- 텔레그램 /update: 한투 포함(데이터 채워진 뒤)
- validate 경고 0
