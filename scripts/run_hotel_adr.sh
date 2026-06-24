#!/bin/bash
# fetch_hotel_adr.py 실행 + 변경 시 git push.
# booking.com Selenium 스크래핑은 비-snap google-chrome 필요(snap chromium은 chromedriver
# 중첩 샌드박스로 'Chrome instance exited' 크래시 — 2026-06 수집 중단 근본원인).
# 매일 12:00 KST 1회 hotel-adr.timer 실행. stale .git/index.lock guard 포함.
set -euo pipefail

REPO=/home/ubuntu/Antigravity_Market_Dashboard
cd "$REPO"

# 중복 실행 방지
exec 200>/tmp/hotel-adr.lock
flock -n 200 || { echo "이미 실행 중 — 스킵"; exit 0; }

# stale .git/index.lock 자동 회복 (60초 이상 오래된 lockfile만 제거)
LOCKFILE="$REPO/.git/index.lock"
if [ -f "$LOCKFILE" ]; then
    LOCK_AGE=$(( $(date +%s) - $(stat -c %Y "$LOCKFILE") ))
    if [ "$LOCK_AGE" -gt 60 ]; then
        echo "[recovery] stale .git/index.lock 제거 (age=${LOCK_AGE}s)"
        rm -f "$LOCKFILE"
    else
        echo "[ABORT] .git/index.lock 존재 (age=${LOCK_AGE}s) — 다른 git 작업 진행 중, 스킵"
        exit 0
    fi
fi

PYTHONIOENCODING=utf-8 python3 execution/fetch_hotel_adr.py

git add hotel_adr.csv
if git diff --staged --quiet; then
    echo "hotel_adr.csv 변경 없음 — push 스킵"
    exit 0
fi

git commit -m "Hotel ADR 갱신 ($(TZ=Asia/Seoul date +%F)) [skip ci]"
git pull --no-rebase --no-edit || true
git push
echo "✓ hotel_adr.csv push 완료"
