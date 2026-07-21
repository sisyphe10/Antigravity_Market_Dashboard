#!/bin/bash
# ETF 구성종목 일별 수집 — VM-side 수집 + 정본 병합 오케스트레이터 (2026-07-21 재설계).
# etf-collect.timer 16:30 / etf-collect-retry.timer 18:00 KST → run_timer_job.sh 경유(1800s 데드라인).
#
# 배경: 2026-07-11 VM→맥미니 이전 후, 맥미니 공인 IP가 한국 금융 소스에 직접 도달 불가.
#   - etfcheck(www.etfcheck.co.kr): WAF IP 차단(정적 파일까지 403).
#   - KRX OpenAPI(data-dbg.krx.co.kr, Akamai): SSH SOCKS 터널로는 MTU 문제로 타임아웃.
#   반면 Oracle VM은 두 소스 모두 직결 200. → 수집은 VM에서 실행하고 "당일분만" 소형 전송 DB로
#   회수해 맥미니 정본(etf_data.db ~635M)에 완결성 검증 후 원자적 병합한다.
#   (구 방식: 맥미니 로컬 수집 + SOCKS 프록시 — etfcheck만 통하고 KRX는 실패해 폐기)
set -uo pipefail

REPO="${REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$REPO"

# 래퍼 레벨 중복 실행 방지
exec 200>/tmp/etf-collect-wrapper.lock
flock -n 200 || { echo "이미 실행 중 — 스킵"; exit 0; }

PY="$REPO/venv/bin/python3"
VM_HOST="ubuntu@144.24.70.224"
VM_KEY="$HOME/.ssh/oracle_vm.key"
VM_REPO="/home/ubuntu/Antigravity_Market_Dashboard"
SSH_OPTS="-i $VM_KEY -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o ServerAliveInterval=30 -o ServerAliveCountMax=6"

if [ ! -f "$VM_KEY" ]; then echo "VM 키 없음: $VM_KEY — 수집 불가" >&2; exit 1; fi

# ── 대상 날짜(전일 최근 거래일) — collect_etf_daily.py 와 동일 로직 ──
TARGET=$("$PY" -c "
from datetime import datetime,timezone,timedelta
import sys
KST=timezone(timedelta(hours=9)); n=datetime.now(KST)
if n.weekday()>=5: sys.exit(9)
d=n.date()-timedelta(days=1)
while d.weekday()>=5: d-=timedelta(days=1)
print(d.strftime('%Y-%m-%d'))")
rc=$?
if [ $rc -eq 9 ]; then echo "주말 — 스킵"; exit 0; fi
[ -z "$TARGET" ] && { echo "대상 날짜 계산 실패" >&2; exit 1; }
echo "대상 날짜: $TARGET"

XFER="/tmp/etf_transfer_${TARGET//-/}.db"
SEED="/tmp/etf_seed_${TARGET//-/}.db"

# ── 1) 수집기 코드를 VM에 동기화(정본 기준 — 새 etfcheck 키·ETF_DB_PATH override 보장) ──
scp $SSH_OPTS \
    execution/etf_collector/etfcheck_client.py \
    execution/etf_collector/etf_db.py \
    execution/etf_collector/collect_etf_daily.py \
    "$VM_HOST:$VM_REPO/execution/etf_collector/" || { echo "VM 코드 동기화 실패" >&2; exit 1; }

# ── 2) 시드: 정본에 이미 해당 날짜 etf_daily가 있으면 전송 DB 초기값으로 심어 KRX 재조회를 건너뛴다.
#      (KRX 간헐 장애 내성 — 목록은 하루 한 번만 KRX 의존, 재시도·복구는 KRX 없이 진행) ──
rm -f "$SEED"
SEED_N=$("$PY" scripts/make_etf_seed.py "$TARGET" "$SEED" 2>/dev/null | awk '/^SEED/{print $2}')
SEED_N="${SEED_N:-0}"
ssh $SSH_OPTS "$VM_HOST" "rm -f '$XFER' '$XFER-wal' '$XFER-shm'" 2>/dev/null || true
if [ "$SEED_N" -gt 0 ] 2>/dev/null; then
    echo "시드: 기존 etf_daily ${SEED_N}종목 → KRX 건너뜀"
    scp $SSH_OPTS "$SEED" "$VM_HOST:$XFER" || { echo "시드 전송 실패" >&2; exit 1; }
else
    echo "시드 없음(신규 날짜) → VM에서 KRX 목록 조회(재시도 내장)"
fi

# ── 3) VM에서 당일 구성종목 수집(전송 DB에 적재) + WAL 체크포인트(단독 파일 보장) ──
ssh $SSH_OPTS "$VM_HOST" "cd $VM_REPO && \
    ETF_DB_PATH='$XFER' PYTHONIOENCODING=utf-8 python3 execution/etf_collector/collect_etf_daily.py $TARGET && \
    python3 -c \"import sqlite3; c=sqlite3.connect('$XFER'); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.close()\"" \
    || { echo "VM 수집 실패" >&2; exit 1; }

# ── 4) 전송 DB 회수 ──
scp $SSH_OPTS "$VM_HOST:$XFER" "$XFER" || { echo "전송 DB 회수 실패" >&2; exit 1; }

# ── 5) 정본 병합(완결성 검증 → 원자적 교체; 미달 시 정본 미변경) ──
"$PY" scripts/import_etf_transfer.py "$XFER" "$TARGET" --min-ok 1000
irc=$?

# ── 6) 정리 — 성공 시에만 로컬 전송 DB 제거(실패 시 보존 → 재수집 없이 재-import 가능).
#      시드·원격 전송 DB는 항상 정리(원격 /tmp 누적 방지). ──
ssh $SSH_OPTS "$VM_HOST" "rm -f '$XFER' '$XFER-wal' '$XFER-shm'" 2>/dev/null || true
rm -f "$SEED" 2>/dev/null || true
if [ $irc -eq 0 ]; then
    rm -f "$XFER" "$XFER-wal" "$XFER-shm" 2>/dev/null || true
    echo "완료: $TARGET"
else
    echo "병합 실패(rc=$irc) — 로컬 전송 DB 보존: $XFER (재-import: scripts/import_etf_transfer.py $XFER $TARGET)" >&2
    exit $irc
fi
