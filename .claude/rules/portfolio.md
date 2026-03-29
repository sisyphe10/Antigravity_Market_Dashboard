---
patterns:
  - "calculate_wrap_nav.py"
  - "calculate_returns.py"
  - "Wrap_NAV.xlsx"
  - "execution/create_portfolio_tables.py"
---

# 포트폴리오 규칙

## 데이터 소스
- KOSPI/KOSDAQ: 네이버 금융이 primary source (FDR/Yahoo는 종가 부정확할 수 있음)

## 검증
- calculate_wrap_nav.py 실행 후: 수익률 시트 값 확인
- Wrap_NAV.xlsx 수정 후: merge 이후에도 수정값이 살아있는지 반드시 재확인

## Excel 주의
- Wrap_NAV.xlsx가 Excel에서 열려있으면 PermissionError 발생. 쓰기 실패 시 안내
