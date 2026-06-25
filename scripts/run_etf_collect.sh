#!/bin/bash
# ETF 구성종목 일별 수집 (etf-collect.timer 16:30 / etf-collect-retry.timer 18:00 KST).
# 봇(sisyphe-bot) apscheduler에서 분리 — 배포/봇 재시작이 진행 중인 수집을 죽이지 않도록
# 별도 systemd 서비스(별 cgroup)로 실행한다. (2026-05-13, 2026-06-25 배포-중-수집사망 근본해결)
#
# collect_etf_daily.py:
#   - 전일(최근 거래일) ETF 전체 목록(KRX OpenAPI) + 구성종목/비중(etfcheck) → etf_data.db
#   - 재개형: 이미 'ok'인 ETF는 건너뜀. ok가 >=1000이면 즉시 스킵(재시도 idempotent).
#   - 자체 /tmp/etf_collector.lock(flock) 보유.
# etf_data.db는 VM 전용(untracked) → push 없음. etf.html 재생성·push는 18:30 Featured 2차 잡 담당.
set -uo pipefail

REPO=/home/ubuntu/Antigravity_Market_Dashboard
cd "$REPO"

# 래퍼 레벨 중복 실행 방지 (collect_etf_daily.py 자체 lock과 이중 안전장치)
exec 200>/tmp/etf-collect-wrapper.lock
flock -n 200 || { echo "이미 실행 중 — 스킵"; exit 0; }

PYTHONIOENCODING=utf-8 exec python3 execution/etf_collector/collect_etf_daily.py
