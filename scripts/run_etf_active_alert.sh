#!/bin/bash
# 액티브 ETF 구성 변동 텔레그램 알림 (etf-active-alert.timer 19:00 KST).
# etf_data.db(전 액티브 ETF의 전일 대비 신규편입/편출/비중급변) → subscribers.json 브로드캐스트.
# 봇(sisyphe-bot)과 무관한 독립 systemd 서비스(별 cgroup) → 봇 재시작/배포가 알림을 죽이지 않음
# (ETF 수집을 systemd 로 분리한 것과 같은 이유).
# 대시보드 etf.html '액티브 ETF' 탭과 동일한 단일 출처 모듈(active_etf_changes.py)로 계산 → 숫자 일치.
set -uo pipefail

REPO="${REPO:-$(cd "$(dirname "$0")/.." && pwd)}"  # self-locate (macOS/VM 겸용)
cd "$REPO"

# 중복 실행 방지
exec 200>/tmp/etf-active-alert.lock
flock -n 200 || { echo "이미 실행 중 — 스킵"; exit 0; }

PYTHONIOENCODING=utf-8 exec python3 execution/etf_active_alert.py
