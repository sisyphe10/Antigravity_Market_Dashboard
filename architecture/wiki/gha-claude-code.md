---
id: "gha-claude-code"
name: "Claude Code Action (@claude 이벤트)"
domain: "ops-infra"
project: "antigravity"
type: "gha_workflow"
runs_on: "gha"
schedule_kst: "이벤트 (@claude PR/이슈)"
status: "active"
code:
  - ".github/workflows/claude.yml"
reads: []
writes: []
depends_on:
  - "infra-github"
alerts: ""
---

# Claude Code Action (@claude 이벤트)

**Domain:** 운영 · 인프라 · **Type:** GHA · **Runs on:** gha · **Schedule (KST):** 이벤트 (@claude PR/이슈) · **Status:** active · **Project:** antigravity

PR/이슈/코멘트에서 `@claude`가 언급되면 Claude Code Action이 도는 워크플로. 코드 자동 리뷰/수정 보조.

- 트리거: issue_comment/PR review comment의 `@claude`, 또는 issues opened/assigned, PR opened/synchronize.
- `--append-system-prompt "항상 한글로 답변할 것"`.
- 데이터 파이프라인과 무관한 개발 편의 워크플로.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[infra-github]] — GitHub (정본 repo · Pages · Actions)

## Code
- `.github/workflows/claude.yml`
