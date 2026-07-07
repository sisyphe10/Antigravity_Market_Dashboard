---
id: "timer-hotel-adr"
name: "호텔 ADR 타이머 (12:00, 은퇴)"
domain: "market-global"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "12:00 매일 (disabled)"
status: "retired"
code:
  - "scripts/hotel-adr.timer"
reads: []
writes:
  - "hotel_adr.csv"
depends_on: []
alerts: ""
---

# 호텔 ADR 타이머 (12:00, 은퇴)

**Domain:** 해외 · 매크로 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 12:00 매일 (disabled) · **Status:** retired · **Project:** antigravity

booking.com 호텔 ADR(lead +7/+14/+30)을 수집하던 타이머. **2026-07-06 전면 은퇴**(VM timer disabled).

- 은퇴 사유: 크롬 selenium 잡이 저사양 VM 메모리를 굶겨 12:00 /update 잡을 죽인 사고. `hotels.html` 데이터는 동결.
- systemd 유닛/러너/`fetch_hotel_adr.py`는 origin에서 이미 삭제됨(dead code 정리 커밋 e33ce836). `hotel_adr.csv`·`hotels.html`은 동결 상태로 잔존.
- launchd 이전 타이머 세트에도 미포함(정상). 이 카드는 이력 보존용.

## Reads
- (none)

## Writes
- `hotel_adr.csv`

## Depends on
- (none)

## Code
- `scripts/hotel-adr.timer`
