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
- market.html = 마켓 대시보드 (Monthly Returns 표 + Indices/MARKET 동적 차트)
- wrap.html = WRAP (Dashboard / Order / AUM 3탭, Order는 추가로 Email 서브탭)
- market_alert.html = 투자유의종목
- universe.html = Universe
- seibro.html = SEIBro
- featured.html = Featured (KRX 거래대금/시총/상승률 TOP)
- hotels.html = Hotels (ADR 추적)
- etf.html = ETF 구성종목 (조건부, etf_data.db 있을 때만)
- architecture.html = 아키텍처 (수동 관리)

## 파일 생성 의존 체인
```
Wrap_NAV.xlsx 변경 → calculate_wrap_nav.py → calculate_returns.py → create_dashboard.py
dataset.csv 변경 → draw_charts.py → create_dashboard.py
fetch_monthly_returns.py → monthly_returns.json → market.html (MONTHLY RETURNS 테이블)
portfolio_data.json (create_portfolio_tables.py) → wrap.html PORTFOLIO + Order 탭 fetch
orders/pending_orders.json (사용자 브라우저 → GitHub Contents API) → 16:00 KST GHA finalize → Wrap_NAV.xlsx NEW 시트
create_dashboard.py 변경 → 전체 HTML 재생성 (index, market, wrap, universe, seibro, featured, hotels)
create_market_alert.py 변경 → market_alert.html 재생성
```

## WRAP Order 탭 특이사항
- 3개 서브탭: 일반형 / NH 목표전환형 2호 / Email (DB 3차 청산 2026-05-06)
- 임시저장 (회색): orders/pending_orders.json에 누적 (GitHub Contents API)
- 최종 저장 (초록): 임시저장 + finalize_orders.yml workflow_dispatch 즉시 트리거
- Email 탭: 컴플라이언스/삼성/NH/네이트온 이메일 + 자문지 4개 다운로드 통합
- 추천사유는 종목코드 + 주문구분이 같을 때만 탭 간 동기화

## UI 일관성
- 글씨체: 영문 Inter + 한글 Noto Sans KR (`font-family: 'Inter', 'Noto Sans KR', sans-serif;`). Google Fonts 링크 필수. Chart.js 사용 시 `Chart.defaults.font.family` 동일하게 설정
- Home 버튼: 모든 페이지에서 오른쪽 상단, 라이트 그레이(#e0e0e0), `Home` (이모지 없음, font-size 15px, font-weight 600, border-radius 8px)
- create_dashboard.py 수정 시 모든 생성 파일 재생성 후 확인
- UI 변경 시 전체 페이지에서 일관성 확인
