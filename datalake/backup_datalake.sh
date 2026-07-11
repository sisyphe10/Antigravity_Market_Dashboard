#!/bin/bash
# datalake 주간 백업 — private repo sisyphe10/sisyphe-datalake push (일요일 10:00 launchd).
# 제외: market.duckdb(재생성물), _staging/, *.tmp
# 사용: bash datalake/backup_datalake.sh [--init]   # --init = 최초 repo 초기화+원격 연결
set -euo pipefail

ROOT="${DATALAKE_ROOT:-$HOME/datalake}"
REMOTE="https://github.com/sisyphe10/sisyphe-datalake.git"
cd "$ROOT"

if [ "${1:-}" = "--init" ] || [ ! -d .git ]; then
  git init -b main 2>/dev/null || git init
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "$REMOTE"
  cat > .gitignore <<'EOF'
market/market.duckdb
market/*/_staging/
*.tmp
.DS_Store
backfill.log
EOF
  echo "백업 repo 초기화 완료"
fi

git add -A
if git diff --cached --quiet; then
  echo "변경 없음 — push 생략"
  exit 0
fi
git commit -m "backup: $(date '+%Y-%m-%d %H:%M')" --quiet
git push -u origin main --quiet

SIZE="$(du -sh "$ROOT" 2>/dev/null | cut -f1)"
echo "백업 완료: $(date '+%F %T') / datalake 총 크기 $SIZE"
