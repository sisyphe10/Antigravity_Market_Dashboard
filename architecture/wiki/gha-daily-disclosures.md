---
id: "gha-daily-disclosures"
name: "Daily Disclosures DART+KIND (16:30)"
domain: "market-kr"
project: "antigravity"
type: "gha_workflow"
runs_on: "gha"
schedule_kst: "16:30 매일"
status: "active"
code:
  - ".github/workflows/daily_disclosures.yml"
reads: []
writes:
  - "disclosures.json"
  - "corp_codes.json"
depends_on:
  - "src-dart-disclosures"
  - "src-kind-disclosures"
alerts: "실패 자체 알림 없음 → gha-daily-health-check"
---

# Daily Disclosures DART+KIND (16:30)

**Domain:** 국내 시장 · **Type:** GHA · **Runs on:** gha · **Schedule (KST):** 16:30 매일 · **Status:** active · **Project:** antigravity

보유종목 공시를 16:30 KST(07:30 UTC) 장종료 후 수집·누적하는 워크플로. DART(전자공시)+KIND(거래소 공시)를 `disclosures.json`+`corp_codes.json`에 append.

- 봇 알림(RA_Sisyphe 17:00 수집/17:30 발송)과 별개의 GHA 수집 경로 — 타이밍 무관하게 데이터를 축적.
- git-auto-commit-action으로 두 JSON만 push(맥미니 이전 시 safe_commit_push로 통일 예정).
- 교훈: GHA 스케줄 cron이 3~5h 지연될 수 있음.

## Reads
- (none)

## Writes
- `disclosures.json`
- `corp_codes.json`

## Depends on
- [[src-dart-disclosures]] — DART 공시 (fetch_disclosures.py)
- [[src-kind-disclosures]] — KIND 거래소 공시 (fetch_kind_disclosures.py)

## Code
- `.github/workflows/daily_disclosures.yml`

## Alerts
⚠ 실패 자체 알림 없음 → gha-daily-health-check
