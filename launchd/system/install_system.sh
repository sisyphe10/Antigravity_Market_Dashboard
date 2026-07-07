#!/bin/bash
# install_system.sh — install the launchd/system daemons on the mac mini:
#   * com.antigravity.catchup         — one-shot boot catch-up runner (Persistent= repl.)
#   * com.antigravity.crash-watcher   — 5-min bot crash-loop watcher (StartLimit+OnFailure repl.)
#   * com.antigravity.git-pull        — 5-min repo sync (VM */5 git-pull cron repl.)
#   * com.antigravity.daily-selfcheck — 08:50 KST daily health digest to Telegram (B9)
#
# DEPLOY LAYOUT (CONTRACT "배포 레이아웃"): the whole launchd/ tree is deployed
# in-place at __REPO__/launchd/. The runner + watcher scripts run FROM there
# (they self-locate $REPO from their own path) — they are NOT copied elsewhere,
# so there is no second copy to drift. This installer therefore does exactly
# two things:
#   1. render the plist tokens (__MACMINI_USER__, __REPO__) and install the two
#      plists into /Library/LaunchDaemons, then bootstrap them.
#   2. create logs/launchd/{stamps,starts} and mark the in-place scripts +x.
# (schedule.tsv is installed by A2b's install_timers.sh, not here.)
#
# Must be run with sudo (writes to /Library/LaunchDaemons, chown root:wheel).
#
# Usage:
#   sudo ./install_system.sh [macmini_user]
#     macmini_user defaults to the invoking (SUDO_USER) account, else $USER.
#
# Idempotent: re-running re-renders and re-bootstraps cleanly.
set -euo pipefail

# --- locate ourselves + repo (this script lives at $REPO/launchd/system/) -----
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SRC_DIR/../.." && pwd)"

# --- resolve + validate target user ------------------------------------------
# Strict username-format check BEFORE any sed substitution (blocks newline / sed
# metachars that would corrupt the rendered plist). Uses case-glob, not grep -Eq:
# grep matches per line, so an embedded newline can slip past ^...$ anchors,
# whereas case matches the whole string. Mirrors install_bots.sh valid_user() (DR3).
valid_user() {
    local u="$1"
    [ -n "$u" ] || return 1
    case "$u" in [a-z_]*) ;; *) return 1 ;; esac                 # first char lowercase/_
    case "$u" in *[!a-z0-9_-]*) return 1 ;; *) return 0 ;; esac  # reject any char outside the set
}
MACMINI_USER="${1:-${SUDO_USER:-$USER}}"
if ! valid_user "$MACMINI_USER"; then
    echo "ERROR: invalid username '$MACMINI_USER' (allowed: lowercase/digits/_/-, first char lowercase/_)." >&2
    echo "       sudo ./install_system.sh <macmini_user>" >&2
    exit 1
fi
if [ "$MACMINI_USER" = "root" ]; then
    echo "ERROR: MACMINI_USER is root. Pass a real user: sudo ./install_system.sh <macmini_user>" >&2
    exit 1
fi

# Source files (all in this dir)
CATCHUP_PLIST_SRC="$SRC_DIR/com.antigravity.catchup.plist"
CATCHUP_RUNNER="$SRC_DIR/catchup_runner.sh"
CRON_HELPER="$SRC_DIR/cron_prev.py"
CRASH_PLIST_SRC="$SRC_DIR/com.antigravity.crash-watcher.plist"
CRASH_WATCHER="$SRC_DIR/crash_watcher.sh"
GITPULL_PLIST_SRC="$SRC_DIR/com.antigravity.git-pull.plist"
GITPULL_SCRIPT="$SRC_DIR/git_pull.sh"
SELFCHECK_PLIST_SRC="$SRC_DIR/com.antigravity.daily-selfcheck.plist"
SELFCHECK_SCRIPT="$SRC_DIR/daily_selfcheck.sh"

for f in "$CATCHUP_PLIST_SRC" "$CATCHUP_RUNNER" "$CRON_HELPER" \
         "$CRASH_PLIST_SRC" "$CRASH_WATCHER" \
         "$GITPULL_PLIST_SRC" "$GITPULL_SCRIPT" \
         "$SELFCHECK_PLIST_SRC" "$SELFCHECK_SCRIPT"; do
    [ -f "$f" ] || { echo "ERROR: missing source file: $f" >&2; exit 1; }
done

