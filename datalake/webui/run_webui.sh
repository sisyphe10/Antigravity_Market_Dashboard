#!/bin/bash
# Datalake 문답 웹 UI 기동 (수동). 테일넷 공개: tailscale serve --bg 8787
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
PY="$REPO/venv/bin/python3"
[ -x "$PY" ] || PY="python3"
echo "Datalake WebUI: http://127.0.0.1:${DATALAKE_WEBUI_PORT:-8787}"
exec "$PY" "$SCRIPT_DIR/server.py"
