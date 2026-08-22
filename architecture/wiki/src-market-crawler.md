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

- 수집: DRAM/NAND(DRAMeXchange), 원자재·크립토·FX·지수(yfinance), SMM 리튬(탄산), Sunsirs 폴리실리콘·수산화리튬, 해상운임(SCFI), 미국/한국/글로벌 지수.
- 서브 크롤러 호출: `crawl_kpx_smp`(SMP), `crawl_silicondata_indexes`(LLM토큰/H100렌탈/RAM). 각각 실패 격리(계속 진행).
- 리튬은 별도 모듈 없이 이 크롤러에 접혀 있음(hq.smm.cn · sunsirs.com).
- ★**SMM 리튬 숨김 대응(2026-08-22)**: SMM이 2026-08-21부로 비로그인 사용자에게 전지급 리튬 시세를 감추면서(`hide_data:true`, avg=0) 크롤러가 **0.0을 그대로 시계열에 적재**했다. ① `avg<=0` 행은 저장하지 않고 스킵하는 가드(값이 없으면 0이 아니라 빈칸). ② **탄산리튬은 SMM 지수(`202212050001`) 히스토리로 승계** — 21일 겹침 실측에서 지수가 스팟 대비 +1.00%(std 0.18%p)로 안정적이라 `SMM_INDEX_SPOT_RATIO=1.0100`으로 나눠 보정한 뒤 롤링 히스토리를 전량 append 한다(중복은 `save_to_csv`가 (날짜, 제품명)으로 걸러 기존 스팟 값은 보존되고 빈 날짜만 채워진다). ③ **수산화리튬은 지수-스팟 스프레드가 불안정(-2.4~-4.8%)해 승계를 기각** — 구 SMM `Lithium Hydroxide` 시리즈는 2026-08-20에서 동결하고 아래 Sunsirs 신규 시리즈로 대체했다.
- **Sunsirs 수산화리튬 신설(2026-08-22, `crawl_sunsirs_lithium_hydroxide`)**: `Lithium Hydroxide Sunsirs`(CNY/톤) 시리즈. HW_CHECK 쿠키 2단계 핸드셰이크는 폴리실리콘 크롤러와 동일 패턴을 재사용하고, 주말 행은 금요일 값 이월이라 제외해 구 SMM 시리즈와 같이 거래일만 적재한다. [[page-market]] DATA 차트의 **표시명은 `Lithium Hydroxide` 그대로 두고 csv 키만 새 시리즈로 갈아끼웠다**(롤백=csv 키를 구 이름으로 원복). country/단위/정렬 배선도 새 키 기준으로 추가.
- DRAM은 기존 최고가(High) 시리즈에 더해 **세션 평균가를 `<이름> Avg` 시리즈로 병행 수집**(2026-07-23~, 최저≤평균≤최고 정합 검증) → MEMORY 차트 그룹에 배선.
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
