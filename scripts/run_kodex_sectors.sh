#!/bin/bash
# fetch_kodex_sectors.py 실행 + 변경 시 git push.
# pykrx 1.2.x가 KRX 인증 강화 + KRX가 GHA Azure IP 차단으로 VM에서 실행.
set -euo pipefail

REPO=/home/ubuntu/Antigravity_Market_Dashboard
cd "$REPO"

set -a
source .env
set +a

PYTHONIOENCODING=utf-8 python3 execution/fetch_kodex_sectors.py

git add kodex_sectors.json
if git diff --staged --quiet; then
    echo "kodex_sectors.json 변경 없음 — push 스킵"
    exit 0
fi

git commit -m "KODEX 섹터 갱신 ($(TZ=Asia/Seoul date +%F))"
git pull --no-rebase --no-edit || true
git push
echo "✓ kodex_sectors.json push 완료"
