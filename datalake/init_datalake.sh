#!/bin/bash
# datalake 초기화 (맥미니, 1회). 트리 생성 + 의존성 설치 + CLAUDE.md 배치.
# 사용: bash datalake/init_datalake.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT="${DATALAKE_ROOT:-$HOME/datalake}"
PY="$REPO/venv/bin/python3"

echo "① 디렉토리 트리 생성: $ROOT"
mkdir -p "$ROOT"/{research_notes/media,market,snapshots,catalog}

echo "② venv 의존성 설치 (duckdb·pyarrow·yfinance·fastapi·uvicorn)"
"$REPO/venv/bin/pip" install --quiet duckdb pyarrow yfinance fastapi uvicorn pydantic

echo "③ CLAUDE.md 배치 (기존 파일 있으면 보존)"
if [ -f "$ROOT/CLAUDE.md" ]; then
  echo "   $ROOT/CLAUDE.md 이미 존재 — 건너뜀 (갱신하려면 삭제 후 재실행)"
else
  cp "$SCRIPT_DIR/templates/CLAUDE.md" "$ROOT/CLAUDE.md"
fi

echo "④ 임포트 스모크 테스트"
"$PY" - <<'EOF'
import duckdb, pyarrow, yfinance, fastapi, pandas
print("   duckdb", duckdb.__version__, "/ pyarrow", pyarrow.__version__,
      "/ pandas", pandas.__version__)
EOF

echo "완료. 다음 단계: DESIGN.md §8 실행 순서 참조"
