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
#   --prefer-remote-pending: on merge, if origin advanced orders/pending_orders.json
#       or orders/aum_pending.json since merge-base, keep the REMOTE version —
#       a user save racing this job is authoritative (2026-08-12 finalize 유실 사고).
#       Our finalizedAt-stamped copy is dropped, so the Order tab shows (임시 저장됨)
#       and the user naturally re-finalizes.
#
set -uo pipefail

BRANCH="${GITHUB_REF_NAME:-main}"
XLSX="Wrap_NAV.xlsx"
PORTFOLIO_JSON="portfolio_data.json"

# 커밋 드랍을 호출부에 알리는 마커 (2026-07-27). SAFE_PUSH_DROP_MARKER 가 설정된 경우에만 기록하므로
# GHA 러너(미설정)에선 무동작. 맥미니 run_gha_job.sh 는 이 마커를 보고 stamp/heartbeat 를 억제한다.
# 취지: '잡 성공'을 보는 이유는 결국 데이터가 남았는지이므로, 드랍이면 성공으로 기록하면 안 된다.
mark_drop() {
  [ -n "${SAFE_PUSH_DROP_MARKER:-}" ] || return 0
  echo "$(date "+%Y-%m-%d %H:%M:%S") $1" >> "$SAFE_PUSH_DROP_MARKER" 2>/dev/null || true
}

# 머지 직전에 임시 보관한 '형제 잡의 미커밋 산출물' 상태 (★2026-07-27, 아래 dirty worktree guard 참조)
DIRTY_BAK=""
DIRTY_FILES=()

