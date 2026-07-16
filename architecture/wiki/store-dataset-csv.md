---
id: "store-dataset-csv"
name: "dataset.csv (시장 시계열 통합)"
domain: "market-global"
project: "antigravity"
type: "dataset"
runs_on: "github"
schedule_kst: "다수 잡 append"
status: "active"
code:
  - "config.py"
reads: []
writes: []
depends_on: []
alerts: ""
---

# dataset.csv (시장 시계열 통합)

**Domain:** 해외 · 매크로 · **Type:** Dataset · **Runs on:** github · **Schedule (KST):** 다수 잡 append · **Status:** active · **Project:** antigravity

생태계의 시계열 데이터 통합 저장소(~1.9MB, append-only). 원자재/메모리/지수/금리/매크로/capex 등 모든 시계열이 `날짜,이름,값,타입` 형태로 쌓인다.

- 기록자: market_crawler, ECOS/FRED/KOFIA/NPS/KRX/KOSIS/일본capex, SMP, SiliconData, 파생·수급([[src-deriv-daily]]) 등.
- 소비자: create_dashboard(market.html DATA 섹션), draw_charts, [[timer-wrap-principle-check]](KOSPI 20일선).
- append-only라 과거 잠정값 정정은 rebuild 필요. 타입→카테고리 매핑은 `config.py` CATEGORY_MAP.
- 2026-07-16 **파생·수급 13종 추가**(삼성전자·SK하이닉스 현선물 괴리율/미결제약정/미결제약정 금액/공매도잔고/시가총액/레버리지 ETF AUM + VKOSPI) — 이력은 커밋 `19eeefcd`로 백필. 이 계열은 append-only 예외로 **최근 7일 upsert**(T+2 공시인 공매도잔고를 뒤늦게 정정하기 위함).

## Reads
- (none)

## Writes
- (none)

## Depends on
- (none)

## Code
- `config.py`
