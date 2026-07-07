---
id: "bot-ra-sisyphe"
name: "RA_Sisyphe_bot (리서치 알림 봇)"
domain: "news-research"
project: "antigravity"
type: "bot"
runs_on: "vm_macmini"
schedule_kst: "상시 (내부 잡 05:10~21:00)"
status: "active"
code:
  - "execution/ra_sisyphe_bot.py"
  - "scripts/ra-sisyphe-bot.service"
  - "launchd/bots/com.antigravity.ra-sisyphe-bot.plist"
reads:
  - "sources.json"
  - "disclosures.json"
  - "store-featured-data"
  - "page-market-alert"
writes:
  - "store-sources-state"
  - "subscribers_ra_sisyphe.json"
depends_on:
  - "src-generic-pipeline"
  - "src-semianalysis"
  - "src-trendforce"
  - "src-foreign-ir"
  - "src-kna-kneiss"
  - "src-dart-disclosures"
  - "src-kind-disclosures"
  - "infra-telegram"
alerts: "OnFailure → notify_sisyphe_failure.sh ra-sisyphe-bot → 텔레그램"
---

# RA_Sisyphe_bot (리서치 알림 봇)

**Domain:** 뉴스 · 리서치 · **Type:** Bot · **Runs on:** vm_macmini · **Schedule (KST):** 상시 (내부 잡 05:10~21:00) · **Status:** active · **Project:** antigravity

리서치·공시·뉴스 알림 전담 봇(`execution/ra_sisyphe_bot.py`). 보유종목/시장 관련 외부 소스를 폴링해 텔레그램 다이제스트로 발송.

- **내부 스케줄(KST)**: 05:10 리서치 헤드라인 · 05:15 투자유의 요약 · 07:00~15:00 매시 + 18:00 통합 WiseReport 신규 리포트 · 16:00 20일 신고가 · 17:00 공시 수집→17:30 발송(DART+KIND) · 월 09:10 해외IR 사각지대 점검.
- **Generic Source Pipeline**: `sources.json`을 부팅 시 로드해 소스별 잡을 등록 — SemiAnalysis(09:00/21:00), TrendForce(08:00), 해외 IR 뉴스룸(07:30/20:00), k-neiss 원전(18:00).
- 신규 소스 추가 = `execution/sources/<name>.py` + sources.json 엔트리 + deploy.
- 구독자 `subscribers_ra_sisyphe.json`.

## Reads
- `sources.json`
- `disclosures.json`
- [[store-featured-data]] — featured_data.json / newhigh_20d.json
- [[page-market-alert]] — market_alert.html (투자유의종목)

## Writes
- [[store-sources-state]] — sources_state/ + kna_state.json
- `subscribers_ra_sisyphe.json`

## Depends on
- [[src-generic-pipeline]] — Generic Source Pipeline (execution/sources/)
- [[src-semianalysis]] — SemiAnalysis 소스 (sources/semianalysis.py)
- [[src-trendforce]] — TrendForce 소스 (sources/trendforce.py)
- [[src-foreign-ir]] — 해외 기업 IR/뉴스룸 (sources/foreign_ir.py)
- [[src-kna-kneiss]] — 원전 뉴스 KNA/KNEISS (sources/kna.py)
- [[src-dart-disclosures]] — DART 공시 (fetch_disclosures.py)
- [[src-kind-disclosures]] — KIND 거래소 공시 (fetch_kind_disclosures.py)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `execution/ra_sisyphe_bot.py`
- `scripts/ra-sisyphe-bot.service`
- `launchd/bots/com.antigravity.ra-sisyphe-bot.plist`

## Alerts
⚠ OnFailure → notify_sisyphe_failure.sh ra-sisyphe-bot → 텔레그램
