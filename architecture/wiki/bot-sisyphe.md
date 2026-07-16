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
  - "execution/daily_portfolio_report.py"
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

- **내부 스케줄(KST)**: 05:00 날씨 · 05:05 캘린더 · 09:10·09:30~15:35 30분 자동 포트폴리오 업데이트(거래일) · 16:05 투자유의 재생성(`src-create-market-alert`) · 16:10 투자일지(`src-journal-data`) · 16:20/18:30/08:30 Featured 1·2·3차 · 17:00 일간 리포트 publish · 20:00 백업 재시도 · 23:00 투자유의 야간.
- **17:00 일간 리포트(`daily_portfolio_report.py`)**: 별도 잡이 아니라 **봇이 subprocess로 부르는 내부 잡** — 정기 발송은 `daily_portfolio_job`, `/portfolio` 명령은 같은 스크립트를 `--no-send`로 돌려 stdout을 답장한다(개별 카드 없이 이 봇 카드에 흡수 — `architecture/REGISTRY_NOTES.md`). 거래일만 발송하고, 당일 중복 발송은 전송일자 기록으로 차단. 16:00→17:00으로 옮긴 이유는 KIS 확정 종가 확보 후 publish하기 위함.
- **리포트 표기 규약(2026-07-16 확정)**: 텍스트는 `기준가`+`수익률` 2블록, 종목 구성은 PNG 표로 분리 전송. **기준가=전 상품 개별 / 수익률=일반형 그룹대표+벤치마크+전환형 개별**의 비대칭이 핵심 — 수익률만 `wrap_config.report_return_products()`가 같은 `group`의 일반형을 대표 1줄(트루밸류)로 접는다(포트가 수렴해 같은 숫자라서). 순서는 **벤치마크 선두** = KOSPI → KOSDAQ → 일반형 → 목표전환형. 종목 PNG는 그룹 병합을 시도했다가(`e9289560`) 되돌려 **현재는 전체 개별**(일반형 랩 대표 + 단독 일반형 + 활성 전환형 각 1장)이고, 종목별 `YTD` 컬럼이 붙었다.
  - ★`get_portfolio_holdings`/`format_message` docstring은 아직 "그룹 대표 1장씩만 보낸다"는 폐기된 설계를 기술한다(`26ed7df6`이 `_group_reps()`를 걷어냄) — **docstring이 stale**, 실제 전송부는 개별. `daily_portfolio_job` docstring의 "오후 4시"도 17:00 이관 전 잔재.
- **`/update` 동일구성 그룹핑(2026-07-16)**: `format_update_summary`가 `(종목명, D-1 비중 1자리)` 시그니처가 같은 상품을 한 블록으로 묶어 **종목 기여 리스트를 1회만** 출력한다. 수렴 전·신규 출시라 구성이 어긋난 상품은 시그니처가 달라 **자동으로 별도 블록**이 되는 자기적응 구조. 상품별 YTD·누적은 `_portfolio_meta`의 D-1 값에 당일 등락을 복리 결합해 상품마다 따로 보존.
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
- `execution/daily_portfolio_report.py`
- `scripts/sisyphe-bot.service`
- `launchd/bots/com.antigravity.sisyphe-bot.plist`

## Alerts
⚠ OnFailure → notify_sisyphe_failure.sh sisyphe-bot → 텔레그램
