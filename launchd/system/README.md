# A4 — launchd system daemons (`launchd/system/`)

Three `LaunchDaemon`s that replace systemd/cron features launchd lacks:

1. **`com.antigravity.catchup`** — replaces `Persistent=true`. Runs once at boot, works out
   which timer jobs missed their last scheduled fire while the mac was off, and re-runs them
   (sequentially).
2. **`com.antigravity.crash-watcher`** — replaces `StartLimitBurst` + `OnFailure`. Polls every
   5 minutes and fires a Telegram alert when a KeepAlive bot is crash-looping.
3. **`com.antigravity.git-pull`** — replaces the VM's `*/5` git-pull cron. Keeps the local checkout
   in sync with origin every 5 minutes (the sync lifeline for bots + timers).

## Files

| File | Role |
|:---|:---|
| `catchup_runner.sh` | Catch-up orchestrator. Reads stamps + `schedule.tsv`, decides what was missed, re-runs it. |
| `cron_prev.py` | Pure-stdlib helper: 5-field cron → epoch of the most recent fire `<= now` in KST. |
| `com.antigravity.catchup.plist` | Catch-up daemon: `RunAtLoad=true`, no `KeepAlive` → once per boot. |
| `crash_watcher.sh` | Crash-loop detector. Reads `starts/<bot>.log`, alerts via the notify script. |
| `com.antigravity.crash-watcher.plist` | Crash-watcher daemon: `StartInterval=300` (+`RunAtLoad`). |
| `git_pull.sh` | Repo sync: `git checkout -- "*.html"` then `git pull origin main --quiet`; alerts on a failure streak. |
| `com.antigravity.git-pull.plist` | Git-pull daemon: `StartInterval=300` (+`RunAtLoad`). |
| `install_system.sh` | Renders `__MACMINI_USER__`/`__REPO__` tokens (sed) and installs all three daemons. `sudo`. |
| `README.md` | This file. |

All scripts target the stock `/bin/bash` 3.2 and use only tools present on a clean macOS.

## Interfaces (`CONTRACT.md` §"패키지 간 인터페이스" + A2a/A2b confirmations)

- **Success stamps (interface 1 — read only):** `__REPO__/logs/launchd/stamps/<name>.last` — epoch of
  the job's last success. **The wrapper writes these; A4 only reads them** (plus a baseline seed for
  a missing stamp). A catch-up re-fire goes through the wrapper, which writes the stamp.
- **Per-job lock (interface 1-1):** `run_timer_job.sh` holds a per-job lock; because both the launchd
  timer and an A4 catch-up re-fire go through that same wrapper, the lock is the single double-run
  defense. A4's `launchctl print` check is only a best-effort courtesy.
- **`schedule.tsv` (read-only, A2b):** `name <TAB> "KST cron (5 fields)" <TAB> command`, where
  `command` invokes `run_timer_job.sh`. **Fixed runtime path:
  `__REPO__/logs/launchd/schedule.tsv`** — `install_timers.sh` installs the token-*substituted* copy
  there (commands carry real paths). A4 reads that copy, never the unsubstituted original under
  `launchd/timers/`. `$SCHEDULE_TSV` overrides for tests. Per-job stamps are independent, so
  `etf-collect` and `etf-collect-retry` (same command, different names) are judged separately.
- **Bot start logs (interface 0 — read):** `__REPO__/logs/launchd/starts/<bot>.log` — **one epoch
  integer per line** (A2a keeps ~10 lines, atomically truncated). The crash watcher parses strictly and
  **ignores any line that is not a plausible epoch integer** (never `tr`-numerifies). The set of
  `*.log` files defines the watched bot set.
- **Failure/alert notify:** the crash watcher (and the wrapper) call
  `__REPO__/scripts/notify_sisyphe_failure.sh <name>` (existing script, never modified).
  `seonyuduo-exercise-bot` is that script's default case — the watcher just passes the name through.
  The catch-up runner does **not** notify (the wrapper owns that).
- **Crash-watcher cooldown stamp (write):** `__REPO__/logs/launchd/stamps/crashwatch_<bot>.notified`.

---

## 1. Catch-up runner

Two passes, so the full "why" is logged before anything runs.

**Pass 1 — decide.** For each row of `schedule.tsv`:

