#!/bin/bash
# run_datalake_job.sh — datalake 전용 launchd 타이머 wrapper.
#
# CONTRACT 규약을 자체 구현 (기존 run_timer_job.sh 무수정 원칙):
#   잡별 락(mkdir) · .env 안전 파서(v3) · 타임아웃 워치독 · 성공 stamp · 실패 notify
# catch-up 러너 대상 아님 — 각 잡이 lookback/멱등으로 자가치유 (DESIGN.md §5).
#
# 사용법: run_datalake_job.sh <이름>
#   <이름> ∈ datalake-market-update | datalake-macro-update
#           | datalake-research-export | datalake-snapshot | datalake-backup
set -u

NAME="${1:?usage: run_datalake_job.sh <name>}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
PY="$REPO/venv/bin/python3"
STAMP_DIR="$REPO/logs/launchd/stamps"
LOCK_ROOT="$REPO/logs/launchd/locks"
mkdir -p "$STAMP_DIR" "$LOCK_ROOT"
cd "$REPO" || { echo "[datalake] cd $REPO 실패" >&2; exit 1; }
export PATH="$REPO/venv/bin:$PATH"

# ── 잡 정의: 커맨드·타임아웃(초) ─────────────────────────────
case "$NAME" in
  datalake-market-update)   CMD=("$PY" "$REPO/datalake/daily_market_update.py");  TIMEOUT=7200 ;;
  datalake-macro-update)    CMD=("$PY" "$REPO/datalake/daily_macro_update.py");   TIMEOUT=2700 ;;
  datalake-research-export) CMD=("$PY" "$REPO/datalake/export_research_notes.py"); TIMEOUT=900 ;;
  datalake-snapshot)        CMD=("$PY" "$REPO/datalake/snapshot_archiver.py");     TIMEOUT=600 ;;
  datalake-backup)          CMD=(/bin/bash "$REPO/datalake/backup_datalake.sh");   TIMEOUT=3600 ;;
  datalake-sheets-mirror)   CMD=("$PY" "$REPO/datalake/mirror_sheets.py");          TIMEOUT=600 ;;
  *) echo "[datalake] 알 수 없는 잡: $NAME" >&2; exit 64 ;;
esac

notify() {
  [ -x "$REPO/scripts/notify_sisyphe_failure.sh" ] && \
    /bin/bash "$REPO/scripts/notify_sisyphe_failure.sh" "$NAME" || true
}

# ── 잡별 동시실행 락 ─────────────────────────────────────────
#   pid 파일을 담은 임시 디렉토리를 만들어 mv(rename)로 획득 — mkdir 후
#   pid 기록 사이의 빈 락 창이 없어 stale 오판·탈취가 원천 차단된다.
LOCK="$LOCK_ROOT/$NAME.lock"
acquire_lock() {
  local tmp="$LOCK.acq.$$"
  mkdir "$tmp" 2>/dev/null || return 1
  echo "$$" > "$tmp/pid"
  if mv "$tmp" "$LOCK" 2>/dev/null; then return 0; fi
  rm -rf "$tmp"; return 1
}
if ! acquire_lock; then
  HOLD_PID="$(cat "$LOCK/pid" 2>/dev/null || echo "")"
  if [ -n "$HOLD_PID" ] && kill -0 "$HOLD_PID" 2>/dev/null; then
    echo "[datalake] $NAME 이미 실행 중(pid $HOLD_PID) — skip"; exit 0
  fi
  # stale 회수: rename으로 배타 확보 후 삭제
  STALE="$LOCK.stale.$$"
  if mv "$LOCK" "$STALE" 2>/dev/null; then rm -rf "$STALE"; fi
  acquire_lock || { echo "[datalake] 락 획득 실패 — skip"; exit 0; }
fi
release_lock() { [ "$(cat "$LOCK/pid" 2>/dev/null)" = "$$" ] && rm -rf "$LOCK"; }
trap release_lock EXIT

# ── .env 안전 파서 (CONTRACT v3: set -a source 금지, 양끝 동일 따옴표 한 쌍만 제거) ──
if [ -f "$REPO/.env" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in \#*|"") continue ;; esac
    key="${line%%=*}"; val="${line#*=}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    if [ "${#val}" -ge 2 ]; then
      first="${val:0:1}"; last="${val: -1}"
      if [ "$first" = "$last" ] && { [ "$first" = '"' ] || [ "$first" = "'" ]; }; then
        val="${val:1:${#val}-2}"
      fi
    fi
    export "$key=$val"
  done < "$REPO/.env"
fi

# ── 타임아웃 워치독 하에 실행 ────────────────────────────────
#   TERM 무시/자식(build_catalog 등) 잔존 대비: TERM → 20s 유예 → 자식 포함 KILL
echo "[datalake] $NAME 시작 $(date '+%F %T')"
"${CMD[@]}" &
JOB_PID=$!
(
  sleep "$TIMEOUT"
  kill -0 "$JOB_PID" 2>/dev/null || exit 0
  echo "[datalake] $NAME 타임아웃(${TIMEOUT}s) — TERM" >&2
  pkill -TERM -P "$JOB_PID" 2>/dev/null
  kill -TERM "$JOB_PID" 2>/dev/null
  sleep 20
  pkill -KILL -P "$JOB_PID" 2>/dev/null
  kill -KILL "$JOB_PID" 2>/dev/null
) &
WATCH_PID=$!
wait "$JOB_PID"; RC=$?
kill "$WATCH_PID" 2>/dev/null; wait "$WATCH_PID" 2>/dev/null

if [ "$RC" -eq 0 ]; then
  # 성공 stamp (mktemp+mv 원자적). 기록 실패 = notify + 비정상 종료 (CONTRACT 인터페이스 1)
  TMP="$(mktemp "$STAMP_DIR/.$NAME.XXXXXX")" || { notify; exit 1; }
  date +%s > "$TMP" && mv -f "$TMP" "$STAMP_DIR/$NAME.last" || { rm -f "$TMP"; notify; exit 1; }
  echo "[datalake] $NAME 성공 $(date '+%F %T')"
else
  echo "[datalake] $NAME 실패 rc=$RC" >&2
  notify
fi
exit "$RC"
