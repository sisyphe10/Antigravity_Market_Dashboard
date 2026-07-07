---
id: "gha-dormant-push"
name: "휴면 push-트리거 워크플로 (backfill · merge-ddr5)"
domain: "ops-infra"
project: "antigravity"
type: "gha_workflow"
runs_on: "gha"
schedule_kst: "push 트리거 (사실상 휴면)"
status: "frozen"
code:
  - ".github/workflows/run_backfill.yml"
  - ".github/workflows/run_merge_ddr5.yml"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "infra-github"
alerts: ""
---

# 휴면 push-트리거 워크플로 (backfill · merge-ddr5)

**Domain:** 운영 · 인프라 · **Type:** GHA · **Runs on:** gha · **Schedule (KST):** push 트리거 (사실상 휴면) · **Status:** frozen · **Project:** antigravity

특정 파일 push 시에만 도는, 사실상 휴면 상태의 유틸 워크플로 2종.

- `run_backfill.yml`: 자기 자신(yml) push 시 yfinance 히스토리 백필+차트+대시보드 재생성 후 커밋. 초기 셋업용 잔재.
- `run_merge_ddr5.yml`: `merge_ddr5_data.py` push 시 DDR5 데이터 병합. 일회성 병합 도구.
- 둘 다 정기 스케줄 없음, 평소 트리거 안 됨 → status frozen. 삭제보다 보존.

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[infra-github]] — GitHub (정본 repo · Pages · Actions)

## Code
- `.github/workflows/run_backfill.yml`
- `.github/workflows/run_merge_ddr5.yml`
