#!/bin/bash
# catchup_runner.sh — launchd "missed job" catch-up runner (systemd Persistent=true replacement).
#
# WHY THIS EXISTS
#   systemd timers with Persistent=true re-run a job that was missed while the
#   machine was off. launchd has no equivalent that is reliable across a full
#   power-off. This one-shot LaunchDaemon runs once at boot, inspects each
#   timer job's success stamp against its schedule, and re-runs jobs whose last
#   scheduled fire was missed — sequentially, one at a time.
#
# BSD / macOS NOTES (kept deliberately portable — see README "Compatibility")
#   * Target shell is the stock /bin/bash 3.2 — NO associative arrays, mapfile,
#     ${x,,}, or other bash 4+ features are used.
#   * No flock(1) on macOS -> a mkdir() atomic directory lock is used instead.
#   * BSD ping semantics: `ping -c 1 -t <sec>` where -t is an overall timeout.
#   * BSD date: `date -r <epoch>` formats an epoch (GNU `date -d @epoch` differs).
#
# INTERFACE (migration CONTRACT.md, section "패키지 간 인터페이스")
#   * Reads success stamps:  $REPO/logs/launchd/stamps/<name>.last  (epoch; interface 1 —
#     A4 only READS these; the wrapper writes them).
#   * Reads schedule table:  schedule.tsv  ->  name <TAB> "KST cron (5 fields)" <TAB> command,
#     where <command> invokes A2b's shared wrapper run_timer_job.sh (interface 1-1).
#   * A missed job is re-fired by running its <command> (the wrapper). The wrapper owns the
#     per-job lock (interface 1-1 — the single double-run defense), .env loading, the success
#     stamp (interface 1) and failure notify. This runner therefore does NOT write stamps,
#     load .env, or notify itself — it only decides *what* to re-fire and triggers it.
#   This script NEVER modifies schedule.tsv or the notify script.
#
# DEPLOY LAYOUT (CONTRACT "배포 레이아웃"): this script is deployed in-place as
#   __REPO__/launchd/system/catchup_runner.sh
# and run there directly (no copy to scripts/launchd — avoids double-copy drift).
# It is therefore token-free and self-locates $REPO from its own path.
set -u

# --- derived paths -----------------------------------------------------------
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SELF_DIR/../.." && pwd)"          # launchd/system -> repo root
MACMINI_USER="$(id -un 2>/dev/null || echo "${USER:-unknown}")"
LOGDIR="$REPO/logs/launchd"
STAMPDIR="$LOGDIR/stamps"
LOCKDIR="$LOGDIR/catchup.lock"
CRON_PREV="$SELF_DIR/cron_prev.py"

# venv python (CONTRACT 결정 5); fall back to whatever python3 is on PATH so the
# runner still works before the venv is built.
PYTHON="$REPO/venv/bin/python3"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3 || true)"

# schedule.tsv runtime location is FIXED per the A2b interface confirmation:
# install_timers.sh installs the token-SUBSTITUTED copy (commands have real
# paths, not __REPO__) to $REPO/logs/launchd/schedule.tsv. We read that copy —
# never the unsubstituted original under launchd/timers/. $SCHEDULE_TSV is an
# env escape hatch for testing only.
SCHEDULE_TSV_PATH="${SCHEDULE_TSV:-$LOGDIR/schedule.tsv}"

# Per-job wall-clock timeout for a catch-up run (seconds). Best-effort watchdog.
CATCHUP_JOB_TIMEOUT="${CATCHUP_JOB_TIMEOUT:-3600}"

# Hosts probed for network readiness (IPs -> no DNS dependency).
NET_HOSTS="1.1.1.1 8.8.8.8"
# Max seconds to wait for the network at boot (CONTRACT: up to 3 minutes).
# Overridable so an always-online host (or a test) can shorten/skip the wait;
# set to 0 to skip the probe entirely.
NET_WAIT_MAX="${CATCHUP_NET_WAIT_MAX:-180}"

# -----------------------------------------------------------------------------
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $*"; }

human_time() {
  # epoch -> readable KST string. BSD date (-r). Falls back to raw epoch.
  date -r "$1" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "@$1"
}

# --- atomic shared-file write (CONTRACT: mktemp same dir -> mv -f) ------------
atomic_write() {
  # atomic_write <dest> <content>
  local dest="$1" content="$2" tmp
  tmp="$(mktemp "$(dirname "$dest")/.tmp.XXXXXX")" || return 1
  printf '%s\n' "$content" > "$tmp"
  mv -f "$tmp" "$dest"
}

