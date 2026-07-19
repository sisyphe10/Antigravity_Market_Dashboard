---
id: "timer-us-etf-collect"
name: "미국 ETF NAV·AUM 수집 타이머 (us-etf-collect 화~토 09:00)"
domain: "market-global"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "09:00 화~토"
status: "active"
code:
  - "launchd/timers/com.antigravity.us-etf-collect.plist"
  - "scripts/run_us_etf_collect.sh"
  - "execution/etf_collector/collect_us_etf.py"
  - "execution/etf_collector/us_etf_config.py"
reads: []
writes:
  - "us_etf_history.csv"
  - ".us_etf_alert_sent.json"
  - "page-etf"
depends_on:
  - "ext-data-apis"
  - "src-create-dashboard"
  - "infra-telegram"
alerts: "실패 시 sisyphe-bot-notify(us-etf-collect) → 텔레그램"
---

# 미국 ETF NAV·AUM 수집 타이머 (us-etf-collect 화~토 09:00)

**Domain:** 해외 · 매크로 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 09:00 화~토 · **Status:** active · **Project:** antigravity

미국(+홍콩) ETF 28종의 NAV·AUM·종가·보수와 USDKRW 환율, 삼성전자·SK하이닉스 보유비중을 yfinance로 수집해 `us_etf_history.csv`에 적재하는 타이머(`run_us_etf_collect.sh` → `execution/etf_collector/collect_us_etf.py`). 2026-07-19 신설.

- 대상: 반도체 지수형·레버리지(SOXX/SMH/SOXL/SOXS 등), 메모리(DRAM/RAM), 홍콩 삼전·하이닉스 2x(7747/7709.HK), 한국 단일국가(EWY/FLKR), MSCI EM·FTSE 선진 등 한국 포함/미포함 대조군 — 대상 목록·한국 비중 추정 규칙은 `us_etf_config.py` 단일 출처(YTD 종가 백필 포함).
- 한국 비중 변동 4지표(총 AUM·실투자·삼전 노출·하이닉스 노출, 원화)를 Sisyphe-Bot으로 화~토 아침 발송(dedup=`.us_etf_alert_sent.json`, USDKRW 델타 포함).
- 수집 후 `etf.html` 미국 ETF 서브탭을 재생성(`create_dashboard.generate_etf_html`, main 미추적 로컬 산출물) → 게시는 래퍼 publish_snapshot이 담당. `us_etf_history.csv`만 race-safe push.
- 홍콩 2종(.HK)은 yfinance NAV가 stale이라 가격(HKD)·AUM(USD)만 수집. 09:00 화~토 = 미국 마감·NAV 확정 후이자 KRX 개장 전.
- flock으로 래퍼 중복 실행 방지. Timeout/실패 시 `sisyphe-bot-notify@us-etf-collect`.

## Reads
- (none)

## Writes
- `us_etf_history.csv`
- `.us_etf_alert_sent.json`
- [[page-etf]] — etf.html (ETF 구성종목)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `launchd/timers/com.antigravity.us-etf-collect.plist`
- `scripts/run_us_etf_collect.sh`
- `execution/etf_collector/collect_us_etf.py`
- `execution/etf_collector/us_etf_config.py`

## Alerts
⚠ 실패 시 sisyphe-bot-notify(us-etf-collect) → 텔레그램
