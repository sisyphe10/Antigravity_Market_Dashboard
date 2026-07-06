#!/bin/bash
# create_landing_highlights.py 실행 + 변경 시 git push.
# 30분 간격 timer로 실행. 16:00~16:59 KST는 cron race 우려로 스킵.
# 충돌/push 실패 시: 보호 파일 백업 → origin/main hard reset → 재생성 → 재push (최대 2회).
set -euo pipefail

REPO="${REPO:-$(cd "$(dirname "$0")/.." && pwd)}"  # self-locate (macOS/VM 겸용)
cd "$REPO"

HOUR=$(TZ=Asia/Seoul date +%H)
if [ "$HOUR" = "16" ]; then
    echo "16:00~16:59 KST 가드 — 스킵"
    exit 0
fi

exec 200>/tmp/landing-highlights.lock
flock -n 200 || { echo "이미 실행 중 — 스킵"; exit 0; }

set -a
source .env
set +a

# 사용자가 로컬에서 staged/working 변경으로 보존 중인 파일 — reset --hard 시 백업 후 복원
PRESERVE_FILES=("Wrap_NAV.xlsx")
PRESERVE_TMP=$(mktemp -d /tmp/lh_preserve.XXXXXX)
trap 'rm -rf "$PRESERVE_TMP"' EXIT

backup_preserved() {
    local f
    for f in "${PRESERVE_FILES[@]}"; do
        if [ -f "$f" ]; then
            cp "$f" "$PRESERVE_TMP/$(basename "$f")"
        fi
    done
}

restore_preserved() {
    local f b
    for f in "${PRESERVE_FILES[@]}"; do
        b="$PRESERVE_TMP/$(basename "$f")"
        if [ -f "$b" ] && ! cmp -s "$f" "$b" 2>/dev/null; then
            cp "$b" "$f"
            echo "  [preserve] $f 사용자 변경분 복원"
        fi
    done
}

build_and_stage() {
    PYTHONIOENCODING=utf-8 python3 execution/create_landing_highlights.py
    git add landing_highlights.json
}

recover_to_origin() {
    echo "[recovery] origin/main으로 hard reset 후 재생성"
    git merge --abort 2>/dev/null || true
    backup_preserved
    git reset --hard origin/main
    restore_preserved
    build_and_stage
}

# === 첫 빌드 ===
build_and_stage
if git diff --staged --quiet; then
    echo "landing_highlights.json 변경 없음 — push 스킵"
    exit 0
fi
git commit -m "landing_highlights 갱신 ($(TZ=Asia/Seoul date '+%F %H:%M KST'))"

# === Push 시도 (최대 2회, 실패 시 origin 우선 복구) ===
attempt=1
while [ $attempt -le 2 ]; do
    git fetch origin main
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse origin/main)
    BASE=$(git merge-base HEAD origin/main 2>/dev/null || echo "")

    if [ "$LOCAL" = "$REMOTE" ]; then
        echo "✓ 이미 origin과 동일 — 종료"
        exit 0
    fi

    if [ "$BASE" = "$REMOTE" ]; then
        # 로컬이 origin보다 앞섬만 — 그냥 push
        if git push; then
            echo "✓ landing_highlights.json push 완료 (attempt $attempt, ff push)"
            exit 0
        fi
    elif git pull --no-rebase --no-edit; then
        # 깨끗하게 merge 성공 — push 시도
        if git push; then
            echo "✓ landing_highlights.json push 완료 (attempt $attempt, merge 후)"
            exit 0
        fi
    fi

    # pull merge 충돌 OR push 거부 — origin 우선 복구
    echo "[recovery] push attempt $attempt 실패 — origin 우선 복구 진행"
    recover_to_origin
    if git diff --staged --quiet; then
        echo "[recovery] 재생성 후 변경 없음 — 종료"
        exit 0
    fi
    git commit -m "landing_highlights 재생성 (충돌 복구, $(TZ=Asia/Seoul date '+%F %H:%M KST'))"
    attempt=$((attempt + 1))
done

echo "[FAIL] push 2회 모두 실패 — OnFailure 알림 트리거"
exit 1
