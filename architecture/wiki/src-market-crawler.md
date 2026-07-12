---
id: "src-market-crawler"
name: "마스터 시장 크롤러 (market_crawler.py)"
domain: "market-global"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "23:00 (daily_crawl)"
status: "active"
code:
  - "execution/market_crawler.py"
reads:
  - "config.py"
writes:
  - "store-dataset-csv"
depends_on:
  - "src-smp-kpx"
  - "src-silicondata"
  - "ext-data-apis"
alerts: ""
---

# 마스터 시장 크롤러 (market_crawler.py)

**Domain:** 해외 · 매크로 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 23:00 (daily_crawl) · **Status:** active · **Project:** antigravity

dataset.csv에 원자재·메모리·시세 시계열을 적재하는 daily_crawl의 핵심 수집기.

- 수집: DRAM/NAND(DRAMeXchange), 원자재·크립토·FX·지수(yfinance), SMM 리튬(탄산/수산화), Sunsirs 폴리실리콘, 해상운임(SCFI), 미국/한국/글로벌 지수.
- 서브 크롤러 호출: `crawl_kpx_smp`(SMP), `crawl_silicondata_indexes`(LLM토큰/H100렌탈/RAM). 각각 실패 격리(계속 진행).
- 리튬은 별도 모듈 없이 이 크롤러에 접혀 있음(hq.smm.cn).
- ★미국 지수는 **마감 세션만 적재**(2026-07-12 수정): 장중 스냅샷이 종가로 오염되던 문제를 완결 세션 기준 수집 + 오염 행 재작성으로 근본수정. 지수 임베드는 YTD 보장.

## Reads
- `config.py`

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[src-smp-kpx]] — KPX 육지 SMP (fetch_smp_kpx.py)
- [[src-silicondata]] — SiliconData 지수 3종 (fetch_silicondata_index.py)
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/market_crawler.py`
