# DB 목표전환형 6차 출시 계획 (2026-07-01 수)

> 2026-06-29 사전설계(팀원). **단독(group=None)** 확정 — 목표전환형은 출시일 상이로 항상 개별 표시(사용자 규칙). NH5 출시에서 정비된 인프라 위라 대부분 자동 동작. 출시일 필수 작업은 ①PNG fix ②엔트리 1건 ③자문지 ④NEW/AUM.

## 1. wrap_config.py 사전 엔트리 (NH5 활성 엔트리 다음에 삽입)
```python
    # DB 목표전환형 6차 — 2026-07-01 개시. 단독(group=None).
    Product(broker='DB', nav_key='목표전환형 6차', aum_name='목표전환형 6차', ptype='target', kind_label='목표전환형',
            display='DB 목표전환형 6차', base_price=1000.00, start_date='2026-07-01', ytd_base='2026-07-01',
            color='#00854A',
            advisory_template='자문지/라이프자산운용_DB 목표전환형 랩 _6차_2026.7.1.xlsx',
            group=None, active=True, keep_in_nav=True),
```
- GROUPS에 페어 추가 안 함. nav_key '목표전환형 6차'는 충돌 없음(validate 0).
- 자동 파생: active_target_transform {NH:5호,DB:6차} / order_portfolios DB6 단독카드 / target_tabs 2개 / chart·report 개별.

## 2. ★daily_portfolio_report.py PNG 단일슬롯 fix (DB6 active 전 필수 — 활성 목표전환형 2개)
`get_portfolio_holdings`가 target을 단일 변수로 덮어써 2개 중 1개만 PNG 전송됨.
- **diff A** `get_portfolio_holdings()`(~L169): `target = None`/`target = (key, stocks)`/`return general, target` → `targets = []`/`targets.append((key, stocks))`/`return general, targets`.
- **diff B** `send_report()`(~L335,L350): `general, target = ...` → `general, targets = ...`; 전송 루프를 `[('일반형 랩', general)]` + `targets` 각 항목(제목=표시명 'NH 목표전환형 5호'/'DB 목표전환형 6차')으로 순회.
→ PNG 3장: 일반형 / NH5 / DB6.

## 3. 자문지
`자문지/라이프자산운용_DB 목표전환형 랩 _5차_2026.6.12.xlsx` 복사 → `..._6차_2026.7.1.xlsx`. DB 템플릿 B2='DB증권 라이프 목표전환형 랩 현황'(회차 숫자 없음)이라 그대로 OK(다운로드가 데이터 채움). git 추적 필수.

## 4. 출시 절차 (16:00~17:00 KST 배포 회피)
①PNG fix 적용 ②자문지 복사 ③wrap_config 엔트리 ④Wrap_NAV.xlsx NEW(DB/목표전환형 6차 종목)+AUM ⑤add_aum `2026-07-01/DB/성과형/<AUM원>` ⑥`python execution/wrap_config.py` validate 경고0 ⑦체인(calc_wrap_nav→returns→create_portfolio_tables→create_dashboard,+contribution) ⑧push+배포.

## 5. 출시일 받을 정보
종목명/6자리코드/섹터/개시비중% · 개시 AUM(원) · base_price(보통1000) · 자문지(DB5 복사로 OK인지).

## 6. 출시 후 검증 체크리스트
- Order 카드: 결합(일반형) + NH5 단독 + **DB6 단독** + Email
- Email 자문지 다운로드: 5버튼(삼성/NH/DB 일반 + NH5 + DB6)
- Email 박스: 컴플라이언스/삼성/NH/**DB**/네이트온 (NH·DB 개별 박스)
- AUM 표: NH5·DB6·일반형 **전부**(신규가 기존 안 가림)
- PORTFOLIO/CHART/RETURN: NH5(파랑)·DB6(초록) 개별
- **PNG: 일반형/NH5/DB6 3장** (fix 확인)
- 텔레그램 /update: NH5·DB6 모두
- 이메일 기준선: DB6 1차=신규편입(is_today_new 변경전0), 추가주문=증분
- validate 경고 0
