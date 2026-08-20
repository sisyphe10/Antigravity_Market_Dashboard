#!/bin/bash
# 태깅 백로그 새벽 분할 회수 (2026-08-20 임시) — 완주 시 재투영 체인 후 crontab 자가 제거.
# cron: 20 3 * * * (02:30 어닝봇 night_llm 쿼터 경합 회피). marker=tagdocs-backlog-260820
set -uo pipefail
REPO="$HOME/Antigravity_Market_Dashboard"
PY="$REPO/venv/bin/python3"
TAG="$REPO/datalake/tagging/tag_docs.py"
LOG="$HOME/tmp/tagdocs_backlog_night.log"
LOCK="$HOME/tmp/tagdocs_backlog_night.lock"
MARKER="tagdocs-backlog-260820"

if ! /usr/bin/shlock -f "$LOCK" -p $$; then
  echo "$(date '+%F %T') 이미 실행 중 — 종료" >> "$LOG"
  exit 0
fi
trap 'rm -f "$LOCK"' EXIT

{
echo "===== $(date '+%F %T') 백로그 야간 회수 시작 ====="
TAG_ENGINE=headless DOC_TAG_HEADLESS_MAX_TODO=1400 DOC_TAG_HEADLESS_MAX_CALLS=180 \
  "$PY" "$TAG" --max-items 1400
rc=$?
echo "tag_docs rc=$rc ($(date '+%F %T'))"
if [ "$rc" -eq 75 ] || [ "$rc" -eq 78 ]; then
  echo "엔진 장애/정책 차단 — cron 유지, 익야 멱등 재시도"
  exit 0
fi
remain=$("$PY" "$TAG" --dry-run 2>/dev/null | grep -o '청크 대상 [0-9]*개' | grep -o '[0-9]*' | head -1)
echo "잔여 청크: ${remain:-판정불가}"
if [ -z "${remain:-}" ] || [ "$remain" -ne 0 ]; then
  echo "미완 — cron 유지"
  exit 0
fi
echo "백로그 완주 — 재투영·인덱스 체인 시작"
"$PY" "$REPO/datalake/export_research_notes.py" --from 2026-08-16 --to "$(date +%F)" \
  || { echo "재투영 실패 — cron 유지"; exit 1; }
"$PY" "$REPO/datalake/tagging/build_tag_index.py" || { echo "인덱스 실패 — cron 유지"; exit 1; }
"$PY" "$REPO/datalake/tagging/export_tags_parquet.py" || { echo "parquet 실패 — cron 유지"; exit 1; }
"$PY" "$REPO/datalake/tagging/build_theme_trends.py" || { echo "추이 실패 — cron 유지"; exit 1; }
crontab -l | grep -v "$MARKER" | crontab -
if crontab -l | grep -q "$MARKER"; then
  echo "★crontab 자가 제거 실패 — 수동 제거 필요"
  exit 1
fi
echo "완료 — crontab 자가 제거됨 ($(date '+%F %T'))"
} >> "$LOG" 2>&1
