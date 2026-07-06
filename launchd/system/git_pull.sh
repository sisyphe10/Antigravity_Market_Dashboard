#!/bin/bash
# git_pull.sh — 5-minute repo sync (replaces the VM crontab's git-pull cron).
#
# WHY THIS EXISTS
#   On the VM a */5 cron kept the working tree in sync with origin. It is the
#   mac mini's sync lifeline (bots + timers all run off the local checkout).
#
# HARDENED LOGIC (inherited from the VM cron — INVENTORY_LIVE §4)
#   The bots continuously regenerate HTML files, leaving the tree dirty; a plain
#   `git pull` then aborts forever ("would be overwritten by merge"). So we first
#   discard the bot-regenerated HTML, then pull:
#       git checkout -- "*.html" 2>/dev/null ; git pull origin main --quiet
#
# LOGGING / ALERTING
#   Runs every 5 min, so SUCCESS is silent (git-pull.log does not grow). Only
#   FAILURES are recorded. If pulls fail GIT_PULL_FAIL_THRESHOLD times in a row
#   (default 12 = 1 hour), notify_sisyphe_failure.sh is called once, then a
#   cooldown suppresses repeats until it recovers or the cooldown elapses. A
#   success resets the streak (and clears the cooldown).
#
# NOT a calendar job — it has no success stamp and is NOT in schedule.tsv, so the
# catch-up runner never touches it. It is a plain interval daemon. (Pull-only, so
# it has no push-race concern; each job does its own safe_commit_push.)
#
# Token-free: deployed in-place at __REPO__/launchd/system/, self-locates $REPO.
set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SELF_DIR/../.." && pwd)"          # launchd/system -> repo root
LOGDIR="$REPO/logs/launchd"
LOGFILE="$LOGDIR/git-pull.log"
FAILCOUNT="$LOGDIR/git-pull.failcount"
NOTIFIED="$LOGDIR/git-pull.notified"
NOTIFY="$REPO/scripts/notify_sisyphe_failure.sh"

FAIL_THRESHOLD="${GIT_PULL_FAIL_THRESHOLD:-12}"        # consecutive fails -> alert (12 x 5m = 1h)
NOTIFY_COOLDOWN="${GIT_PULL_NOTIFY_COOLDOWN:-3600}"    # re-alert at most this often while broken (s)

logf() { echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $*" >> "$LOGFILE"; }

atomic_write() {                        # CONTRACT: mktemp same dir -> mv -f
  local dest="$1" content="$2" tmp
  tmp="$(mktemp "$(dirname "$dest")/.tmp.XXXXXX")" || return 1
  printf '%s\n' "$content" > "$tmp"
  mv -f "$tmp" "$dest"
}

read_int() {                            # first line as a pure integer, else 0
  local v=""
  [ -f "$1" ] && v="$(head -n1 "$1" 2>/dev/null)"
  v="${v#"${v%%[![:space:]]*}"}"; v="${v%"${v##*[![:space:]]}"}"
  case "$v" in ''|*[!0-9]*) echo 0 ;; *) echo "$v" ;; esac
}

main() {
  mkdir -p "$LOGDIR" 2>/dev/null || true
  if ! cd "$REPO" 2>/dev/null; then
    logf "FAIL cd $REPO failed"
    exit 0
  fi

  # Discard bot-regenerated dirty HTML so the pull can fast-forward.
  git checkout -- "*.html" 2>/dev/null || true

  local out rc
  out="$(git pull origin main --quiet 2>&1)"; rc=$?

  if [ "$rc" -eq 0 ]; then
    # Success is silent. Reset streak state only if we had been failing.
    if [ "$(read_int "$FAILCOUNT")" != 0 ] || [ -f "$NOTIFIED" ]; then
      atomic_write "$FAILCOUNT" 0
      rm -f "$NOTIFIED"
    fi
    exit 0
  fi

  # Failure: record and count.
  local count
  count=$(( $(read_int "$FAILCOUNT") + 1 ))
  atomic_write "$FAILCOUNT" "$count"
  logf "FAIL git pull (rc=$rc, consecutive=$count): $(printf '%s' "$out" | head -n1)"

  # Alert once per cooldown after N consecutive failures.
  if [ "$count" -ge "$FAIL_THRESHOLD" ]; then
    local now last
    now="$(date +%s)"; last="$(read_int "$NOTIFIED")"
    if [ "$last" = 0 ] || [ "$(( now - last ))" -ge "$NOTIFY_COOLDOWN" ]; then
      if [ -x "$NOTIFY" ]; then
        "$NOTIFY" git-pull >/dev/null 2>&1 || logf "WARN notify failed"
      else
        logf "WARN notify script not executable: $NOTIFY"
      fi
      atomic_write "$NOTIFIED" "$now"
      logf "ALERT $count consecutive git-pull failures (>= $FAIL_THRESHOLD) — notified"
    fi
  fi
  exit 0
}

main "$@"
