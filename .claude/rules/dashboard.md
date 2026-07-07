---
patterns:
  - "execution/create_dashboard.py"
  - "execution/create_market_alert.py"
  - "execution/draw_charts.py"
  - "*.html"
---

# 대시보드 규칙

## 페이지 구조
- index.html = 랜딩 페이지 (sparkline + 인용구 카드, 상단 탭바로 네비게이션)
- market.html = 마켓 대시보드 (Monthly Returns 표 + Indices/MARKET 동적 차트)
- wrap.html = WRAP (Dashboard / Order / AUM 3탭, Order는 추가로 Email 서브탭)
- market_alert.html = 투자유의종목
- universe.html = Universe
- seibro.html = SEIBro
- featured.html = Featured (KRX 거래대금/시총/상승률 TOP)
- hotels.html = Hotels (ADR 추적)
- etf.html = ETF 구성종목 (조건부, etf_data.db 있을 때만)
- taiwan.html = Taiwan 월매출 (대만 큐레이션 53종목, 별도 생성기 create_taiwan_page.py)
- architecture.html = 아키텍처 (수동 관리)

## 파일 생성 의존 체인
```
Wrap_NAV.xlsx 변경 → calculate_wrap_nav.py → calculate_returns.py → create_dashboard.py
dataset.csv 변경 → draw_charts.py → create_dashboard.py
fetch_monthly_returns.py → monthly_returns.json → market.html (MONTHLY RETURNS 테이블)
taiwan_universe.csv(큐레이션 53종, 사용자 편집 가능) → fetch_taiwan_revenue.py → taiwan_revenue.csv → create_taiwan_page.py → taiwan.html (GHA daily_taiwan_revenue.yml 23:00 KST)
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
- 글씨체: **Pretendard** (2026-05-24 통일). `font-family: 'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif;`. 로드: `<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">`. Chart.js 사용 시 `Chart.defaults.font.family` 동일하게 설정
- 상단 탭바: 모든 페이지 공통. **WRAP / Market / Architecture 3개 메인 탭** (pill 모양, 라운드 직사각형 테두리). Market은 호버 시 6개 페이지(Market, 투자유의종목, Universe, SEIBro, Featured, ETF) 드롭다운. WRAP은 호버 시 5개 내부 탭(Dashboard, 공시, Order, AUM, 수수료) 드롭다운 — 링크는 `wrap.html#dashboard` 등 해시 방식이고, wrap.html의 `wrapTabFromHash()`가 hashchange/로드 시 해당 JS 탭으로 전환 (타 페이지에서 진입해도 동작). 드롭다운 항목은 `text-align: center` (`.topnav-sub`). 좌측 "Age of Emergence" 브랜드 클릭 시 index.html로 이동
- 우측 별도 Home 버튼은 사용 안 함 (탭바가 네비게이션 담당)
- create_dashboard.py 수정 시 모든 생성 파일 재생성 후 확인
- UI 변경 시 전체 페이지에서 일관성 확인
- **architecture.html 동기화 주의**: 자동 생성되지 않고 수동 관리됨. `TOP_NAV_CSS`, `top_nav_html()` 결과(상단 탭바 HTML)를 정적으로 박아넣은 상태이므로, `create_dashboard.py`의 헬퍼 함수(TOP_NAV_MAIN 멤버/순서/라벨, TOP_NAV_CSS, 폰트 등)를 수정할 때마다 architecture.html도 수동으로 동기화해야 함 (안 하면 다른 페이지와 탭바 디자인 어긋남)
