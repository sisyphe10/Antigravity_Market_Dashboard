---
id: "timer-wrap-principle-check"
name: "WRAP 원칙 점검 타이머 (17:10, 변화 시에만 발송)"
domain: "portfolio-wrap"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "17:10 평일"
status: "active"
code:
  - "launchd/timers/com.antigravity.wrap-principle-check.plist"
  - "execution/wrap_principle_check.py"
reads:
  - "store-portfolio-data"
  - "store-wrap-nav-xlsx"
  - "store-dataset-csv"
  - "config/wrap_principles_config.json"
writes:
  - "logs/wrap_principle_state.json"
depends_on:
  - "src-create-portfolio-tables"
  - "infra-telegram"
alerts: "FAIL → notify_sisyphe_failure.sh wrap-principle-check → 텔레그램"
---

# WRAP 원칙 점검 타이머 (17:10, 변화 시에만 발송)

**Domain:** 포트폴리오 · WRAP · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 17:10 평일 · **Status:** active · **Project:** antigravity

2026-07-16 신설. 매일 17:10 KST WRAP 포트폴리오의 투자원칙 준수를 점검해 **위반 상태가 변했을 때만** 텔레그램(🧭)으로 알리는 타이머(`com.antigravity.wrap-principle-check` → `execution/wrap_principle_check.py`). 16:xx 수집·리포트 잡들 뒤에 배치.

- **알림 설계(v2, 변화 기반)**: 행위 룰(당일 발생 시 항상) = 물타기 의심(원칙17)·약세장 신규 편입(원칙11). 상태 룰(변화 기반) = 계좌 MDD(원칙3)·섹터 쏠림(원칙26)·종목 DD·삥(원칙25)·종목 수 상한·단일 종목 쏠림·지수 20일선(원칙8) — 신규 진입 🆕 / 해소 ✅ 에만 상세, 지속분은 요약 1줄. **변화·행위가 없으면 평일 침묵**, 월요일은 전체 상세 리포트.
- 전일 상태 = `logs/wrap_principle_state.json`(diff 근거). 첫 실행은 baseline 스냅숏만 저장해 🆕 도배를 막고, `WPC_SEED` 환경변수는 무발송 시드 모드(배포 직후 상태 동기화용). 행위 룰은 `actions_sent`+날짜로 당일 재발송 차단, 종목 단위 룰은 상품 중복 없이 1회만 표기.
- 임계값은 `config/wrap_principles_config.json`(없으면 코드의 `DEFAULTS` — 종목 수 15·최소비중 2%·섹터 65%·종목 DD -30%·NAV MDD -10% 등). 주말은 자체 스킵.
- 입력은 `portfolio_data.json`(보유·비중)·`Wrap_NAV.xlsx`(NAV 드로다운)·`dataset.csv`(KOSPI 20일선, 17:10 시점엔 통상 D-1 종가라 기준일을 문구에 명기). `portfolio_data.json`이 30시간보다 오래되면 갱신 지연 경고를 덧붙인다.
- wrapper 타임아웃 300초(`run_timer_job.sh`), 설치는 `install_timers.sh` NAMES 목록.

## Reads
- [[store-portfolio-data]] — portfolio_data.json
- [[store-wrap-nav-xlsx]] — Wrap_NAV.xlsx (랩 운용 원장)
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)
- `config/wrap_principles_config.json`

## Writes
- `logs/wrap_principle_state.json`

## Depends on
- [[src-create-portfolio-tables]] — 포트폴리오 표 생성 (create_portfolio_tables.py)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `launchd/timers/com.antigravity.wrap-principle-check.plist`
- `execution/wrap_principle_check.py`

## Alerts
⚠ FAIL → notify_sisyphe_failure.sh wrap-principle-check → 텔레그램
