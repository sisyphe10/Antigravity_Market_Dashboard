---
id: "daemon-daily-selfcheck"
name: "일일 셀프체크 다이제스트 (08:50, 이상 시에만 발송)"
domain: "ops-infra"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "08:50 매일"
status: "active"
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
alerts: "이상(⚠️) 있을 때만 발송 → 텔레그램 · 정상일은 무음(로그만)"
---

# 일일 셀프체크 다이제스트 (08:50, 이상 시에만 발송)

**Domain:** 운영 · 인프라 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 08:50 매일 · **Status:** active · **Project:** antigravity

맥미니 상태를 매일 08:50 KST 점검해 **이상이 있을 때만** 텔레그램으로 요약을 보내는 launchd 데몬(`com.antigravity.daily-selfcheck`). 2026-07-11 컷오버로 라이브.

- ★**2026-07-15 설계 반전(사용자 지시)**: 원래는 정상이어도 매일 발송해 메시지 존재 자체가 liveness 신호인 dead-man's switch였으나, 매일의 정상 알림 소음이 그 값어치를 넘어선다고 판단 — warn이 없으면 발송을 생략하고 로컬 로그만 남긴다. **dead-man 감시 역할은 외부 워치독([[gha-daily-health-check]], 11:00 KST)이 승계** — 맥미니가 통째로 죽어도 GitHub 쪽에서 잡히므로 침묵이 감시 공백이 되지 않는다.

- 수집: 봇 4종 running 여부 · **`schedule.tsv` 등재 타이머**(2026-07-16 기준 10종 — memento-telegram·wrap-principle-check 추가) stamp 신선도(OK n/N) · 24h 재시작 수 · 디스크 여유 · git-pull 실패연속/HEAD 나이. 타이머 목록은 하드코딩이 아니라 `schedule.tsv`를 읽어 열거 — 새 타이머는 그 표에 등재되는 순간 자동으로 감시망에 든다.
- **웹 섹션(2026-07-11 W9 추가)**: Caddy(`com.antigravity.web`) running · ts.net 도달성(자기 ts.net을 tailscale IP로 resolve) · 게시 스냅숏(`current`) 나이.
- 실제 문제(봇 다운/타이머 STALE/디스크 부족/웹 다운)만 ⚠️ 라인이 되고, 그 warn 유무가 곧 발송 여부다. ℹ️ 라인(24h 재시작 수·대형 로그)은 참고 정보라 단독으로는 발송을 유발하지 않는다.
- 실적 다이제스트(08:00) 후, 신선도 워치독(11:00) 전 배치.

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
⚠ 이상(⚠️) 있을 때만 발송 → 텔레그램 · 정상일은 무음(로그만)
