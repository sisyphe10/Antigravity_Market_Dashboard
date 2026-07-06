#!/bin/bash
# crash_watcher.sh — detect KeepAlive-bot crash loops and alert (systemd
# StartLimitBurst + OnFailure equivalent).
#
# WHY THIS EXISTS
#   systemd's StartLimitBurst=10 + OnFailure fires a Telegram alert when a unit
#   crash-loops. launchd has no equivalent, and the KeepAlive bot wrappers exec
#   their target so they can't trap the exit themselves. Instead the A2a wrapper
#   (run_bot.sh) appends each start's epoch to a per-bot log; this watcher reads
#   those logs on a 5-minute cadence and alerts when a bot restarts too often.
#
# INTERFACE (A2a)
#   * Reads start logs:  $REPO/logs/launchd/starts/<botname>.log
#       - one Unix epoch per line, appended at each bot start; A2a keeps only the
#         most recent ~10 lines. The set of *.log files defines the bot set.
#   * On a detected crash loop calls: $REPO/scripts/notify_sisyphe_failure.sh <botname>
#       - seonyuduo-exercise-bot is handled by that script's default case; we
#         just pass the bot name through.
#   * Dedup: after a successful alert, writes a cooldown stamp
#       $REPO/logs/launchd/stamps/crashwatch_<botname>.notified  (epoch)
#     and stays silent for that bot until the cooldown elapses.
#
# Detection rule: >= CRASH_THRESHOLD starts within the last CRASH_WINDOW seconds.
#
# BSD / macOS notes: stock /bin/bash 3.2 (no assoc arrays); mkdir lock (no
# flock); pure integer epoch math (no `date -d`).
#
# DEPLOY LAYOUT (CONTRACT "배포 레이아웃"): deployed in-place as
#   __REPO__/launchd/system/crash_watcher.sh
# and run there directly. Token-free; self-locates $REPO from its own path.
set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SELF_DIR/../.." && pwd)"          # launchd/system -> repo root

LOGDIR="$REPO/logs/launchd"
STARTSDIR="$LOGDIR/starts"
STAMPDIR="$LOGDIR/stamps"
LOCKDIR="$LOGDIR/crashwatch.lock"
NOTIFY="$REPO/scripts/notify_sisyphe_failure.sh"

# Tunables (env-overridable).
CRASH_THRESHOLD="${CRASH_THRESHOLD:-5}"   # restarts within the window => crash loop
CRASH_WINDOW="${CRASH_WINDOW:-600}"       # seconds (10 minutes)
CRASH_COOLDOWN="${CRASH_COOLDOWN:-1800}"  # seconds between alerts per bot (30 min)

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $*"; }

# --- atomic shared-file write (CONTRACT: mktemp same dir -> mv -f) ------------
atomic_write() {
  local dest="$1" content="$2" tmp
  tmp="$(mktemp "$(dirname "$dest")/.tmp.XXXXXX")" || return 1
  printf '%s\n' "$content" > "$tmp"
  mv -f "$tmp" "$dest"
}

# --- single-instance lock (mkdir atomic; flock unavailable on macOS) ----------
# Same design as catchup_runner.sh: (1) ownership-checked release (delete only if
# our pid is recorded — root defense, no cross-deletion), (2) creation-window
# retry, (3) reclaim without restore (leave tombstone + defer on a live race),
# (4) orphan GC of dead tombstones. See that file's header for the rationale.
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
    [ -d "$d" ] || continue
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
  local oldpid="" tries=0
  while [ "$tries" -lt 3 ]; do
    oldpid="$(read_holder_pid)" && break
    tries=$((tries+1)); sleep 0.2
  done
  if [ -n "$oldpid" ] && kill -0 "$oldpid" 2>/dev/null; then
    log "another crash_watcher is running (pid $oldpid) — exiting"
    return 1
  fi
  local stale="$LOCKDIR.stale.$$.$(date +%s)"
  if ! mv "$LOCKDIR" "$stale" 2>/dev/null; then
    log "lock contended during stale reclaim — exiting"
    return 1
  fi
  local grabbed=""
  [ -f "$stale/pid" ] && grabbed="$(head -n1 "$stale/pid" 2>/dev/null | tr -d '[:space:]')"
  case "$grabbed" in ''|*[!0-9]*) grabbed="" ;; esac
  if [ -n "$grabbed" ] && kill -0 "$grabbed" 2>/dev/null; then
    log "stale reclaim aborted — owner pid $grabbed became live; deferring (tombstone kept)"
    return 1
  fi
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

