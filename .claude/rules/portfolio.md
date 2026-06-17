---
patterns:
  - "calculate_wrap_nav.py"
  - "calculate_returns.py"
  - "Wrap_NAV.xlsx"
  - "execution/create_portfolio_tables.py"
---

# 포트폴리오 규칙

## 데이터 소스
- KOSPI/KOSDAQ 지수: **KIS 일자별 확정지수(FHPUP02120000, inquire-index-daily-price)가 primary** → 네이버 금융 → FDR 폴백. (KIS=거래소 공식 확정 종가라 장중/마감직후 잠정값 회피. iscd KOSPI=0001/KOSDAQ=1001)
- 잠정 종가 자가복구(Fix A): calculate_wrap_nav는 신규 포트폴리오가 없는 일반 실행에서 최근 3거래일(개시행 보존 cap)을 롤백·재계산 → 한번 기록된 잠정값을 확정 종가로 덮어씀. 자동 업데이트 마지막 틱은 15:50(종가 확정 후).
- 과거 교훈: FDR/Yahoo는 종가 부정확/지연 가능. 네이버 일별시세는 마감 직후(~15:35) 잠정값일 수 있음 → KIS 확정지수로 전환(2026-06-17).

## 검증
- calculate_wrap_nav.py 실행 후: 수익률 시트 값 확인
- Wrap_NAV.xlsx 수정 후: merge 이후에도 수정값이 살아있는지 반드시 재확인

## Excel 주의
- Wrap_NAV.xlsx가 Excel에서 열려있으면 PermissionError 발생. 쓰기 실패 시 안내