# --- single-instance lock (mkdir atomic; flock unavailable on macOS) ----------
# Design (no "restore" — restoring a mv'd lock is itself a race):
#   1. Ownership-checked release: the trap deletes the lock ONLY if our pid is
#      still the one recorded in it. This is the root defense — no instance can
#      ever delete a lock another instance legitimately holds.
#   2. Creation window: owner does `mkdir` then writes pid a moment later; a
#      racer retries the pid read (3 x 0.2s) before ever judging the lock stale.
#   3. Stale reclaim: `mv` the apparently-dead lock aside, then re-verify. If a
#      live owner had only-just populated it, do NOT restore — leave the
#      tombstone and defer (that owner runs lock-less, but #1 stops it deleting
#      anyone's lock; real double-run defense is the wrapper's per-job lock — see
#      README "accepted residual"). Dead/empty owner: discard tombstone, mkdir.
#   4. Orphan GC: on acquire, remove sibling `.stale.*` tombstones with a dead pid.
lock_release() {                       # trap handler — delete only if WE own it
  [ "$(cat "$LOCKDIR/pid" 2>/dev/null)" = "$$" ] && rm -rf "$LOCKDIR"
}
read_holder_pid() {                    # echoes a numeric pid, or nothing
  local p=""
  [ -f "$LOCKDIR/pid" ] && p="$(head -n1 "$LOCKDIR/pid" 2>/dev/null)"
  p="${p#"${p%%[![:space:]]*}"}"; p="${p%"${p##*[![:space:]]}"}"
  case "$p" in ''|*[!0-9]*) return 1 ;; esac
  echo "$p"
}
gc_stale_locks() {                     # reclaim tombstones whose owner is dead
  local d p
  for d in "$LOCKDIR".stale.*; do
    [ -d "$d" ] || continue            # no matches -> literal glob -> skip
    p=""
    [ -f "$d/pid" ] && p="$(head -n1 "$d/pid" 2>/dev/null | tr -d '[:space:]')"
    case "$p" in ''|*[!0-9]*) p="" ;; esac
    if [ -z "$p" ] || ! kill -0 "$p" 2>/dev/null; then
      rm -rf "$d"                       # dead/unknown owner -> reclaim (live -> keep)
    fi
  done
}
acquire_lock() {
  mkdir -p "$LOGDIR" 2>/dev/null || true
  if mkdir "$LOCKDIR" 2>/dev/null; then
    echo $$ > "$LOCKDIR/pid"
    trap 'lock_release' EXIT INT TERM
    gc_stale_locks
    return 0
  fi
  # Lock exists. Read the owner pid, retrying to absorb the creation window.
  local oldpid="" tries=0
  while [ "$tries" -lt 3 ]; do
    oldpid="$(read_holder_pid)" && break
    tries=$((tries+1)); sleep 0.2
  done
  if [ -n "$oldpid" ] && kill -0 "$oldpid" 2>/dev/null; then
    log "another catchup instance is running (pid $oldpid) — exiting"
    return 1
  fi
  # No live owner after retries. Move the apparently-stale lock aside atomically.
  local stale="$LOCKDIR.stale.$$.$(date +%s)"
  if ! mv "$LOCKDIR" "$stale" 2>/dev/null; then
    log "lock contended during stale reclaim — exiting"
    return 1
  fi
  # Re-verify the grabbed dir. A live owner that only-just populated it means we
  # raced its creation window: do NOT restore (that is a race) — leave the
  # tombstone (GC'd once it dies) and defer.
  local grabbed=""
  [ -f "$stale/pid" ] && grabbed="$(head -n1 "$stale/pid" 2>/dev/null | tr -d '[:space:]')"
  case "$grabbed" in ''|*[!0-9]*) grabbed="" ;; esac
  if [ -n "$grabbed" ] && kill -0 "$grabbed" 2>/dev/null; then
    log "stale reclaim aborted — owner pid $grabbed became live; deferring (tombstone kept)"
    return 1
  fi
  # Genuinely dead/empty owner: discard tombstone and re-acquire.
  rm -rf "$stale"
  if mkdir "$LOCKDIR" 2>/dev/null; then
    echo $$ > "$LOCKDIR/pid"
    trap 'lock_release' EXIT INT TERM
    gc_stale_locks
    log "reclaimed stale lock (dead owner pid '${oldpid:-none}')"
    return 0
  fi
  log "lock contended after reclaim — exiting"
  return 1
}

# --- wait for network after boot (best-effort, capped) ------------------------
wait_network() {
  local deadline=$(( $(date +%s) + NET_WAIT_MAX )) h
  while [ "$(date +%s)" -lt "$deadline" ]; do
    for h in $NET_HOSTS; do
      if ping -c 1 -t 5 "$h" >/dev/null 2>&1; then
        log "network reachable via $h"
        return 0
      fi
    done
    sleep 5
  done
  log "WARN: network not reachable after ${NET_WAIT_MAX}s — proceeding anyway"
  return 1
}