# --- count starts within the window for one log ------------------------------
# (item 1 / CONTRACT interface 0) The starts log holds ONE epoch integer per
# line. Parse strictly: a line that is not purely a plausible epoch integer is
# IGNORED — never force-numerified with tr (a human timestamp like
# "2026-07-06 14:30" would otherwise collapse to a huge number and be counted as
# "recent", causing a permanent false crash-loop alert).
count_recent_starts() {
  local cutoff="$1" logfile="$2" line count=0
  while IFS= read -r line || [ -n "$line" ]; do
    # trim surrounding whitespace
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    # strict: digits only, and a plausible epoch width (9-12 digits)
    case "$line" in
      ''|*[!0-9]*) continue ;;
    esac
    if [ "${#line}" -lt 9 ] || [ "${#line}" -gt 12 ]; then
      continue
    fi
    if [ "$line" -ge "$cutoff" ]; then
      count=$((count+1))
    fi
  done < "$logfile"
  echo "$count"
}

# --- alert with per-bot cooldown ---------------------------------------------
maybe_alert() {
  local name="$1" now="$2" count="$3"
  local notified="$STAMPDIR/crashwatch_$name.notified"

  if [ -f "$notified" ]; then
    # strict read (no tr-numerify): first line must be a pure integer
    local last; last="$(head -n1 "$notified" 2>/dev/null)"
    last="${last#"${last%%[![:space:]]*}"}"
    last="${last%"${last##*[![:space:]]}"}"
    case "$last" in *[!0-9]*) last="" ;; esac
    if [ -n "$last" ] && [ "$(( now - last ))" -lt "$CRASH_COOLDOWN" ]; then
      log "COOLDOWN $name — crash loop ($count starts) but alerted $(( (now - last) / 60 ))m ago (<${CRASH_COOLDOWN}s); silent"
      return 0
    fi
  fi

  log "ALERT $name — crash loop: $count starts within ${CRASH_WINDOW}s (>= $CRASH_THRESHOLD) — notifying"
  if [ -x "$NOTIFY" ]; then
    if "$NOTIFY" "$name" >/dev/null 2>&1; then
      mkdir -p "$STAMPDIR" 2>/dev/null || true
      atomic_write "$notified" "$now"   # start cooldown only on a successful alert
      log "ALERT $name — notified; cooldown until $(( now + CRASH_COOLDOWN ))"
    else
      log "WARN  $name — notify failed (no cooldown set; will retry next cycle)"
    fi
  else
    log "WARN  notify script not executable: $NOTIFY"
  fi
}

# -----------------------------------------------------------------------------
main() {
  log "=== crash_watcher start (threshold=$CRASH_THRESHOLD window=${CRASH_WINDOW}s cooldown=${CRASH_COOLDOWN}s) ==="

  acquire_lock || exit 0

  if [ ! -d "$STARTSDIR" ]; then
    log "no starts dir ($STARTSDIR) yet — no bots to watch"
    exit 0
  fi

  local now; now="$(date +%s)"
  local cutoff=$(( now - CRASH_WINDOW ))
  local watched=0 looping=0 f name count

  for f in "$STARTSDIR"/*.log; do
    [ -f "$f" ] || continue          # no matches -> literal glob -> skip
    name="$(basename "$f" .log)"
    watched=$((watched+1))
    count="$(count_recent_starts "$cutoff" "$f")"
    if [ "$count" -ge "$CRASH_THRESHOLD" ]; then
      looping=$((looping+1))
      maybe_alert "$name" "$now" "$count"
    else
      log "ok    $name — $count start(s) in window"
    fi
  done

  log "=== crash_watcher done: watched=$watched crash-looping=$looping ==="
  exit 0
}

main "$@"
