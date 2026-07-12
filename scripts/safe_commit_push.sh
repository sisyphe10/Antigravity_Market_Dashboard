#!/usr/bin/env bash
#
# safe_commit_push.sh — race-safe commit + push for the dashboard workflows.
#
# The dashboard repo is pushed to `main` by several actors at once:
#   - 3 GitHub Actions workflows (recalc_wrap_nav, finalize_orders, daily_crawl)
#     that all regenerate Wrap_NAV.xlsx + dashboard HTML/JSON, and
#   - the VM (sisyphe-bot) which pushes portfolio_data.json / *.html every 30 min.
# Because every run rewrites the "Last Updated" timestamp, each run produces a
# diff and tries to push even when nothing material changed, so plain
# `git push` (skip_fetch:true) loses the race with "! [rejected] (fetch first)".
#
# This script makes the push self-healing: on rejection it fetches, merges
# whole-file (never line-splices regenerated artifacts), and retries. The
# GitHub `concurrency:` group on the workflows guarantees no two GHA runs write
# Wrap_NAV.xlsx at once, so the only actor that can advance the binary under us
# is a manual/user xlsx push — which the xlsx guard refuses to clobber.
#
# Project rule (feedback_git_conflict.md / vm-deploy.md): merge, never rebase;
# protect Wrap_NAV.xlsx (binary holding 기준가/수익률/NEW/AUM sheets).
#
# Usage:
#   safe_commit_push.sh -m "<commit message>" \
#       [--xlsx-conflict bail|fail] [--prefer-remote-portfolio] \
#       -- <file> [<file> ...]
#
#   --xlsx-conflict bail  (default): if origin advanced Wrap_NAV.xlsx under us,
#       drop our commit and exit 0. Safe for recalc_wrap_nav (re-triggers on the
#       next xlsx push) and daily_crawl.
#   --xlsx-conflict fail: same detection but exit 1 (red run, manual re-run).
#       Use for finalize_orders, where a dropped commit silently loses NEW/AUM.
#   --prefer-remote-portfolio: on merge, keep the REMOTE portfolio_data.json
#       (VM live prices are authoritative). Default keeps OURS (e.g. finalize,
#       whose regenerated portfolio_data.json reflects freshly finalized orders).
#
set -uo pipefail

BRANCH="${GITHUB_REF_NAME:-main}"
XLSX="Wrap_NAV.xlsx"
PORTFOLIO_JSON="portfolio_data.json"

XLSX_CONFLICT="bail"
PREFER_REMOTE_PORTFOLIO=0
MSG=""
FILES=()
PUSH_HEAD=0   # --push-head: push an already-made HEAD commit (VM 호출처가 add+commit 직접 수행)

