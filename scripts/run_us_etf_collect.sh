#!/bin/bash
# 미국 ETF NAV·AUM 일별 수집 (us-etf-collect.timer, 화~토 09:00 KST).
#   collect_us_etf.py: yfinance 28종 + USDKRW + 삼전·하이닉스 보유비중
#     → us_etf_history.csv append + 한국 비중 변동 텔레그램(Sisyphe-Bot, dedup).
#   이후 etf.html 재생성(main 미추적 — 스냅숏 게시용 로컬 산출물, 게시는 래퍼 담당)
#   + 데이터 CSV race-safe push.
set -uo pipefail

REPO="${REPO:-$(cd "$(dirname "$0")/.." && pwd)}"  # self-locate
cd "$REPO"

# 래퍼 레벨 중복 실행 방지
exec 200>/tmp/us-etf-collect.lock
flock -n 200 || { echo "이미 실행 중 — 스킵"; exit 0; }

PYTHONIOENCODING=utf-8 python3 execution/etf_collector/collect_us_etf.py || exit $?

# etf.html 재생성 — 실패해도 수집은 성공 처리 (다음 정기 재생성이 회복)
PYTHONIOENCODING=utf-8 python3 - <<'PY' || echo "[warn] etf.html 재생성 실패"
import os
import sys
sys.path.insert(0, os.path.join(os.getcwd(), 'execution'))
import create_dashboard
create_dashboard.generate_etf_html()
PY

# 데이터 CSV push (race-safe). 실패해도 수집은 성공 처리 (다음 실행이 재푸시).
bash scripts/safe_commit_push.sh -m "us-etf: NAV·AUM 수집 $(date +%F) [skip ci]" -- us_etf_history.csv \
  || echo "[warn] us_etf_history.csv push 실패"

exit 0
