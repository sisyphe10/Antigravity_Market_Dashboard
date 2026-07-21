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

REPO="${REPO:-$(cd "$(dirname "$0")/.." && pwd)}"  # self-locate (macOS/VM 겸용)
cd "$REPO"

# 래퍼 레벨 중복 실행 방지 (collect_etf_daily.py 자체 lock과 이중 안전장치)
exec 200>/tmp/etf-collect-wrapper.lock
flock -n 200 || { echo "이미 실행 중 — 스킵"; exit 0; }

# 2026-07-21: 맥미니 공인 IP가 etfcheck WAF에 IP 차단(정적 파일까지 403) → Oracle VM 경유 SSH SOCKS5
# 프록시로 etfcheck 요청만 우회한다(수집/DB는 그대로 맥미니). 다른 호출은 프록시를 타지 않는다.
ETF_PROXY_PORT="${ETF_PROXY_PORT:-18081}"
VM_HOST="ubuntu@144.24.70.224"
VM_KEY="$HOME/.ssh/oracle_vm.key"
SSH_TUNNEL_PID=""
cleanup() { [ -n "$SSH_TUNNEL_PID" ] && kill "$SSH_TUNNEL_PID" 2>/dev/null; }
trap cleanup EXIT

# 이전 실행이 -9 등으로 죽어 남긴 stale 터널 정리(ExitOnForwardFailure=yes라 포트 점유 시 기동 실패 방지)
pkill -f "ssh -f -N -D 127.0.0.1:${ETF_PROXY_PORT}" 2>/dev/null || true

if [ -f "$VM_KEY" ]; then
  ssh -f -N -D "127.0.0.1:${ETF_PROXY_PORT}" -i "$VM_KEY" \
      -o StrictHostKeyChecking=no -o ExitOnForwardFailure=yes \
      -o ServerAliveInterval=30 -o ConnectTimeout=15 "$VM_HOST"
  if [ $? -eq 0 ]; then
    SSH_TUNNEL_PID="$(pgrep -f "ssh -f -N -D 127.0.0.1:${ETF_PROXY_PORT}" | head -1)"
    export ETFCHECK_PROXY="socks5h://127.0.0.1:${ETF_PROXY_PORT}"
    echo "etfcheck 프록시 활성: ${ETFCHECK_PROXY} (VM 경유, tunnel pid=${SSH_TUNNEL_PID})"
  else
    echo "경고: VM SSH 터널 기동 실패 — 프록시 없이 직결 시도(맥미니 IP 차단 시 403 가능)" >&2
  fi
else
  echo "경고: VM 키($VM_KEY) 없음 — 프록시 없이 직결 시도" >&2
fi

PYTHONIOENCODING=utf-8 python3 execution/etf_collector/collect_etf_daily.py
