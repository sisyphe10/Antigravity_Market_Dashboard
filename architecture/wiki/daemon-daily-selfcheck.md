---
id: "daemon-daily-selfcheck"
name: "일일 셀프체크 다이제스트 (08:50, dead-man's switch)"
domain: "ops-infra"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "08:50 매일"
status: "planned"
code:
  - "launchd/system/daily_selfcheck.sh"
  - "launchd/system/com.antigravity.daily-selfcheck.plist"
reads:
  - "logs/launchd/stamps/"
  - "logs/launchd/starts/"
writes: []
depends_on:
  - "infra-vm-macmini"
  - "infra-telegram"
alerts: "매일 발송(침묵이 곧 경보) → 텔레그램"
---

# 일일 셀프체크 다이제스트 (08:50, dead-man's switch)

**Domain:** 운영 · 인프라 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 08:50 매일 · **Status:** planned · **Project:** antigravity

맥미니 상태를 매일 08:50 KST 텔레그램 한 줄로 요약하는 launchd 데몬(`com.antigravity.daily-selfcheck`). **정상이어도 매일 발송** — 메시지의 존재 자체가 liveness 신호(침묵=다운).

- 수집: 봇 4종 running 여부 · 타이머 8종 stamp 신선도(OK n/N) · 24h 재시작 수 · 디스크 여유 · git-pull 실패연속/HEAD 나이.
- 실제 문제(봇 다운/타이머 STALE/디스크 부족)만 ⚠️ 라인으로 헤더를 뒤집는다.
- 실적 다이제스트(08:00) 후, 신선도 워치독(11:00) 전 배치.
- **신규 추가(2026-07-06 커밋), 맥미니 전용 → 컷오버 시 활성(planned).** VM엔 대응 잡 없음.

## Reads
- `logs/launchd/stamps/`
- `logs/launchd/starts/`

## Writes
- (none)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `launchd/system/daily_selfcheck.sh`
- `launchd/system/com.antigravity.daily-selfcheck.plist`

## Alerts
⚠ 매일 발송(침묵이 곧 경보) → 텔레그램
