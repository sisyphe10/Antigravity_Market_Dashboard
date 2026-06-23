#!/bin/bash
# update_stock_master.py 실행 + 변경 시 안전 push.
# KRX 데이터(pykrx 로그인 + FDR) → Code 시트 신규상장/사명변경 반영.
# 주 1회 (토 09:00 KST) timer 실행. stale .git/index.lock guard 포함.
set -euo pipefail

REPO=/home/ubuntu/Antigravity_Market_Dashboard
cd "$REPO"

# 중복 실행 방지
exec 200>/tmp/update-stock-master.lock
flock -n 200 || { echo "이미 실행 중 — 스킵"; exit 0; }

# stale .git/index.lock 자동 회복 (60초 이상)
LOCKFILE="$REPO/.git/index.lock"
if [ -f "$LOCKFILE" ]; then
    LOCK_AGE=$(( $(date +%s) - $(stat -c %Y "$LOCKFILE") ))
    if [ "$LOCK_AGE" -gt 60 ]; then
        echo "[recovery] stale .git/index.lock 제거 (age=${LOCK_AGE}s)"
        rm -f "$LOCKFILE"
    else
        echo "[ABORT] .git/index.lock 존재 (age=${LOCK_AGE}s) — 다른 git 작업 중 가능, 스킵"
        exit 0
    fi
fi

# origin 최신 동기 (파생 데이터 충돌 회피)
git fetch -q origin || true
git merge -q --ff-only origin/main 2>/dev/null || true

set -a
source .env
set +a

cp Wrap_NAV.xlsx /tmp/Wrap_NAV.premaster.bak.xlsx

PYTHONIOENCODING=utf-8 python3 execution/update_stock_master.py --apply

if git diff --quiet -- Wrap_NAV.xlsx stock_master.json; then
    echo "변경 없음 — push 스킵"
    exit 0
fi

bash scripts/safe_commit_push.sh \
    -m "주간 종목 마스터 갱신 ($(TZ=Asia/Seoul date +%F)) [skip ci]" \
    --xlsx-conflict bail \
    -- Wrap_NAV.xlsx stock_master.json

echo "✓ 종목 마스터 갱신 완료"
