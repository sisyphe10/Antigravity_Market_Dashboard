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

상시 봇 4종·systemd 타이머 8종·VM cron(git-pull, earnings sync)을 돌리는 리눅스 컴퓨트 호스트. 현재는 Oracle Cloud VM(144.24.70.224, Ubuntu, systemd, Python 3.10.12). 

- **이전 진행 중**: 사용자의 맥미니(Apple Silicon, macOS, launchd)로 흡수 예정. Phase 1(봇·타이머·system 데몬)은 임박, Phase 2(GHA 스케줄 잡 흡수)는 안정화 후. 변환물은 `launchd/` 트리에 초안으로 존재.
- KRX/KOSIS/SEAJ 등 클라우드 IP가 차단하는 소스는 GHA가 아닌 이 호스트에서만 인증 수집이 된다(pykrx 로그인 등).
- 메모리 356Mi 저사양 → 크롬 selenium 잡이 메모리를 굶기면 다른 잡을 죽이는 사고 이력(호텔 ADR 은퇴 원인).
- 시각 판단은 로컬 시계 말고 `TZ=Asia/Seoul date`(VM)로.

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
