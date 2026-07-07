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

- 기록자: market_crawler, ECOS/FRED/KOFIA/NPS/KRX/KOSIS/일본capex, SMP, SiliconData 등.
- 소비자: create_dashboard(market.html DATA 섹션), draw_charts.
- append-only라 과거 잠정값 정정은 rebuild 필요. 타입→카테고리 매핑은 `config.py` CATEGORY_MAP.

## Reads
- (none)

## Writes
- (none)

## Depends on
- (none)

## Code
- `config.py`
