#!/bin/bash
# publish_pages.sh — GitHub Pages 게시기 (gh-pages 브랜치 단일 writer)
#
# 설계: ~/work/analysis/260712_git_bloat/DECISION.md (D-수정안, codex rescue 반영)
#   - main 은 소스·데이터만, 생성 대시보드(HTML 등)는 gh-pages 브랜치로만 게시
#   - 평시 일반 push, 커밋 수 임계(3000) 초과 시에만 orphan squash 재생성(--force-with-lease)
#   - 이 스크립트가 gh-pages 의 유일한 writer. 호출: safe_commit_push 성공 훅 / git_pull 원격변경 훅
#   - 게시 내용 = publish_snapshot.sh 와 동일 화이트리스트, 단 개인용 가공(1.5단계) 없이 repo 원본
# 실패해도 잡 rc 에 영향 없도록 호출측은 백그라운드/|| true 로 부른다.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
PUB="${PAGES_PUB_ROOT:-$HOME/srv/pages_publisher}"
WT="$PUB/repo"
LOCK="$PUB/.lock"
BRANCH="gh-pages"
SQUASH_AT="${PAGES_SQUASH_AT:-3000}"

log(){ echo "[pages $(date '+%F %T')] $*"; }

# 맥 전용 (GHA 러너 등에서는 조용히 스킵)
[ "$(uname)" = "Darwin" ] || exit 0

REMOTE_URL="$(git -C "$REPO" remote get-url origin)" || exit 1
mkdir -p "$PUB" || exit 1

# mkdir 원자 락 (최대 120s — 게시 직렬화)
waited=0
until mkdir "$LOCK" 2>/dev/null; do
  waited=$((waited+2))
  if [ "$waited" -ge 120 ]; then log "락 타임아웃 - 이번 게시 스킵"; exit 75; fi
  sleep 2
done
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# 0) 게시 전용 clone 준비 (gh-pages 단일 브랜치, 운영 checkout 과 완전 분리)
if [ ! -d "$WT/.git" ]; then
  if ! git clone -q --single-branch --branch "$BRANCH" "$REMOTE_URL" "$WT" 2>/dev/null; then
    log "원격에 $BRANCH 없음 — orphan 최초 생성"
    rm -rf "$WT"
    git init -q "$WT" || exit 1
    git -C "$WT" remote add origin "$REMOTE_URL"
    git -C "$WT" checkout -q --orphan "$BRANCH"
  fi
  git -C "$WT" config credential.helper store
  git -C "$WT" config user.name "macmini-publisher"
  git -C "$WT" config user.email "kts77775@gmail.com"
fi

cd "$WT" || exit 1
CUR="$(git symbolic-ref --short HEAD 2>/dev/null)"
if [ "$CUR" != "$BRANCH" ]; then log "브랜치 이상($CUR) - 중단"; exit 1; fi

# 1) 화이트리스트 rsync (publish_snapshot.sh 와 동일 규칙 + 원본 무가공)
if ! rsync -a --delete \
  --exclude='/.*' \
  --include='/*.html' --include='/*.json' --include='/*.csv' \
  --include='/orders/' --include='/orders/*.json' \
  --include='/architecture/' --include='/architecture/**' \
  --include='/charts/' --include='/charts/**' \
  --exclude='*' \
  "$REPO/" "$WT/"; then
  log "rsync 실패 - 중단"; exit 1
fi
touch .nojekyll

# 2) 변경 있을 때만 commit + 일반 push
git add -A
if git diff --cached --quiet; then
  log "변경 없음 - 게시 스킵"
else
  git commit -q -m "publish: $(date '+%F %T')" || { log "commit 실패"; exit 1; }
  ok=0
  for i in 1 2 3; do
    # 주의: `if git push | grep` 은 grep 의 종료코드를 보게 되어 성공을 거부로 오판한다 —
    # 반드시 push 자체의 rc 로 판정 (키체인 -25308 경고는 stderr 무해 출력)
    pushout="$(git push origin "HEAD:$BRANCH" 2>&1)"; pushrc=$?
    printf '%s\n' "$pushout" | grep -v 'failed to store' || true
    if [ "$pushrc" -eq 0 ]; then ok=1; break; fi
    log "push 거부(attempt $i) - fetch 후 재시도"
    git fetch -q origin "$BRANCH" 2>/dev/null || true
    sleep 3
  done
  if [ "$ok" != 1 ]; then log "push 실패 - 다음 게시에서 재시도됨"; exit 1; fi
  log "게시 완료 $(git rev-parse --short HEAD)"
fi

# 3) 히스토리 squash (커밋 수 임계 초과 시에만 — main 무관, gh-pages 전용)
CNT="$(git rev-list --count HEAD 2>/dev/null || echo 0)"
if [ "$CNT" -gt "$SQUASH_AT" ]; then
  log "커밋 $CNT > $SQUASH_AT — orphan squash 재생성"
  OLD="$(git rev-parse "origin/$BRANCH" 2>/dev/null || git rev-parse HEAD)"
  git checkout -q --orphan squash_tmp
  git add -A
  git commit -q -m "publish: squash $(date '+%F %T')"
  git branch -M "$BRANCH"
  sqout="$(git push --force-with-lease="refs/heads/$BRANCH:$OLD" origin "HEAD:$BRANCH" 2>&1)"; sqrc=$?
  printf '%s\n' "$sqout" | grep -v 'failed to store' || true
  if [ "$sqrc" -eq 0 ]; then
    log "squash 완료 ($CNT -> 1)"
    git fetch -q origin "$BRANCH" 2>/dev/null || true
  else
    log "squash push 실패 — 로컬 재초기화(다음 게시가 재클론)"
    cd "$PUB" && rm -rf "$WT"
  fi
fi
exit 0
