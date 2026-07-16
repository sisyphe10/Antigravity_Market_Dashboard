---
id: "ext-sisyphe"
name: "Sisyphe 가계부/운동 대시보드 + 투자일지 시트"
domain: "personal"
project: "antigravity"
type: "external"
runs_on: "external"
schedule_kst: ""
status: "active"
code:
  - "execution/fetch_journal_data.py"
reads: []
writes: []
depends_on: []
alerts: ""
---

# Sisyphe 가계부/운동 대시보드 + 투자일지 시트

**Domain:** 개인 · 가족 · **Type:** External · **Runs on:** external · **Status:** active · **Project:** antigravity

가계부 + 운동기록 대시보드(Ledger/Fitness/Weight 3탭, Google Sheets + data.json 이중). 별도 생태계지만 이 repo와 접점이 여럿이다.

- **투자일지**: `src-journal-data`(fetch_journal_data.py)가 매일 16:10 KST 시장데이터를 Sisyphe의 Google Sheet Data 탭 + `~/Journal/journal_market.json`에 이중기록.
- **가계부**: 카드 SMS→아이폰 단축어→Apps Script→Sheet 파이프라인. Sisyphe-Bot이 답장으로 분류/수정.
- **서빙**: 평문 페이지가 `~/srv/sisyphe_plain` → `compose_personal_view.py` → 스냅숏 `current/sisyphe/`로 합성돼 `/sisyphe/*`로 서빙([[web-publish-snapshot]], 2026-07-13 staticrypt 암호화 폐기).
- **2026-07-16 'Sisyphe 구역' 해체** — 전용 탭·색 테마를 없애고 개인 뷰 전체가 단일 AoE topnav로 통일됐다. 페이지들은 AoE 탭으로 승격: `Journal`(구 Invest)·`Weekly`(딥링크 `#weekly`)·`Memento`·`Ledger`. **`memento.html`은 AoE 기본 화면**(루트 302 대상, [[web-caddy]])이고, 구 진입점 `/sisyphe/index.html`은 Memento 리다이렉트 스텁으로 격하됐다.
- 파생 접점: [[timer-memento-telegram]](12:00 따끔어 텔레그램)·[[daemon-plan-api]](Ledger 'Plan' 탭 백엔드) — 둘 다 스크립트 실체는 `~/Journal` 로컬 전용이라 repo는 배선만 소유.

## Reads
- (none)

## Writes
- (none)

## Depends on
- (none)

## Code
- `execution/fetch_journal_data.py`
