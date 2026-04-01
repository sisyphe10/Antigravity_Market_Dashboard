---
patterns:
  - "execution/create_dashboard.py"
  - "execution/create_market_alert.py"
  - "execution/draw_charts.py"
  - "*.html"
---

# 대시보드 규칙

## 페이지 구조
- index.html = 랜딩 페이지 (카드 네비게이션)
- market.html = 마켓 대시보드
- wrap.html = WRAP
- market_alert.html = 투자유의종목
- universe.html = Universe
- seibro.html = SEIBro
- architecture.html = 아키텍처 (수동 관리)

## 파일 생성 의존 체인
```
Wrap_NAV.xlsx 변경 → calculate_returns.py → create_dashboard.py
dataset.csv 변경 → draw_charts.py → create_dashboard.py
create_dashboard.py 변경 → 전체 HTML 재생성 (index, market, wrap, universe, seibro)
create_market_alert.py 변경 → market_alert.html 재생성
```

## UI 일관성
- 글씨체: 영문 Inter + 한글 Noto Sans KR (`font-family: 'Inter', 'Noto Sans KR', sans-serif;`). Google Fonts 링크 필수. Chart.js 사용 시 `Chart.defaults.font.family` 동일하게 설정
- Home 버튼: 모든 페이지에서 오른쪽 상단, 라이트 그레이(#e0e0e0), `🏠 Home`
- create_dashboard.py 수정 시 모든 생성 파일 재생성 후 확인
- UI 변경 시 전체 페이지에서 일관성 확인