LAUNCHD_DIR="/Library/LaunchDaemons"
LOGDIR="$REPO/logs/launchd"
STAMPDIR="$LOGDIR/stamps"
STARTSDIR="$LOGDIR/starts"        # A2a bot wrappers append start epochs here

echo "==> target user : $MACMINI_USER"
echo "==> repo        : $REPO"
echo "==> scripts (in-place) : $SRC_DIR/{catchup_runner.sh,crash_watcher.sh,git_pull.sh,daily_selfcheck.sh,cron_prev.py}"
echo "==> daemons     : $LAUNCHD_DIR/com.antigravity.{catchup,crash-watcher,git-pull,daily-selfcheck}.plist"

# --- runtime dirs (owned by the target user) ---------------------------------
install -d -o "$MACMINI_USER" "$LOGDIR"
install -d -o "$MACMINI_USER" "$STAMPDIR"
install -d -o "$MACMINI_USER" "$STARTSDIR"

# --- scripts run in-place: just make sure they're executable (no copy) --------
chmod 755 "$CATCHUP_RUNNER" "$CRASH_WATCHER" "$GITPULL_SCRIPT" "$SELFCHECK_SCRIPT" "$CRON_HELPER"

# --- preseed stamps BEFORE bootstrapping catchup (item 3) --------------------
# The catchup daemon has RunAtLoad=true, so `launchctl bootstrap` fires it once
# immediately at install time. If it ran with no stamps present it would INIT-
# seed everything anyway, but doing the seed explicitly HERE (as the target user)
# makes it a deliberate, documented step: every job starts "current", the
# install-time fire is a no-op, and the first REAL catch-up is the next boot.
# (Needs schedule.tsv; if A2b's install_timers.sh hasn't run yet this is a
# logged no-op and the first catchup run will seed instead.)
echo "==> preseeding catch-up stamps (baseline = now)"
sudo -u "$MACMINI_USER" /bin/bash "$CATCHUP_RUNNER" --seed || \
    echo "    (preseed skipped/failed — first catchup run will seed; ensure install_timers.sh ran)"

# --- install + (re)bootstrap one daemon --------------------------------------
install_daemon() {
    # install_daemon <label> <plist_src>
    local label="$1" src="$2" dest="$LAUNCHD_DIR/$1.plist"
    sed -e "s|__MACMINI_USER__|$MACMINI_USER|g" \
        -e "s|__REPO__|$REPO|g" \
        "$src" > "$dest"
    chown root:wheel "$dest"
    chmod 644 "$dest"
    launchctl bootout "system/$label" 2>/dev/null || true   # ignore "not loaded"
    launchctl bootstrap system "$dest"
    echo "==> bootstrapped $label"
}

# catchup first (its stamps are now preseeded) then the crash watcher + git-pull.
install_daemon "com.antigravity.catchup"         "$CATCHUP_PLIST_SRC"
install_daemon "com.antigravity.crash-watcher"   "$CRASH_PLIST_SRC"
install_daemon "com.antigravity.git-pull"        "$GITPULL_PLIST_SRC"
install_daemon "com.antigravity.daily-selfcheck" "$SELFCHECK_PLIST_SRC"

echo
echo "Installed. catchup runs once at each boot; crash-watcher + git-pull run every 5 min;"
echo "daily-selfcheck runs at 08:50 KST."
echo
echo "Dry-run catch-up sweep now (no reboot):"
echo "    sudo -u $MACMINI_USER /bin/bash $CATCHUP_RUNNER"
echo "Dry-run crash-watcher now:"
echo "    sudo -u $MACMINI_USER /bin/bash $CRASH_WATCHER"
echo "Dry-run git-pull now:"
echo "    sudo -u $MACMINI_USER /bin/bash $GITPULL_SCRIPT"
echo "Dry-run daily-selfcheck now (sends a Telegram message):"
echo "    sudo -u $MACMINI_USER /bin/bash $SELFCHECK_SCRIPT"
echo "Force an immediate launchd-triggered run:"
echo "    sudo launchctl kickstart -k system/com.antigravity.catchup"
echo "    sudo launchctl kickstart -k system/com.antigravity.crash-watcher"
echo "    sudo launchctl kickstart -k system/com.antigravity.git-pull"
echo "    sudo launchctl kickstart -k system/com.antigravity.daily-selfcheck"
echo "Logs: $LOGDIR/{catchup,crash-watcher,git-pull,daily-selfcheck}.{out,err}"
