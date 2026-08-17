---
id: "src-universe"
name: "유니버스 수집 (fetch_universe.py)"
domain: "market-global"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "18:30 / 07:00 (gha-daily-universe)"
status: "active"
code:
  - "execution/fetch_universe.py"
  - "execution/fetch_index_returns.py"
reads:
  - "universe_tickers.csv"
writes:
  - "store-universe-json"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# 유니버스 수집 (fetch_universe.py)

**Domain:** 해외 · 매크로 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 18:30 / 07:00 (gha-daily-universe) · **Status:** active · **Project:** antigravity

관심 유니버스 종목 시세/지표를 yfinance로 수집해 `universe.json`+`universe_history.json` 생성.

- 52주 낙폭(DD), RSI(1M)는 fetch_index_returns 산출을 소비.
- 종목 추가=universe_tickers.csv 행+타겟 주입(전체 2회 실행 금지). 멀티인스턴스는 별도 경로.
- **중국 A주 지원(2026-07-27)**: `PREFIX_MAP`에 SHA→`.SS`(상하이/科创板)·SHE→`.SZ`(선전/创业板) 추가, 통화 CNY(`fetch_fx_to_krw`에 `CNYKRW=X`, 폴백 216). `THRESHOLD_BY_CURRENCY` CNY=0.20(科创板 20% 가격제한). 첫 종목 CXMT(SHA:688825, ChangXin Memory, 2026-07-27 상장). A주 시세 primary는 텐센트 gtimg, yfinance는 폴백.
- **A주 RSI(1M) 벤치마크 = CSI 300 추가(2026-08-17)**: `fetch_index_returns.py`의 `INDICES`에 CSI 300(沪深300)을 넣고 `INDEX_BY_PREFIX`에 SHA·SHE → `CSI 300` 매핑을 더했다 — 종전 A주 종목은 대응 지수가 없어 RSI(1M)(종목 1M − 지수 1M)가 비어 있었다. 지수 소스는 **야후가 아니라 텐센트 gtimg(`sh000300`)** — 야후 `000300.SS`는 일봉이 통째 비는 구간이 관측돼(2026-08 실측: 7/17 다음 봉이 8/17) 21거래일 lookback이 어긋난다. 이로써 종목·지수 양쪽 A주 primary가 gtimg로 일치한다. 구현은 지수 전용 우회로(`TENCENT_INDICES` → `fetch_tencent_index_closes`)로, 1M 수익률·1y 히스토리 두 경로 모두에서 yfinance보다 앞서 분기한다.

## Reads
- `universe_tickers.csv`

## Writes
- [[store-universe-json]] — universe.json / universe_history.json

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_universe.py`
- `execution/fetch_index_returns.py`
