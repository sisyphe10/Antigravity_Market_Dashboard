---
id: "infra-ups"
name: "UPS (무정전 전원, 맥미니 대비)"
domain: "ops-infra"
project: "antigravity"
type: "infra"
runs_on: "external"
schedule_kst: ""
status: "planned"
code: []
reads: []
writes: []
depends_on:
  - "infra-vm-macmini"
alerts: ""
---

# UPS (무정전 전원, 맥미니 대비)

**Domain:** 운영 · 인프라 · **Type:** Infra · **Runs on:** external · **Status:** planned · **Project:** antigravity

맥미니 자가호스팅 전환에 대비한 무정전 전원 장치. 아직 도입 전(planned).

- 클라우드 VM과 달리 가정 호스팅은 정전에 취약 → catch-up 러너(부팅 시 놓친 잡 복구)와 함께 가용성 축을 이룬다.
- 정전/재부팅 시 놓친 스케줄 잡은 `daemon-catchup`이 stamp 기준으로 재실행.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)

## Code
- (none)
