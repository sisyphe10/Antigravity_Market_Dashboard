---
id: "bot-sisyphe"
name: "Sisyphe-Bot (펀드/일상 텔레그램 봇)"
domain: "portfolio-wrap"
project: "antigravity"
type: "bot"
runs_on: "vm_macmini"
schedule_kst: "상시 (내부 잡 05:00~23:00)"
status: "active"
code:
  - "execution/sisyphe_bot.py"
  - "scripts/sisyphe-bot.service"
  - "launchd/bots/com.antigravity.sisyphe-bot.plist"
reads:
  - "store-portfolio-data"
  - "store-featured-data"
  - "store-orders-pending"
writes:
  - "page-market-alert"
  - "page-featured"
  - "subscribers.json"
depends_on:
  - "src-create-market-alert"
  - "src-journal-data"
  - "src-investor-trading"
  - "src-create-dashboard"
  - "infra-telegram"
alerts: "OnFailure → notify_sisyphe_failure.sh sisyphe-bot → 텔레그램"
---

# Sisyphe-Bot (펀드/일상 텔레그램 봇)

**Domain:** 포트폴리오 · WRAP · **Type:** Bot · **Runs on:** vm_macmini · **Schedule (KST):** 상시 (내부 잡 05:00~23:00) · **Status:** active · **Project:** antigravity

생태계의 중심 봇. python-telegram-bot JobQueue로 하루종일 포트폴리오·시장·가계부 잡을 돌린다(`execution/sisyphe_bot.py`, 134KB).

- **내부 스케줄(KST)**: 05:00 날씨 · 05:05 캘린더 · 09:30~15:35 30분 자동 포트폴리오 업데이트(거래일) · 16:05 투자유의 재생성(`src-create-market-alert`) · 16:10 투자일지(`src-journal-data`) · 16:20/18:30/08:30 Featured 1·2·3차 · 17:00 일간 리포트 publish · 20:00 백업 재시도 · 23:00 투자유의 야간.
- 가계부: Apps Script doPost가 거래를 직접 텔레그램 전송, 봇은 답장(분류/수정/제외) 처리.
- systemd `Restart=always`(10회 실패 시 중단+알림). 맥미니에선 launchd KeepAlive + wrapper로 등가 구현.
- 함정: JobQueue 가드/pytz 필요, 라이브 테스트는 VM 봇 중지 후.

## Reads
- [[store-portfolio-data]] — portfolio_data.json
- [[store-featured-data]] — featured_data.json / newhigh_20d.json
- [[store-orders-pending]] — orders/ (pending_orders · aum_pending)

## Writes
- [[page-market-alert]] — market_alert.html (투자유의종목)
- [[page-featured]] — featured.html (Featured TOP)
- `subscribers.json`

## Depends on
- [[src-create-market-alert]] — 투자유의 생성기 (create_market_alert.py)
- [[src-journal-data]] — 투자일지 시장데이터 (fetch_journal_data.py)
- [[src-investor-trading]] — 투자자별 수급 (fetch_investor_trading.py)
- [[src-create-dashboard]] — 대시보드 생성기 (create_dashboard.py)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `execution/sisyphe_bot.py`
- `scripts/sisyphe-bot.service`
- `launchd/bots/com.antigravity.sisyphe-bot.plist`

## Alerts
⚠ OnFailure → notify_sisyphe_failure.sh sisyphe-bot → 텔레그램
