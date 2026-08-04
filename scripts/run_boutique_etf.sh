#!/bin/bash
# run_boutique_etf.sh — 부티크 액티브 ETF 일일 수집 + 테스트 페이지 재빌드
# (run_timer_job.sh 가 .env 로드·락·타임아웃·stamp 를 담당 — 여기선 실행만)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/venv/bin/python3"
cd "$REPO"

PYTHONIOENCODING=utf-8 "$PY" -m execution.boutique_etf.collect

# 특이사항(편입/편출/급변) 텔레그램 — 없으면 침묵, 실패해도 잡은 성공 처리
PYTHONIOENCODING=utf-8 "$PY" -m execution.boutique_etf.alert || echo "[run_boutique_etf] alert 실패(비치명)" >&2

VIEWER_DIR="$HOME/work/charts/260715_현선물공매도"
if [ -f "$VIEWER_DIR/build_viewer_boutique.py" ]; then
  (cd "$VIEWER_DIR" && PYTHONIOENCODING=utf-8 "$PY" build_viewer_boutique.py)
fi
