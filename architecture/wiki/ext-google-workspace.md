---
id: "ext-google-workspace"
name: "Google Workspace (Sheets · Calendar · Drive)"
domain: "ops-infra"
project: "antigravity"
type: "external"
runs_on: "external"
schedule_kst: ""
status: "active"
code: []
reads: []
writes: []
depends_on: []
alerts: ""
---

# Google Workspace (Sheets · Calendar · Drive)

**Domain:** 운영 · 인프라 · **Type:** External · **Runs on:** external · **Status:** active · **Project:** antigravity

서비스계정(GOOGLE_SERVICE_ACCOUNT_KEY)으로 접근하는 구글 서비스 묶음. 여러 잡의 repo 밖 산출처.

- **Sheets**: 투자일지 데이터(`src-journal-data`), 운동봇 기록.
- **Calendar**: 미국 실적 일정(`src-earnings-calendar-sync`)이 여기에 직접 이벤트를 기록(repo push 없음) → 신선도 감시 공백이라 Phase 2 heartbeat가 메움.
- 리서치봇/실적봇 이미지 업로드는 GitHub raw를 쓰고, 여기서는 시트/캘린더가 주.

## Reads
- (none)

## Writes
- (none)

## Depends on
- (none)

## Code
- (none)