while [[ $# -gt 0 ]]; do
  case "$1" in
    -m)                        MSG="$2"; shift 2 ;;
    --xlsx-conflict)           XLSX_CONFLICT="$2"; shift 2 ;;
    --prefer-remote-portfolio) PREFER_REMOTE_PORTFOLIO=1; shift ;;
    --push-head)               PUSH_HEAD=1; shift ;;
    --)                        shift; FILES=("$@"); break ;;
    *) echo "safe_push: unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ "$PUSH_HEAD" == "1" ]]; then
  if [[ -n "$MSG" || ${#FILES[@]} -gt 0 ]]; then
    echo "safe_push: --push-head는 -m/파일 인자를 받지 않습니다 (기존 HEAD 커밋을 push)" >&2; exit 2
  fi
elif [[ -z "$MSG" || ${#FILES[@]} -eq 0 ]]; then
  echo "safe_push: usage: -m <msg> [--xlsx-conflict bail|fail] [--prefer-remote-portfolio] -- <files...>" >&2
  exit 2
fi
if [[ "$XLSX_CONFLICT" != "bail" && "$XLSX_CONFLICT" != "fail" ]]; then
  echo "safe_push: --xlsx-conflict must be 'bail' or 'fail'" >&2; exit 2
fi

if [[ "$PUSH_HEAD" == "1" ]]; then
  # VM 경로: 호출처가 이미 자신의 identity 로 add+commit 완료 → 기존 git user 보존(없을 때만 폴백)
  git config user.name  >/dev/null 2>&1 || git config user.name  "vm-bot"
  git config user.email >/dev/null 2>&1 || git config user.email "vm-bot@local"
else
  git config user.name  "github-actions[bot]"
  git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
fi

if [[ "$PUSH_HEAD" == "1" ]]; then
  # 이미 만들어진 HEAD 커밋을 push (add/commit 생략). OUR_COMMIT = 현재 HEAD.
  OUR_COMMIT="$(git rev-parse HEAD)"
else
  # Stage only the files that actually exist (file lists include optional artifacts).
  ADD=()
  for f in "${FILES[@]}"; do [[ -e "$f" ]] && ADD+=("$f"); done
  if [[ ${#ADD[@]} -gt 0 ]]; then
    git add -- "${ADD[@]}" 2>/dev/null || true
  fi

  if git diff --cached --quiet; then
    echo "safe_push: nothing staged — nothing to commit."
    exit 0
  fi

  git commit -m "$MSG"
  OUR_COMMIT="$(git rev-parse HEAD)"
fi
# Files OUR commit actually changed (relative to its parent). Only these get the
# whole-file ours/theirs policy; files we didn't touch keep the natural merge
# result so a concurrent actor's solo change to them is never reverted.
# bash 3.2 호환 (macOS 기본 bash엔 mapfile 없음)
OUR_CHANGED=()
while IFS= read -r _f; do OUR_CHANGED+=("$_f"); done < <(git diff --name-only "${OUR_COMMIT}^" "${OUR_COMMIT}")

xlsx_tracked() { git ls-files --error-unmatch "$XLSX" >/dev/null 2>&1; }

for attempt in 1 2 3 4 5; do
  if git push origin "HEAD:${BRANCH}"; then
    echo "safe_push: pushed on attempt ${attempt}."
    # gh-pages 게시 트리거 (맥 전용 — GHA 러너는 Linux 가드로 스킵. 백그라운드
    # 실행이라 호출측 타임아웃과 무관, 실패해도 push 결과에 영향 없음)
    if [ "$(uname)" = "Darwin" ] && [ -x "$(pwd)/scripts/publish_pages.sh" ]; then
      mkdir -p "$(pwd)/logs/launchd" 2>/dev/null || true
      ( nohup bash "$(pwd)/scripts/publish_pages.sh" >> "$(pwd)/logs/launchd/publish_pages.log" 2>&1 & ) || true
    fi
    exit 0
  fi

  echo "safe_push: push rejected (attempt ${attempt}); syncing with origin/${BRANCH}..."
  git fetch origin "${BRANCH}"

  # merge-base MUST be recomputed after the fetch (origin advanced).
  base="$(git merge-base HEAD "origin/${BRANCH}")"

  # ---- Wrap_NAV.xlsx guard ----------------------------------------------
  # With the concurrency group in place, no sibling GHA run can write the
  # binary while we run, so a non-empty base..origin xlsx diff means a manual
  # (user) xlsx push landed. Never clobber it: try the 3-way sheet-level
  # merge first (NEW/AUM row semantics, --prefer theirs = the user push is
  # the protected side); only when that declares a domain conflict fall back
  # to the original bail/fail.
  # NOTE: ours is extracted from HEAD, not OUR_COMMIT — on retry iterations
  # HEAD already contains the previous round's merge, and re-merging from the
  # stale OUR_COMMIT would re-read absorbed remote rows as deletions.
  MERGED_XLSX=""
  if xlsx_tracked && ! git diff --quiet "$base" "origin/${BRANCH}" -- "$XLSX"; then
    if ! git diff --quiet "$base" "HEAD" -- "$XLSX"; then
      MERGE_TMPD="$(mktemp -d)"
      if git show "${base}:${XLSX}" > "$MERGE_TMPD/base.xlsx" 2>/dev/null \
         && git show "HEAD:${XLSX}" > "$MERGE_TMPD/ours.xlsx" 2>/dev/null \
         && git show "origin/${BRANCH}:${XLSX}" > "$MERGE_TMPD/theirs.xlsx" 2>/dev/null \
         && python3 scripts/merge_wrap_nav.py "$MERGE_TMPD/base.xlsx" "$MERGE_TMPD/ours.xlsx" \
              "$MERGE_TMPD/theirs.xlsx" -o "$MERGE_TMPD/merged.xlsx" --prefer theirs; then
        MERGED_XLSX="$MERGE_TMPD/merged.xlsx"
        echo "safe_push: ${XLSX} domain-merged sheet-level (local+origin rows both kept)."
      else
        rm -rf "$MERGE_TMPD"
      fi
    fi
    if [[ -z "$MERGED_XLSX" ]]; then
      if [[ "$XLSX_CONFLICT" == "fail" ]]; then
        echo "::error::safe_push: origin advanced ${XLSX} under us — refusing to clobber (NEW/AUM edits at risk). Re-run this workflow."
        git reset --hard "origin/${BRANCH}"
        exit 1
      else
        echo "::warning::safe_push: origin advanced ${XLSX} under us — dropping our commit (will re-trigger on next xlsx push)."
        git reset --hard "origin/${BRANCH}"
        exit 0
      fi
    fi
  fi

  # ---- whole-file merge -------------------------------------------------
  # Regenerated artifacts must never be line-spliced (auto-merging two
  # independently regenerated JSON/HTML files can corrupt them), so for the
  # files OUR commit changed we force whole-file selection per policy.
  git merge --no-ff --no-commit "origin/${BRANCH}" || true

  for f in "${OUR_CHANGED[@]}"; do
    if [[ "$f" == "$PORTFOLIO_JSON" && "$PREFER_REMOTE_PORTFOLIO" == "1" ]] \
       && ! git diff --quiet "$base" "origin/${BRANCH}" -- "$f"; then
      # VM also changed portfolio_data.json -> its live prices win.
      git checkout "origin/${BRANCH}" -- "$f" 2>/dev/null || true
    else
      # Our freshly regenerated version wins. HEAD (not OUR_COMMIT) so retry
      # iterations keep what previous merge rounds already absorbed.
      git checkout HEAD -- "$f" 2>/dev/null || true
    fi
    git add -- "$f" 2>/dev/null || true
  done

  # Any residual conflicts are in files we did NOT change -> take the remote
  # (the other actor is authoritative for files we didn't touch).
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    git checkout "origin/${BRANCH}" -- "$f" 2>/dev/null || true
    git add -- "$f" 2>/dev/null || true
  done < <(git diff --name-only --diff-filter=U)

  # Domain-merged xlsx supersedes the whole-file ours pick from the loop above.
  if [[ -n "$MERGED_XLSX" ]]; then
    cp "$MERGED_XLSX" "$XLSX"
    git add -- "$XLSX"
    rm -rf "$MERGE_TMPD"
  fi

  git commit --no-edit -m "Merge origin/${BRANCH} before push [skip ci]" || true
done

echo "::error::safe_push: exhausted push retries."
exit 1
