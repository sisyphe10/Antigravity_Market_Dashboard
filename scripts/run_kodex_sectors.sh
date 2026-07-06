#!/bin/bash
# fetch_kodex_sectors.py 실행 + 변경 시 git push.
# pykrx 1.2.x가 KRX 인증 강화 + KRX가 GHA Azure IP 차단으로 VM에서 실행.
# 매일 23:30 KST 1회 timer 실행. stale .git/index.lock guard 포함 (60초 이상 = stale).
set -euo pipefail

REPO=/home/ubuntu/Antigravity_Market_Dashboard
cd "$REPO"

# 중복 실행 방지 (정상 cron에선 일어날 일 없지만 안전장치)
exec 200>/tmp/kodex-sectors.lock
flock -n 200 || { echo "이미 실행 중 — 스킵"; exit 0; }

# stale .git/index.lock 자동 회복 (60초 이상 오래된 lockfile만 제거)
LOCKFILE="$REPO/.git/index.lock"
if [ -f "$LOCKFILE" ]; then
    LOCK_AGE=$(( $(date +%s) - $(stat -c %Y "$LOCKFILE") ))
    if [ "$LOCK_AGE" -gt 60 ]; then
        echo "[recovery] stale .git/index.lock 제거 (age=${LOCK_AGE}s)"
        rm -f "$LOCKFILE"
    else
        echo "[ABORT] .git/index.lock 존재 (age=${LOCK_AGE}s) — 다른 git 작업 진행 중 가능성, 스킵"
        exit 0
    fi
fi

set -a
source .env
set +a

PYTHONIOENCODING=utf-8 python3 execution/fetch_kodex_sectors.py

# 퇴직연금 적립금 (KOSIS 연간) — GHA IP가 KOSIS에 막혀 VM 경로가 확실. 실패해도 계속.
PYTHONIOENCODING=utf-8 python3 execution/fetch_pension_kosis.py || true

git add kodex_sectors.json dataset.csv
if git diff --staged --quiet; then
    echo "kodex_sectors.json 변경 없음 — push 스킵"
    exit 0
fi

git commit -m "KODEX 섹터 갱신 ($(TZ=Asia/Seoul date +%F))"
git pull --no-rebase --no-edit || true
git push
echo "✓ kodex_sectors.json push 완료"