1. `last_expected = cron_prev.py(cron, now)` — most recent scheduled fire `<= now`, in KST.
2. **No stamp file** → *first sight of this job.* Do **not** retro-run; seed the stamp with `now`
   (normally already done by install preseed — see below).
3. Stamp exists and `stamp < last_expected` → the job **missed** its last fire → queue it.
4. Otherwise → up-to-date → skip.

**Pass 2 — re-fire** queued jobs **sequentially** (safety over speed — never fan out). For each:

1. **Command validation (item 4):** the `<command>` must match `.../launchd/timers/run_timer_job.sh
   <job>` (A2b's shared wrapper, invoked with a job argument); a row that bypasses it is logged and
   **skipped** (running it unguarded would lose the lock/stamp/notify/timeout guarantees).
2. **Best-effort pre-check:** `launchctl print system/com.antigravity.<name>`; if `state = running`,
   skip. This is only a courtesy — the authoritative double-run defense is the wrapper's per-job lock.
3. Otherwise `eval <command>` — i.e. trigger `run_timer_job.sh <job>`.

**The wrapper owns everything (interfaces 1 & 1-1).** `run_timer_job.sh` takes the per-job lock (the
single double-run defense), loads `.env` with the safe parser (env v3), writes the success stamp, calls
notify on failure, and enforces the process-group timeout. This runner therefore does **not** load
`.env`, **does not write stamps** (interface 1: A4 only *reads* stamps), and **does not notify** — it
only decides *what* to re-fire and triggers the wrapper. (Its own outer watchdog is just a coarse
backstop so one hung job can't block the rest; grandchild cleanup is the wrapper's job.)

Because execution goes through the wrapper, no root is needed (no `launchctl kickstart` of a
system-domain daemon), and a catch-up re-fire is indistinguishable from a normal scheduled run.

### Decision rule — desk-check (verified against `cron_prev.py`)

Times are KST (fixed UTC+9 — Korea has no DST). Values below were emitted by the script and match by hand.

| Job type | cron (KST) | reference `now` | last expected fire | epoch |
|:---|:---:|:---:|:---:|:---:|
| Daily | `20 16 * * *` | Wed 2026-07-08 09:00 | **Tue 2026-07-07 16:20** (today's 16:20 still future → previous day) | `1783408800` |
| Weekday (Tue–Sat) | `50 7 * * 2-6` | Mon 2026-07-06 10:00 | **Sat 2026-07-04 07:50** (Mon/Sun fail dow 2–6 → back to Sat) | `1783119000` |
| Weekly (Sat only) | `0 9 * * 6` | Mon 2026-07-06 10:00 | **Sat 2026-07-04 09:00** (last Saturday) | `1783123200` |

The confirmed 8-row schedule is 6 daily jobs (15:50/16:30/18:00/18:35/19:00/23:30), daily 08:00
(`earnings-bot`), and weekly `0 9 * * 6` (`update-stock-master`, Sat) — the weekly row is exactly the
third desk-check case above.

### Preseed (`--seed`) and first catch-up (item 3)

The catchup daemon has `RunAtLoad=true`, so `launchctl bootstrap` fires it **once at install time**,
not only at boot. To keep that from silently INIT-seeding everything as a side effect,
`install_system.sh` runs `catchup_runner.sh --seed` **before** bootstrapping: `--seed` writes a
baseline stamp (`now`) for every scheduled job that has no stamp and **runs nothing**. So every job
starts "current", the install-time fire is a no-op, and the **first real catch-up is the next boot**.
(If `schedule.tsv` isn't present yet, `--seed` is a logged no-op and Pass 1 seeds on the first run.)

### Catch-up edge cases

- **Stamp absent (first sight of a job):** don't catch up; seed the stamp with `now` (`INIT`). With no
  history we can't tell a genuinely-missed run from a never-scheduled one; the wrapper overwrites the
  stamp on its next success.
- **Unreadable/non-numeric stamp:** treated like absent — reseed, no catch-up, `WARN`.
- **Unparseable cron row:** skip with `WARN`, never guess.
- **Command bypasses `run_timer_job.sh`:** `SKIP` with a warning (item 4) — never run unguarded.
- **dom + dow both restricted:** classic Vixie-cron OR (matches if *either* matches), verified.
- **Sunday** accepted as both `0` and `7`.
- **Job already running under launchd:** best-effort `launchctl print` skip; if it can't report
  (not loaded / non-root), we still trigger and the wrapper's per-job lock arbitrates.
- **`schedule.tsv` missing:** `WARN`, nothing to do, exit 0.

---

## 2. Crash-loop watcher

The KeepAlive bot wrappers `exec` their target, so they can't trap their own exit. Instead A2a's
`run_bot.sh` appends each start's epoch to `starts/<bot>.log` (interface 0: **one epoch integer per
line**). Every 5 minutes this watcher:

1. For each `starts/*.log`, counts start epochs within the last **`CRASH_WINDOW`** seconds (default
   600). Parsing is **strict** (item 1): a line that is not a plausible epoch integer (9–12 digits) is
   ignored — no `tr`-forced numerification, so a stray human timestamp can't inflate the count into a
   false crash-loop.
2. If the count is **`>= CRASH_THRESHOLD`** (default 5) → crash loop.
3. **Cooldown check:** if `crashwatch_<bot>.notified` is younger than **`CRASH_COOLDOWN`** (default
   1800 s = 30 min) → stay silent. Otherwise call `notify_sisyphe_failure.sh <bot>` and, **only on a
   successful notify**, write the cooldown stamp (a failed alert leaves no stamp, so the next cycle
   retries).

### Crash-watcher desk-check (verified end-to-end)

Thresholds: 5 starts / 600 s window / 1800 s cooldown. `now` = run time.

| Bot | `starts/<bot>.log` (offsets from now, sec) | starts in 600 s window | cooldown stamp | outcome |
|:---|:---|:---:|:---:|:---|
| `normal-bot` | −3600, −2000, −120 | **1** (< 5) | — | `ok`, no alert |
| `crash-bot` | −500, −400, −300, −200, −100, −30 | **6** (≥ 5) | none | **ALERT** → notify + write stamp |
| `cooldown-bot` | −500, −400, −300, −200, −100, −30 | **6** (≥ 5) | notified 300 s ago (< 1800 s) | **COOLDOWN**, silent |

Simulation confirmed: only `crash-bot` produced a `notify_sisyphe_failure.sh` call and a fresh
cooldown stamp; `cooldown-bot` was suppressed; `normal-bot` wrote nothing.

---

## 3. Repo sync (git-pull)

Every 5 minutes, `git_pull.sh` keeps the working tree in sync with origin:

```
cd $REPO
git checkout -- "*.html" 2>/dev/null     # discard bot-regenerated dirty HTML (would abort the pull)
git pull origin main --quiet
```

The `git checkout -- "*.html"` is the VM cron's hard-won fix: the bots continuously rewrite HTML, so a
plain `git pull` would abort forever with "local changes would be overwritten". Discarding those files
first lets the pull fast-forward (a subsequent bot cycle rewrites them anyway).

**Logging / alerting.** Because it runs every 5 minutes, **success is silent** — `git-pull.log` does
not grow, and no stamp is touched (state is reset only if it had been failing). Only failures are
recorded. Consecutive failures are counted in `git-pull.failcount`; once the streak reaches
**`GIT_PULL_FAIL_THRESHOLD`** (default 12 = 1 hour) the runner calls `notify_sisyphe_failure.sh
git-pull` **once**, writes a cooldown stamp (`git-pull.notified`), and stays quiet for
**`GIT_PULL_NOTIFY_COOLDOWN`** (default 3600 s) so a long outage alerts at most hourly rather than
every 5 minutes. A single success resets the counter and clears the cooldown.

This is **not** a calendar job: it has no success stamp and is **not** in `schedule.tsv`, so the
catch-up runner never touches it. Pull-only, so there is no push race with GHA or the bots (each job
does its own `safe_commit_push`).

### Git-pull failure-streak desk-check (verified)

Threshold 12, cooldown 3600 s. Simulated by stubbing `git` to fail and stepping the runner:

| Tick (consecutive fails) | `failcount` | Action |
|:---:|:---:|:---|
| 1 … 11 | 1 … 11 | log `FAIL …`, **no notify** (below threshold) |
| 12 | 12 | log `FAIL` + **ALERT** → `notify git-pull`, write cooldown stamp |
| 13 (still failing, <1 h later) | 13 | log `FAIL`, **no notify** (cooldown active) |
| any success | reset to 0 | silent, cooldown cleared, `git-pull.log` unchanged |

---

## Compatibility (macOS / BSD)

- **Stock `/bin/bash` 3.2** — no associative arrays, `mapfile`, or `${x,,}`; the catch-up runner holds
  missed jobs in parallel indexed arrays. Both plists invoke `/bin/bash` explicitly.
- **No `flock(1)`** — each script uses an atomic `mkdir` lock (catch-up: `catchup.lock`; watcher:
  `crashwatch.lock`) with four defenses:
  1. **Ownership-checked release** — the exit trap deletes the lock **only if our pid is still the one
     recorded in it** (`[ "$(cat $LOCKDIR/pid)" = "$$" ]`). Root defense: no instance can ever delete a
     lock another instance holds.
  2. **Creation-window retry** — owner does `mkdir` then writes its pid a moment later, so a racer that
     reads an empty pid **retries (3×0.2 s)** before judging the lock stale.
  3. **Reclaim without restore** — `mv` the apparently-stale dir aside, then re-verify its pid; if a
     live owner had only-just populated it we do **not** restore (restoring is itself a race) — we leave
     the tombstone and defer. Dead/empty owner → discard tombstone, `mkdir`.
  4. **Orphan GC** — on acquire, sibling `.stale.*` tombstones whose owner pid is dead are removed
     (live tombstones are kept until their owner exits).
- **BSD `ping`** — catch-up uses `ping -c 1 -t 5 <host>` where `-t` is an overall timeout (Git Bash's
  Windows `ping -t` means "loop forever", so the Windows test must set `CATCHUP_NET_WAIT_MAX=0`).
- **BSD `date`** — human-readable log times use `date -r <epoch>`; a `@<epoch>` fallback prints on
  non-mac (which is why test logs show `@…`).
- **KST math** uses a fixed UTC+9 offset in `cron_prev.py`, independent of the system clock TZ, and is
  unit-testable on any OS.

## Environment knobs

| Var | Default | Effect |
|:---|:---:|:---|
| `SCHEDULE_TSV` | `$REPO/logs/launchd/schedule.tsv` | Explicit `schedule.tsv` path (tests). |
| `CATCHUP_NET_WAIT_MAX` | `180` | Seconds to wait for network at boot; `0` skips the probe. |
| `CATCHUP_JOB_TIMEOUT` | `3600` | Per-job watchdog (seconds); best-effort `TERM` on overrun. |
| `CRASH_THRESHOLD` | `5` | Restarts within the window that count as a crash loop. |
| `CRASH_WINDOW` | `600` | Crash-loop detection window (seconds). |
| `CRASH_COOLDOWN` | `1800` | Minimum seconds between alerts per bot. |
| `GIT_PULL_FAIL_THRESHOLD` | `12` | Consecutive git-pull failures before alerting (12 × 5 min = 1 h). |
| `GIT_PULL_NOTIFY_COOLDOWN` | `3600` | Minimum seconds between git-pull alerts while broken. |

## Deploy layout

Per CONTRACT "배포 레이아웃", the whole `launchd/` tree is deployed in-place at `__REPO__/launchd/`,
so these scripts run directly from `__REPO__/launchd/system/` — they are **not** copied to a second
location (avoids double-copy drift). The scripts are therefore token-free and self-locate `$REPO` from
their own path (`launchd/system` → repo root); only the plists carry `__REPO__`/`__MACMINI_USER__`
tokens (they install to `/Library/LaunchDaemons`, which is outside the tree).

## Install

Run from the deployed tree (`__REPO__/launchd/system/`):

```bash
sudo ./install_system.sh [macmini_user]     # defaults to $SUDO_USER
```

The installer does exactly two things: (1) renders the plist tokens and installs all three plists into
`/Library/LaunchDaemons/` (root:wheel, 0644), then bootstraps them; (2) creates
`logs/launchd/{stamps,starts}` and marks the in-place scripts executable. It does **not** copy the
scripts anywhere, and does **not** install `schedule.tsv` (that's A2b's `install_timers.sh`). catchup
then runs at each boot; crash-watcher and git-pull run every 5 minutes.

## Test / dry-run

Trigger a daemon immediately (no reboot):

```bash
sudo launchctl kickstart -k system/com.antigravity.catchup
sudo launchctl kickstart -k system/com.antigravity.crash-watcher
sudo launchctl kickstart -k system/com.antigravity.git-pull
tail -f __REPO__/logs/launchd/catchup.out __REPO__/logs/launchd/crash-watcher.out
```

Force a **git-pull failure streak** — put a failing `git` earlier on PATH and step the runner to the
threshold (should stay silent until the 12th, then alert once):

```bash
REPO=/Users/<user>/Antigravity_Market_Dashboard
d=$(mktemp -d); printf '#!/bin/bash\nexit 1\n' > "$d/git"; chmod +x "$d/git"   # stub: git always fails
for i in $(seq 1 12); do PATH="$d:$PATH" /bin/bash "$REPO/launchd/system/git_pull.sh"; done
tail "$REPO/logs/launchd/git-pull.log"   # 11 FAIL lines silent, 12th adds ALERT + notify
```

Simulate a **missed catch-up job** without touching real schedules — plant a stale stamp:

```bash
REPO=/Users/<user>/Antigravity_Market_Dashboard
name=<a-job-name-from-schedule.tsv>
echo $(( $(date +%s) - 7*86400 )) > "$REPO/logs/launchd/stamps/$name.last"   # "last ran a week ago"
CATCHUP_NET_WAIT_MAX=0 /bin/bash "$REPO/launchd/system/catchup_runner.sh"     # logs MISS -> triggers run_timer_job.sh (which restamps)
```

Preseed only (writes baseline stamps, runs nothing):

```bash
/bin/bash "$REPO/launchd/system/catchup_runner.sh" --seed
```

Simulate a **crash loop** — plant 5+ recent start epochs for a fake bot:

```bash
REPO=/Users/<user>/Antigravity_Market_Dashboard
now=$(date +%s); f="$REPO/logs/launchd/starts/fake-bot.log"
for s in 300 240 180 120 60 10; do echo $((now-s)); done > "$f"
/bin/bash "$REPO/launchd/system/crash_watcher.sh"      # logs ALERT fake-bot -> notify -> cooldown stamp
```

Test just the schedule math in isolation:

```bash
# "20 16 * * *" as if now were 2026-07-08 09:00 KST -> expect 1783408800 (Tue 2026-07-07 16:20)
python3 cron_prev.py "20 16 * * *" $(python3 - <<'PY'
from datetime import datetime,timezone,timedelta
print(int(datetime(2026,7,8,9,0,tzinfo=timezone(timedelta(hours=9))).timestamp()))
PY
)
```

## Risks / limitations

- **Double-run defense lives in the wrapper (item 2):** the authoritative guard against a catch-up
  re-fire racing the launchd timer is `run_timer_job.sh`'s per-job lock (interface 1-1), which both
  paths share. A4's `launchctl print` check is only a best-effort courtesy and may be denied for a
  non-root daemon — that's fine, because the wrapper's lock still arbitrates. (This depends on A2b
  actually implementing that lock; A4 additionally refuses any schedule row that doesn't route through
  `run_timer_job.sh`.)
- **Accepted residual — global-lock reclaim race:** in the rare case where a racer `mv`s aside a lock
  whose owner populated its pid only *after* the 3×0.2 s retry window (so the racer briefly frees
  `$LOCKDIR`), that owner keeps running **without** its global lock. This is deliberately not "restored"
  (restoring is itself a race). Bounded because (a) the ownership-checked release means neither instance
  can delete the other's lock, and (b) the real anti-double-run guard is elsewhere anyway — the
  wrapper's per-job lock for catch-up, and the per-bot cooldown stamp for the crash watcher — so at
  worst a second global-lock holder briefly coexists without causing a duplicate job run or a duplicate
  alert. The abandoned tombstone is GC'd once its owner exits.
- **Watchdog is coarse (catch-up):** A4's outer `TERM` targets the wrapper subshell, not a full
  process group — grandchild cleanup on a hang is the wrapper's process-group timeout (macOS has no
  `timeout(1)` / `setsid` builtin). A4's watchdog is only a backstop so one hung job can't block the
  remaining sequential re-fires.
- **Crash-watcher depends on A2a's start logs:** if `run_bot.sh` doesn't append (or the `starts/` dir
  is empty), a crash loop goes undetected — there's no independent liveness probe here. The 10-line
  cap A2a keeps is fine (threshold ≤ that); if A2a ever trims below the threshold, lower
  `CRASH_THRESHOLD` to match.
- **`eval <command>` (catch-up)** trusts the command strings in `schedule.tsv` (generated by A2b from
  vetted systemd units) — the same trust boundary as the timer wrappers.
