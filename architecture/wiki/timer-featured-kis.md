---
id: "timer-featured-kis"
name: "Featured KIS 수집 타이머 (15:50, 신고가)"
domain: "portfolio-wrap"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "15:50 매일"
status: "active"
code:
  - "scripts/featured-kis.timer"
  - "scripts/featured-kis.service"
  - "launchd/timers/com.antigravity.featured-kis.plist"
reads: []
writes:
  - "store-featured-data"
  - "featured_data_kis.json"
depends_on:
  - "src-featured-kis"
alerts: ""
---

# Featured KIS 수집 타이머 (15:50, 신고가)

**Domain:** 포트폴리오 · WRAP · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 15:50 매일 · **Status:** active · **Project:** antigravity

매일 15:50 KST 20일 신고가(`newhigh_20d.json`)를 생성하고 테마를 enrich하는 타이머(`fetch_featured_data_kis.py` + `enrich_newhigh_themes.py`).

- 16:00 RA_Sisyphe_bot 신고가 알림에 선행 수집(장 마감 직후 KIS 확정 시세).
- enrich 실패해도 수집 결과는 유지(ExecStartPost `-` 접두로 서비스 실패 처리 안 함).
- TimeoutStartSec=15min.

## Reads
- (none)

## Writes
- [[store-featured-data]] — featured_data.json / newhigh_20d.json
- `featured_data_kis.json`

## Depends on
- [[src-featured-kis]] — Featured KIS/신고가 (fetch_featured_data_kis.py + enrich)

## Code
- `scripts/featured-kis.timer`
- `scripts/featured-kis.service`
- `launchd/timers/com.antigravity.featured-kis.plist`
