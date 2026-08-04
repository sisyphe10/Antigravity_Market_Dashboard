#!/bin/bash
# run_boutique_etf.sh — 부티크 액티브 ETF 일일 수집 + 테스트 페이지 재빌드
# (run_timer_job.sh 가 .env 로드·락·타임아웃·stamp 를 담당 — 여기선 실행만)
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/venv/bin/python3"
cd "$REPO"

# ★수집이 부분 실패해도(공휴일 전량 stale, 일부 운용사 장애) 이미 확보된 ETF 의
#   알림·페이지는 나가야 한다. set -e 로 즉시 중단하지 말고 코드만 보관했다가 마지막에 반환.
PYTHONIOENCODING=utf-8 "$PY" -m execution.boutique_etf.collect
RC=$?

# 특이사항(편입/편출/급변) 텔레그램 — 없으면 침묵, 실패해도 잡 성공 판정엔 영향 없음
PYTHONIOENCODING=utf-8 "$PY" -m execution.boutique_etf.alert \
  || echo "[run_boutique_etf] alert 실패(비치명)" >&2

VIEWER_DIR="$HOME/work/charts/260715_현선물공매도"
if [ -f "$VIEWER_DIR/build_viewer_boutique.py" ]; then
  (cd "$VIEWER_DIR" && PYTHONIOENCODING=utf-8 "$PY" build_viewer_boutique.py) \
    || echo "[run_boutique_etf] viewer 빌드 실패(비치명)" >&2
fi

exit $RC
