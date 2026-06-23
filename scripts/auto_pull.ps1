# 메인 작업트리 origin 동기화 (매일 16:00 AutoGitPull_Daily 스케줄러 → auto_pull.bat → 이 스크립트)
#
# 근본 설계: 기존 `git pull --ff-only`는 미커밋 변경이 하나라도 있으면 exit 128로 조용히
# 실패(>nul 2>&1) → stale 무한 누적이었다. 이 repo의 메인 트리는 워처(전용 clone push)·
# 봇(deploy.sh 배포)·대시보드 재생성물이 전부 origin 경유로 반영되므로, working copy의
# 추적 변경은 사실상 stale/재생성물이다 → origin이 정답. 따라서 ff 실패 시 patch 백업 후
# reset 한다. 단 (1) 워처 push 진행 중 (2) Wrap_NAV 사용자 미push 저장 은 보류한다.
$ErrorActionPreference = "Continue"
Set-Location "C:\Users\user\Antigravity_Market_Dashboard"

$logDir = "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory $logDir -Force | Out-Null }
$log = Join-Path $logDir ("auto_pull_" + (Get-Date -Format "yyyyMMdd") + ".log")
function Log($m) { ((Get-Date -Format "yyyy-MM-dd HH:mm:ss") + " " + $m) | Add-Content -Path $log -Encoding utf8 }

# (1) 워처 push 진행 중이면 skip — origin/main 포인터 동시이동 race 회피
if (Test-Path ".git\local_safe_push.lock") { Log "워처 push 진행중 → skip"; exit 0 }

git fetch origin main *> $null
$behind = (git rev-list --count HEAD..origin/main 2>$null)
if ($behind -eq "0") { Log "이미 최신 (behind 0)"; exit 0 }

# clean이면 ff-only 빠른 경로
git merge --ff-only origin/main *> $null
if ($LASTEXITCODE -eq 0) { Log "ff 동기화 완료: $behind 커밋"; exit 0 }

# dirty → 전체 diff patch 백업 (복구 가능하게)
$bakDir = "backups"
if (-not (Test-Path $bakDir)) { New-Item -ItemType Directory $bakDir -Force | Out-Null }
$patch = Join-Path $bakDir ("auto_pull_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".patch")
git diff origin/main *> $patch
Log "dirty 감지 → patch 백업: $patch"

# (2) Wrap_NAV 사용자 미push 저장(working mtime > origin 커밋시간)이면 보류 — 워처 push 대기
$wrapDirty = (git status --porcelain -- Wrap_NAV.xlsx 2>$null)
if ($wrapDirty) {
    try {
        $wmt = (Get-Item Wrap_NAV.xlsx).LastWriteTime
        $oiso = (git log -1 --format=%cI origin/main -- Wrap_NAV.xlsx 2>$null)
        if ($oiso) {
            $ocommit = [datetime]::Parse($oiso)
            if ($wmt -gt $ocommit) { Log "Wrap_NAV 사용자 미push 저장(working > origin) → 동기화 보류, 워처 대기"; exit 0 }
        }
    } catch { Log "Wrap_NAV mtime 비교 예외: $_" }
}

# working은 재생성물/stale → origin이 정답. reset로 동기화 (untracked 파일은 보존됨)
git reset --hard origin/main *> $null
if ($LASTEXITCODE -eq 0) { Log "reset 동기화 완료: $behind 커밋 (변경분은 patch 보관)" }
else { Log "FAIL: reset 실패 (exit $LASTEXITCODE) — 수동 확인 필요" }

# 30일 지난 백업/로그 정리
Get-ChildItem $bakDir -Filter "*.patch" -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem $logDir -Filter "auto_pull_*.log" -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force -ErrorAction SilentlyContinue
