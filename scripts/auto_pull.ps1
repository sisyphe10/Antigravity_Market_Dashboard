# Sync main worktree with origin (daily 16:00: AutoGitPull_Daily -> auto_pull.bat -> this script)
#
# Root fix: old `git pull --ff-only` failed with exit 128 (silently, >nul 2>&1) whenever ANY
# uncommitted change existed -> 398-commit stale accumulation. This repo's main tree changes are
# effectively stale/regenerated artifacts (watcher pushes via dedicated clone, bots deploy via
# deploy.sh, dashboards are regenerated), so origin is authoritative. On ff failure: back up the
# full diff as a patch, then reset. Defer only if (1) watcher is pushing, (2) Wrap_NAV has an
# unpushed user save. (English-only: PowerShell 5.x mis-decodes BOM-less UTF-8 Korean.)
$ErrorActionPreference = "Continue"
Set-Location "C:\Users\user\Antigravity_Market_Dashboard"

$logDir = "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory $logDir -Force | Out-Null }
$log = Join-Path $logDir ("auto_pull_" + (Get-Date -Format "yyyyMMdd") + ".log")
function Log($m) { ((Get-Date -Format "yyyy-MM-dd HH:mm:ss") + " " + $m) | Add-Content -Path $log -Encoding utf8 }

# (1) Watcher push in progress -> skip (avoid origin/main pointer race)
if (Test-Path ".git\local_safe_push.lock") { Log "watcher push in progress -> skip"; exit 0 }

git fetch origin main *> $null
$behind = (git rev-list --count HEAD..origin/main 2>$null)
if ($behind -eq "0") { Log "already up to date (behind 0)"; exit 0 }

# Clean -> ff-only fast path
git merge --ff-only origin/main *> $null
if ($LASTEXITCODE -eq 0) { Log "ff sync done: $behind commits"; exit 0 }

# Dirty -> back up full diff as a patch (recoverable)
$bakDir = "backups"
if (-not (Test-Path $bakDir)) { New-Item -ItemType Directory $bakDir -Force | Out-Null }
$patch = Join-Path $bakDir ("auto_pull_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".patch")
git diff origin/main *> $patch
Log "dirty detected -> patch backup: $patch"

# (2) Wrap_NAV unpushed user save (working mtime > origin commit time) -> defer for watcher push
$wrapDirty = (git status --porcelain -- Wrap_NAV.xlsx 2>$null)
if ($wrapDirty) {
    try {
        $wmt = (Get-Item Wrap_NAV.xlsx).LastWriteTime
        $oiso = (git log -1 --format=%cI origin/main -- Wrap_NAV.xlsx 2>$null)
        if ($oiso) {
            $ocommit = [datetime]::Parse($oiso)
            if ($wmt -gt $ocommit) { Log "Wrap_NAV unpushed user save (working > origin) -> defer for watcher"; exit 0 }
        }
    } catch { Log "Wrap_NAV mtime compare failed: $_" }
}

# Working tree is regenerated/stale -> origin authoritative. reset (untracked files preserved)
git reset --hard origin/main *> $null
if ($LASTEXITCODE -eq 0) { Log "reset sync done: $behind commits (changes saved in patch backup)" }
else { Log "FAIL: reset failed (exit $LASTEXITCODE) -- manual check needed" }

# Cleanup backups/logs older than 30 days
Get-ChildItem $bakDir -Filter "*.patch" -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem $logDir -Filter "auto_pull_*.log" -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force -ErrorAction SilentlyContinue
