#!/bin/bash
# premarket_portfolio_refresh.sh — 장 시작 전 포트폴리오 구성 재생성 (평일 07:30 KST)
#
# 왜: portfolio_data.json 의 행 목록은 create_portfolio_tables.py 가 "D-1 구성 ∪ 오늘 구성"
#     합집합으로 만든다(전일 편출 종목을 당일 편출 표시용으로 남기는 의도된 동작).
#     그래서 전일 편출 종목은 "다음 날 첫 재생성" 전까지 weight 0 행으로 살아 있는데,
#     정규 갱신(sisyphe_bot auto_portfolio_update_job)의 첫 발화가 09:10 이라
#     그 전 아침 시간대에 WRAP Order 매트릭스·포트 표에 편출 종목이 계속 보였다.
#     이 잡이 개장 전에 한 번 돌려 기준일을 당일로 넘긴다.
#
# 체인: create_portfolio_tables.py → create_dashboard.py → safe_commit_push.sh
#       (safe_commit_push 가 Darwin 에서 publish_pages.sh 를 백그라운드로 띄워 gh-pages 까지 반영)
set -u
set -o pipefail

REPO="$HOME/Antigravity_Market_Dashboard"
PY="$REPO/venv/bin/python3"
LOGDIR="$REPO/logs/launchd"
NOTIFY="$REPO/scripts/notify_sisyphe_failure.sh"
mkdir -p "$LOGDIR"

cd "$REPO" || exit 1

fail() { echo "[premarket] $1" >&2; [ -x "$NOTIFY" ] && "$NOTIFY" portfolio-premarket >/dev/null 2>&1; exit 1; }

git pull --no-rebase -q || echo "[premarket] git pull 경고(계속 진행)" >&2

"$PY" execution/create_portfolio_tables.py || fail "create_portfolio_tables.py 실패"
"$PY" execution/create_dashboard.py        || fail "create_dashboard.py 실패"

bash scripts/safe_commit_push.sh \
  -m "premarket: portfolio tables refresh ($(date '+%Y-%m-%d %H:%M')) [skip ci]" \
  -- portfolio_data.json index.html market.html wrap.html \
  || fail "safe_commit_push 실패"

echo "[premarket] done $(date '+%F %H:%M:%S')"
