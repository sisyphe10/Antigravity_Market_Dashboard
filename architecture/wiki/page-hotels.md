---
id: "page-hotels"
name: "hotels.html (호텔 ADR, 동결)"
domain: "market-global"
project: "antigravity"
type: "page"
runs_on: "github"
schedule_kst: ""
status: "frozen"
code:
  - "execution/create_dashboard.py"
reads:
  - "hotel_adr.csv"
writes: []
depends_on:
  - "src-create-dashboard"
alerts: ""
---

# hotels.html (호텔 ADR, 동결)

**Domain:** 해외 · 매크로 · **Type:** Page · **Runs on:** github · **Status:** frozen · **Project:** antigravity

booking.com 호텔 ADR 추적 페이지. **데이터 동결**(수집 타이머 은퇴 2026-07-06).

- 차트는 PNG→Chart.js 전환 완료(매 실행 PNG 재생성발 머지충돌 소멸)라 페이지 자체는 정상 렌더, 다만 `hotel_adr.csv`가 더 안 갱신됨.
- `create_dashboard.py`가 여전히 생성 목록에 포함하나 신규 데이터 없음.

## Reads
- `hotel_adr.csv`

## Writes
- (none)

## Depends on
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)

## Code
- `execution/create_dashboard.py`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/hotels.html)
