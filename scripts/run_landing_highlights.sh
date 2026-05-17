#!/bin/bash
# create_landing_highlights.py 실행 + 변경 시 git push.
# 30분 간격 timer로 실행. 16:00~16:59 KST는 cron race 우려로 스킵.
set -euo pipefail

REPO=/home/ubuntu/Antigravity_Market_Dashboard
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

PYTHONIOENCODING=utf-8 python3 execution/create_landing_highlights.py

git add landing_highlights.json
if git diff --staged --quiet; then
    echo "landing_highlights.json 변경 없음 — push 스킵"
    exit 0
fi

git commit -m "landing_highlights 갱신 ($(TZ=Asia/Seoul date '+%F %H:%M KST'))"
git pull --no-rebase --no-edit || true
git push
echo "✓ landing_highlights.json push 완료"
