---
id: "store-wrap-nav-xlsx"
name: "Wrap_NAV.xlsx (랩 운용 원장)"
domain: "portfolio-wrap"
project: "antigravity"
type: "store"
runs_on: "github"
schedule_kst: "사용자 편집 + finalize"
status: "active"
code: []
reads: []
writes: []
depends_on: []
alerts: ""
---

# Wrap_NAV.xlsx (랩 운용 원장)

**Domain:** 포트폴리오 · WRAP · **Type:** Store · **Runs on:** github · **Schedule (KST):** 사용자 편집 + finalize · **Status:** active · **Project:** antigravity

랩 상품 운용의 원장 엑셀. NEW(종목·비중)/AUM/기준가/수익률 시트로 구성. 사용자가 직접 편집하는 유일한 바이너리 데이터.

- NEW/AUM은 사람(또는 finalize 잡)이 채우고, 기준가/수익률은 calculate_wrap_nav/returns가 자동 생성.
- 워처가 저장을 감지→3-way merge→push, recalc_wrap_nav 워크플로가 라이브 반영.
- 바이너리라 push 충돌 위험 → safe_commit_push xlsx 가드 + merge_wrap_nav 3-way 병합.
- Excel에서 열려있으면 쓰기 PermissionError.

## Reads
- (none)

## Writes
- (none)

## Depends on
- (none)

## Code
- (none)
