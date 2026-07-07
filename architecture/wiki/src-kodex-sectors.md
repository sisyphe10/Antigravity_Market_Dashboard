---
id: "src-kodex-sectors"
name: "KODEX 섹터 비중 (fetch_kodex_sectors.py)"
domain: "tech-semis"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "23:30 (kodex 타이머)"
status: "active"
code:
  - "execution/fetch_kodex_sectors.py"
reads: []
writes:
  - "kodex_sectors.json"
depends_on:
  - "ext-data-apis"
alerts: "OnFailure(kodex-sectors) → 텔레그램"
---

# KODEX 섹터 비중 (fetch_kodex_sectors.py)

**Domain:** 반도체 · 테크 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 23:30 (kodex 타이머) · **Status:** active · **Project:** antigravity

KOSPI200/KOSDAQ150 섹터 비중을 pykrx 로그인으로 수집해 `kodex_sectors.json` 생성.

- 클라우드 IP가 KRX 차단 → VM 전용. loginErrMaxCnt=5 잠금 주의(반복 로그인 금지).
- 실패 알림 문구는 오진 표현, 실제 대개 KRX 인증(CD006=비번불일치 등).

## Reads
- (none)

## Writes
- `kodex_sectors.json`

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_kodex_sectors.py`

## Alerts
⚠ OnFailure(kodex-sectors) → 텔레그램
