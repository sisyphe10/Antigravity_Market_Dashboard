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

while [[ $# -gt 0 ]]; do
  case "$1" in
    -m)                        MSG="$2"; shift 2 ;;
    --xlsx-conflict)           XLSX_CONFLICT="$2"; shift 2 ;;
    --prefer-remote-portfolio) PREFER_REMOTE_PORTFOLIO=1; shift ;;
    --)                        shift; FILES=("$@"); break ;;
    *) echo "safe_push: unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$MSG" || ${#FILES[@]} -eq 0 ]]; then
  echo "safe_push: usage: -m <msg> [--xlsx-conflict bail|fail] [--prefer-remote-portfolio] -- <files...>" >&2
  exit 2
fi
if [[ "$XLSX_CONFLICT" != "bail" && "$XLSX_CONFLICT" != "fail" ]]; then
  echo "safe_push: --xlsx-conflict must be 'bail' or 'fail'" >&2; exit 2
fi

git config user.name  "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

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
# Files OUR commit actually changed (relative to its parent). Only these get the
# whole-file ours/theirs policy; files we didn't touch keep the natural merge
# result so a concurrent actor's solo change to them is never reverted.
mapfile -t OUR_CHANGED < <(git diff --name-only "${OUR_COMMIT}^" "${OUR_COMMIT}")

xlsx_tracked() { git ls-files --error-unmatch "$XLSX" >/dev/null 2>&1; }

for attempt in 1 2 3 4 5; do
  if git push origin "HEAD:${BRANCH}"; then
    echo "safe_push: pushed on attempt ${attempt}."
    exit 0
  fi

  echo "safe_push: push rejected (attempt ${attempt}); syncing with origin/${BRANCH}..."
  git fetch origin "${BRANCH}"

  # merge-base MUST be recomputed after the fetch (origin advanced).
  base="$(git merge-base HEAD "origin/${BRANCH}")"

  # ---- Wrap_NAV.xlsx guard ----------------------------------------------
  # With the concurrency group in place, no sibling GHA run can write the
  # binary while we run, so a non-empty base..origin xlsx diff means a manual
  # (user) xlsx push landed. Never clobber it.
  if xlsx_tracked && ! git diff --quiet "$base" "origin/${BRANCH}" -- "$XLSX"; then
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
      # Our freshly regenerated version wins (also keeps OUR Wrap_NAV.xlsx,
      # which the guard proved is the only side that changed the binary).
      git checkout "$OUR_COMMIT" -- "$f" 2>/dev/null || true
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

  git commit --no-edit -m "Merge origin/${BRANCH} before push [skip ci]" || true
done

echo "::error::safe_push: exhausted push retries."
exit 1