# --- resolve schedule.tsv path (fixed location) -------------------------------
find_schedule() {
  if [ -f "$SCHEDULE_TSV_PATH" ]; then
    echo "$SCHEDULE_TSV_PATH"
    return 0
  fi
  return 1
}

# --- is a launchd job currently running? (best-effort, root-tolerant) ---------
# Returns 0 = running, 1 = not running / unknown. If launchctl cannot report
# (job not loaded, or permission denied for a non-root caller) we return 1 and
# let the direct-run path handle it.
is_job_running() {
  local label="com.antigravity.$1" out
  out="$(launchctl print "system/$label" 2>/dev/null)" || return 1
  case "$out" in
    *"state = running"*) return 0 ;;
    *) return 1 ;;
  esac
}

# --- re-fire one missed job by triggering the shared wrapper ------------------
# A missed job is re-run by executing its schedule.tsv <command>, which is an
# invocation of A2b's run_timer_job.sh (interface 1-1). That wrapper owns the
# per-job lock (the real double-run defense), .env loading, the success stamp
# (interface 1) and failure notify — so this function must NOT do any of those
# itself. It only validates the command, best-effort-skips a concurrent launchd
# run, and triggers the wrapper.
# Sets JOB_OUTCOME to one of: ran-ok | ran-fail | skipped
run_job() {
  local name="$1" cmd="$2" last="$3" rc=0
  JOB_OUTCOME="skipped"

  # (item 4) Only re-fire commands that go through run_timer_job.sh. A row that
  # bypasses the wrapper would run without the lock/stamp/notify/timeout
  # guarantees, so refuse it rather than run it unguarded.
  case "$cmd" in
    *"/launchd/timers/run_timer_job.sh "*) : ;;   # full path + an argument
    *)
      log "SKIP  $name — command is not '.../launchd/timers/run_timer_job.sh <job>'; refusing: $cmd"
      return 0 ;;
  esac

  # (item 2) Best-effort pre-check only. The authoritative double-run defense is
  # the wrapper's per-job lock (interface 1-1); if launchctl can't report (non-
  # root / not loaded) we still trigger, and the wrapper's lock arbitrates.
  if is_job_running "$name"; then
    log "SKIP  $name — already running under launchd (wrapper lock would arbitrate anyway)"
    return 0
  fi

  log "RUN   $name — missed scheduled $(human_time "$last") KST :: $cmd"

  # Trigger the wrapper. Grandchild-process cleanup on hang is the wrapper's
  # process-group timeout (interface note); this outer watchdog is only a coarse
  # backstop that TERMs the wrapper subshell so one hung job can't block the rest.
  (
    cd "$REPO" 2>/dev/null || { echo "cd $REPO failed" >&2; exit 127; }
    eval "$cmd"
  ) >>"$LOGDIR/$name.catchup.out" 2>>"$LOGDIR/$name.catchup.err" &
  local job_pid=$!
  ( sleep "$CATCHUP_JOB_TIMEOUT" && kill -TERM "$job_pid" 2>/dev/null ) &
  local watch_pid=$!
  wait "$job_pid"; rc=$?
  kill "$watch_pid" 2>/dev/null
  wait "$watch_pid" 2>/dev/null

  # The wrapper already wrote the stamp (on success) or notified (on failure);
  # we only log the outcome for observability.
  if [ "$rc" -eq 0 ]; then
    JOB_OUTCOME="ran-ok"
    log "OK    $name (rc=0) — wrapper handled stamp"
  else
    JOB_OUTCOME="ran-fail"
    log "WARN  $name exited rc=$rc — wrapper owns notify; see $LOGDIR/$name.catchup.err"
  fi
  return "$rc"
}

# --- preseed mode (item 3): seed a baseline stamp for every scheduled job ------
# Run by install_system.sh BEFORE bootstrapping the catchup daemon, so the
# daemon's install-time RunAtLoad fire finds every stamp already current and does
# nothing. This makes "seed now" a deliberate install step (not an implicit side
# effect of RunAtLoad) and guarantees the FIRST real catch-up is the next boot.
seed_only() {
  log "=== catchup preseed (seed missing stamps, run nothing) ==="
  local schedule
  schedule="$(find_schedule)" || {
    log "WARN: schedule.tsv not found at $SCHEDULE_TSV_PATH — nothing to preseed"
    log "      (run install_timers.sh first, or the first catch-up run will seed)"
    return 0
  }
  local now; now="$(date +%s)"
  mkdir -p "$STAMPDIR" 2>/dev/null || true
  local name cron cmd seeded=0 present=0
  while IFS=$'\t' read -r name cron cmd || [ -n "$name" ]; do
    case "$name" in ''|\#*) continue ;; esac
    name="$(echo "$name" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [ -n "$name" ] || continue
    if [ -f "$STAMPDIR/$name.last" ]; then
      present=$((present+1)); continue
    fi
    atomic_write "$STAMPDIR/$name.last" "$now"
    log "SEED  $name -> $now"
    seeded=$((seeded+1))
  done < "$schedule"
  log "=== preseed done: seeded=$seeded already-present=$present (first real catch-up = next boot) ==="
}

