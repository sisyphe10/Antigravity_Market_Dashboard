---
id: "infra-vm-macmini"
name: "컴퓨트 호스트 (Oracle VM → 맥미니)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "vm_macmini"
schedule_kst: "상시"
status: "active"
code:
  - "scripts/deploy.sh"
  - "scripts/inventory_vm.sh"
  - "launchd/"
reads: []
writes: []
depends_on:
  - "infra-github"
alerts: "봇/타이머 실패 → notify_sisyphe_failure.sh → 텔레그램"
---

# 컴퓨트 호스트 (Oracle VM → 맥미니)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** vm_macmini · **Schedule (KST):** 상시 · **Status:** active · **Project:** antigravity

상시 봇 4종·타이머 8종·GHA 이관 잡·system 데몬을 돌리는 컴퓨트 호스트. **2026-07-11 Oracle VM→맥미니 컷오버 완료** — 봇 4·타이머 8·GHA 이관 잡 10종(taiwan 포함)이 전부 `/Library/LaunchDaemons` launchd로 이전됐고, Oracle VM(144.24.70.224, Ubuntu)은 은퇴 대기 상태다. 현 라이브 호스트 = 맥미니(Apple Silicon, macOS, launchd).

- 컷오버로 함께 신설된 계층: 웹 서빙([[web-caddy]]·[[web-publish-snapshot]]·[[web-publish-pages]]), Sisyphe 클론 서빙([[daemon-sisyphe-pull]]), 데이터레이크([[infra-datalake]]), 아키텍처 자동 최신화([[timer-architecture-daily]]).
- KRX/KOSIS/SEAJ 등 클라우드 IP가 차단하는 소스는 GHA가 아닌 이 호스트에서만 인증 수집이 된다(pykrx 로그인 등).
- launchd 잡 실패는 wrapper가 `notify_sisyphe_failure.sh`로 알리고, 일일 셀프체크([[daemon-daily-selfcheck]])가 dead-man's switch를 담당.
- 시각 판단은 반드시 이 맥의 `date`(KST) 기준.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[infra-github]] — GitHub (정본 repo · Pages · Actions)

## Code
- `scripts/deploy.sh`
- `scripts/inventory_vm.sh`
- `launchd/`

## Alerts
⚠ 봇/타이머 실패 → notify_sisyphe_failure.sh → 텔레그램