# 보관본을 워킹트리에 원위치시킨다. 인덱스/HEAD 는 머지 결과 그대로 두고 워킹트리만
# 진입 시점으로 되돌리는 것이 목적 — 형제 잡이 자기 차례에 add/commit 하므로 여기서 커밋하지 않는다.
restore_dirty() {
  [[ -n "$DIRTY_BAK" ]] || return 0
  if [[ ${#DIRTY_FILES[@]} -gt 0 ]]; then
    for _df in "${DIRTY_FILES[@]}"; do
      [[ -f "$DIRTY_BAK/$_df" ]] && cp -p "$DIRTY_BAK/$_df" "$_df" 2>/dev/null
    done
  fi
  rm -rf "$DIRTY_BAK"
  DIRTY_BAK=""
  DIRTY_FILES=()
  return 0
}

XLSX_CONFLICT="bail"
PREFER_REMOTE_PORTFOLIO=0
PREFER_REMOTE_PENDING=0
MSG=""
FILES=()
PUSH_HEAD=0   # --push-head: push an already-made HEAD commit (VM 호출처가 add+commit 직접 수행)

while [[ $# -gt 0 ]]; do
  case "$1" in
    -m)                        MSG="$2"; shift 2 ;;
    --xlsx-conflict)           XLSX_CONFLICT="$2"; shift 2 ;;
    --prefer-remote-portfolio) PREFER_REMOTE_PORTFOLIO=1; shift ;;
    --prefer-remote-pending)   PREFER_REMOTE_PENDING=1; shift ;;
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
  echo "safe_push: usage: -m <msg> [--xlsx-conflict bail|fail] [--prefer-remote-portfolio] [--prefer-remote-pending] -- <files...>" >&2
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
    # ★2026-07-27 fix: 우리 커밋이 xlsx를 건드리지 않았으면 충돌이 아니다(머지가 origin것을 그대로 가져감).
    # 기존엔 origin이 xlsx를 앞서기만 하면 dataset.csv만 담긴 수집 커밋까지 드랭돼 ECOS/KOFIA 수집분이 유실됐다.
    if [[ -z "$MERGED_XLSX" ]] && ! git diff --quiet "$base" "HEAD" -- "$XLSX"; then
      if [[ "$XLSX_CONFLICT" == "fail" ]]; then
        echo "::error::safe_push: origin advanced ${XLSX} under us — refusing to clobber (NEW/AUM edits at risk). Re-run this workflow."
        mark_drop "xlsx-guard(fail): 우리 커밋 드랍 — ${MSG:-<no msg>}"
        git reset --hard "origin/${BRANCH}"
        exit 1
      else
        echo "::warning::safe_push: origin advanced ${XLSX} under us — dropping our commit (will re-trigger on next xlsx push)."
        mark_drop "xlsx-guard(bail): 우리 커밋 드랍 — ${MSG:-<no msg>}"
        git reset --hard "origin/${BRANCH}"
        exit 0
      fi
    fi
  fi

  # ---- dirty worktree guard (★2026-07-27 fix) ----------------------------
  # git merge 는 "머지가 덮어쓸 추적파일"에 미커밋 변경이 있으면 시작조차 못 하고 abort 한다
  # (error: Your local changes ... would be overwritten by merge → Merge with strategy ort failed).
  # 그러면 아래 ours/theirs 해소 루프는 충돌이 0건이라 공회전하고, 재시도 5회가 전부 거부돼
  # 우리 커밋이 고아로 남는다 → 다음 잡의 `git reset --hard origin/main` 이 조용히 폐기.
  # (7/27 실피해: 17:40 ECOS 커밋이 폐기돼 당일 금리 7종 유실)
  # 더티의 정체는 형제 잡이 재생성만 하고 아직 커밋하지 않은 산출물(portfolio_data.json·
  # *.html·disclosures.json 등)이라 버려서도 안 된다 → 워킹트리 사본을 임시 보관하고 HEAD 로
  # 되돌려 머지를 가능하게 한 뒤, 머지 커밋 후 restore_dirty 로 원위치시킨다.
  # ※형제 잡이 보관~원위치 사이에 같은 파일을 다시 쓰면 그 회차 재생성분은 덮인다(다음 재생성으로 자가치유).
  DIRTY_BAK=""
  DIRTY_FILES=()
  while IFS= read -r _df; do
    [[ -z "$_df" ]] && continue
    [[ -z "$DIRTY_BAK" ]] && DIRTY_BAK="$(mktemp -d)"
    mkdir -p "$DIRTY_BAK/$(dirname "$_df")" 2>/dev/null || true
    cp -p "$_df" "$DIRTY_BAK/$_df" 2>/dev/null || true
    DIRTY_FILES+=("$_df")
    git checkout HEAD -- "$_df" 2>/dev/null || true
  done < <(git diff --name-only HEAD)
  if [[ ${#DIRTY_FILES[@]} -gt 0 ]]; then
    echo "safe_push: 미커밋 산출물 ${#DIRTY_FILES[@]}건 임시 보관 후 머지 (${DIRTY_FILES[*]})"
  fi

  # ---- whole-file merge -------------------------------------------------
  # Regenerated artifacts must never be line-spliced (auto-merging two
  # independently regenerated JSON/HTML files can corrupt them), so for the
  # files OUR commit changed we force whole-file selection per policy.
  if ! git merge --no-ff --no-commit "origin/${BRANCH}"; then
    # ★2026-07-27 fix: '충돌로 멈춤'과 '머지 미개시'는 다르다. MERGE_HEAD 가 없으면 후자이고,
    # 이때 해소 루프는 할 일이 없어 재시도가 무의미하다 → `|| true` 로 삼키지 말고 즉시 실패시킨다.
    # (드랍 마커를 남기므로 run_gha_job.sh 가 heartbeat/stamp 를 억제 → 신선도 점검에 잡힌다)
    if [[ ! -e "$(git rev-parse --git-dir)/MERGE_HEAD" ]]; then
      echo "::error::safe_push: merge did not start (attempt ${attempt}) — 정리되지 않은 워킹트리 변경이 남아 있습니다."
      git status --short | head -20
      mark_drop "merge-not-started: 우리 커밋 미push — ${MSG:-<no msg>}"
      restore_dirty
      exit 1
    fi
  fi

  for f in "${OUR_CHANGED[@]}"; do
    _pending_hit=0
    if [[ "$PREFER_REMOTE_PENDING" == "1" ]]; then
      case "$f" in
        orders/pending_orders.json|orders/aum_pending.json) _pending_hit=1 ;;
      esac
    fi
    if [[ "$f" == "$PORTFOLIO_JSON" && "$PREFER_REMOTE_PORTFOLIO" == "1" ]] \
       && ! git diff --quiet "$base" "origin/${BRANCH}" -- "$f"; then
      # VM also changed portfolio_data.json -> its live prices win.
      git checkout "origin/${BRANCH}" -- "$f" 2>/dev/null || true
    elif [[ "$_pending_hit" == "1" ]] \
       && ! git diff --quiet "$base" "origin/${BRANCH}" -- "$f"; then
      # 사용자 저장이 이 잡과 레이스 → 사용자(원격) 쪽이 정본. finalizedAt 스탬프는
      # 함께 버려지므로 Order 탭 배지가 (임시 저장됨)으로 남아 재확정 필요가 드러난다.
      echo "safe_push: ${f} — origin(user save) advanced during job; keeping REMOTE (재확정 필요)."
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

  # 임시 보관한 형제 잡의 미커밋 산출물을 워킹트리에 원위치 (다음 회차 push 전).
  restore_dirty
done

echo "::error::safe_push: exhausted push retries."
exit 1