# -----------------------------------------------------------------------------
main() {
  if [ "${1:-}" = "--seed" ]; then
    seed_only
    exit 0
  fi

  log "=== catchup runner start (user=$MACMINI_USER repo=$REPO) ==="

  acquire_lock || exit 0

  if [ -z "$PYTHON" ]; then
    log "ERROR: no python3 available (need $REPO/venv/bin/python3) — cannot compute schedules, exiting"
    exit 0
  fi
  if [ ! -f "$CRON_PREV" ]; then
    log "ERROR: cron helper missing: $CRON_PREV — exiting"
    exit 0
  fi

  wait_network || true

  local schedule
  schedule="$(find_schedule)" || {
    log "WARN: schedule.tsv not found at $SCHEDULE_TSV_PATH — nothing to catch up"
    exit 0
  }
  log "using schedule: $schedule"

  local now; now="$(date +%s)"

  # Pass 1: decide. Collect missed jobs into parallel indexed arrays (bash 3.2).
  local m_name=() m_cmd=() m_last=()
  local total=0 missed=0 uptodate=0 initialized=0 skipped=0

  local name cron cmd last stamp_epoch
  while IFS=$'\t' read -r name cron cmd || [ -n "$name" ]; do
    # skip blank lines and comments
    case "$name" in ''|\#*) continue ;; esac
    # trim possible surrounding whitespace on name
    name="$(echo "$name" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [ -n "$name" ] || continue
    if [ -z "${cron:-}" ] || [ -z "${cmd:-}" ]; then
      log "WARN  malformed schedule row for '$name' (missing cron or command) — skipping"
      skipped=$((skipped+1)); continue
    fi
    total=$((total+1))

    last="$("$PYTHON" "$CRON_PREV" "$cron" "$now" 2>/dev/null)"
    if [ -z "$last" ]; then
      log "WARN  $name — could not compute last fire from cron '$cron' — skipping"
      skipped=$((skipped+1)); continue
    fi

    local stampfile="$STAMPDIR/$name.last"
    if [ ! -f "$stampfile" ]; then
      # First-ever boot for this job: no history -> do NOT retro-run. Seed the
      # stamp with "now" so the next boot has a baseline (edge case per README).
      mkdir -p "$STAMPDIR" 2>/dev/null || true
      atomic_write "$stampfile" "$now"
      log "INIT  $name — no stamp yet; seeded stamp=$now (no catch-up on first run)"
      initialized=$((initialized+1)); continue
    fi

    # strict read (no tr-numerify): first line must be a pure integer
    stamp_epoch="$(head -n1 "$stampfile" 2>/dev/null)"
    stamp_epoch="${stamp_epoch#"${stamp_epoch%%[![:space:]]*}"}"
    stamp_epoch="${stamp_epoch%"${stamp_epoch##*[![:space:]]}"}"
    case "$stamp_epoch" in ''|*[!0-9]*) stamp_epoch="" ;; esac
    if [ -z "$stamp_epoch" ]; then
      log "WARN  $name — unreadable stamp; reseeding stamp=$now (no catch-up)"
      atomic_write "$stampfile" "$now"
      skipped=$((skipped+1)); continue
    fi

    if [ "$stamp_epoch" -lt "$last" ]; then
      log "MISS  $name — last success $(human_time "$stamp_epoch") < expected $(human_time "$last") -> catch up"
      m_name[$missed]="$name"; m_cmd[$missed]="$cmd"; m_last[$missed]="$last"
      missed=$((missed+1))
    else
      uptodate=$((uptodate+1))
    fi
  done < "$schedule"

  log "plan: total=$total  missed=$missed  up-to-date=$uptodate  initialized=$initialized  skipped=$skipped"

  # Pass 2: re-fire missed jobs SEQUENTIALLY (safety over speed).
  local i=0 fired=0 failed=0 skipped_run=0
  JOB_OUTCOME=""
  while [ "$i" -lt "$missed" ]; do
    run_job "${m_name[$i]}" "${m_cmd[$i]}" "${m_last[$i]}" || true
    case "$JOB_OUTCOME" in
      ran-ok)   fired=$((fired+1)) ;;
      ran-fail) fired=$((fired+1)); failed=$((failed+1)) ;;
      *)        skipped_run=$((skipped_run+1)) ;;
    esac
    i=$((i+1))
  done

  log "=== catchup runner done: missed=$missed fired=$fired failed=$failed skipped=$skipped_run ==="
  exit 0
}

main "$@"
