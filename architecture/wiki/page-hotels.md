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
  - "hotels.html"
reads:
  - "hotel_adr.csv"
writes: []
depends_on: []
alerts: ""
---

# hotels.html (호텔 ADR, 동결)

**Domain:** 해외 · 매크로 · **Type:** Page · **Runs on:** github · **Status:** frozen · **Project:** antigravity

booking.com 호텔 ADR 추적 페이지. **데이터 동결**(수집 타이머 은퇴 2026-07-06).

- 차트는 PNG→Chart.js 전환 완료(매 실행 PNG 재생성발 머지충돌 소멸)라 페이지 자체는 정상 렌더, 다만 `hotel_adr.csv`가 더 안 갱신됨.
- ★**생성물이 아니라 동결된 정적 HTML(2026-08-17 정정)**: 종전 이 문서는 `create_dashboard.py`가 생성 목록에 포함한다고 적었으나, 생성기 소스 전수로 `hotels.html`을 쓰는 코드는 없다([[src-create-dashboard]]가 쓰는 것은 market/index/wrap/universe/seibro/featured_legacy/etf 7개). GHA·launchd 잡의 커밋 파일 목록에만 이름이 남아 있어 생성되는 것처럼 보였을 뿐 — 실제로는 내용이 바뀌지 않는다.
- 다만 `hotel_adr.csv` 자체는 [[src-create-dashboard]]가 계속 읽는다. 용도는 이 페이지가 아니라 **[[page-market]] DATA 차트의 `Hotel {city}` 시리즈**(도시별 ADR 평균을 빌드타임에 dataset으로 inject, 수집 호텔 목록은 사이드바 title 툴팁). 즉 동결 데이터의 열람 창구는 사실상 market DATA 쪽으로 옮겨져 있다.
- 따라서 양식·nav 규격 변경 시 이 페이지는 자동으로 따라오지 않는다([[page-universe-lab]]과 같은 부류).

## Reads
- `hotel_adr.csv`

## Writes
- (none)

## Depends on
- (none)

## Code
- `hotels.html`

## Links
- [라이브](https://sisyphe10.github.io/Antigravity_Market_Dashboard/hotels.html)
