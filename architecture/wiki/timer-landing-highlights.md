---
id: "timer-landing-highlights"
name: "랜딩 하이라이트 타이머 (18:35)"
domain: "ops-infra"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "18:35 매일"
status: "active"
code:
  - "scripts/landing-highlights.timer"
  - "scripts/landing-highlights.service"
  - "scripts/run_landing_highlights.sh"
  - "launchd/timers/com.antigravity.landing-highlights.plist"
reads:
  - "page-market-alert"
  - "page-seibro"
  - "store-featured-data"
writes:
  - "store-landing-highlights"
depends_on:
  - "src-landing-highlights"
alerts: "OnFailure → landing-highlights-notify.service → 텔레그램"
---

# 랜딩 하이라이트 타이머 (18:35)

**Domain:** 운영 · 인프라 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 18:35 매일 · **Status:** active · **Project:** antigravity

매일 18:35 KST(Featured 2차 마감 후) index.html 회전 위젯 데이터(sparkline+한줄 코멘트, 50슬롯)를 생성하는 타이머(`run_landing_highlights.sh` → `create_landing_highlights.py`).

- 여러 산출물(market_alert/seibro/featured 등)에서 하이라이트를 뽑아 `landing_highlights.json`으로.
- RandomizedDelaySec=60. TimeoutStartSec=5min. stale lockfile 주의.
- 실패 시 `landing-highlights-notify.service`.

## Reads
- [[page-market-alert]] — market_alert.html (투자유의종목)
- [[page-seibro]] — seibro.html (SEIBro)
- [[store-featured-data]] — featured_data.json / newhigh_20d.json

## Writes
- [[store-landing-highlights]] — landing_highlights.json

## Depends on
- [[src-landing-highlights]] — 랜딩 하이라이트 생성 (create_landing_highlights.py)

## Code
- `scripts/landing-highlights.timer`
- `scripts/landing-highlights.service`
- `scripts/run_landing_highlights.sh`
- `launchd/timers/com.antigravity.landing-highlights.plist`

## Alerts
⚠ OnFailure → landing-highlights-notify.service → 텔레그램
