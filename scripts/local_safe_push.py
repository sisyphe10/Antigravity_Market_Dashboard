"""
local_safe_push.py — race-safe commit+push for LOCAL Wrap_NAV.xlsx actors.

Local counterpart of scripts/safe_commit_push.sh (GHA side). Shared by:
  - watch_wrap_nav.py  (watchdog auto-push on Excel save)
  - push_wrap_nav.py   (manual push button)
  - push_wrap_nav.bat  (calls this module's CLI)

Policy (mirrors safe_commit_push.sh, from the local perspective):
  - NEVER rebase. Merge only (project rule: feedback_git_conflict).
  - Refuse to touch git while a rebase/merge is already in progress.
  - On push rejection: fetch, then
      * Wrap_NAV.xlsx changed on BOTH sides since merge-base -> do NOT guess.
        Write a HOLD file, log loudly, keep the local commit unpushed.
        (whole-file ours/theirs would silently drop one side's NEW/AUM rows)
      * otherwise merge --no-ff --no-commit; files OUR commits changed -> ours,
        every other conflict -> theirs (the remote actor is authoritative for
        files we didn't touch); commit; retry push.
  - Cross-process lockfile so watcher / button / sessions don't interleave.

While the HOLD file exists every push attempt is skipped — resolve the xlsx
divergence manually (see HOLD file body), delete the HOLD file, save again.
"""

import os
import subprocess
import time
from datetime import datetime

XLSX = "Wrap_NAV.xlsx"
HOLD_FILE = "Wrap_NAV_push.HOLD"
LOCK_FILE = os.path.join(".git", "local_safe_push.lock")
LOCK_STALE_SECONDS = 300
LOCK_WAIT_SECONDS = 90
PUSH_ATTEMPTS = 3

HOLD_BODY = """Wrap_NAV.xlsx push HOLD — {now}

원격(origin/main)과 로컬이 merge-base 이후 둘 다 Wrap_NAV.xlsx를 수정했습니다.
바이너리라 자동 병합이 불가능해 push를 보류했습니다 (로컬 커밋은 보존됨).

수동 해결 절차:
  1. git fetch origin main
  2. 원격 xlsx에 뭐가 추가됐는지 확인: git log --oneline HEAD..origin/main -- Wrap_NAV.xlsx
  3. 보통은: git merge origin/main (xlsx 충돌) -> git checkout --theirs Wrap_NAV.xlsx
     -> 로컬에서 추가했던 NEW/AUM 행을 다시 입력(add_aum.py 재실행 등) -> commit
  4. 이 파일(Wrap_NAV_push.HOLD)을 삭제하면 자동 push가 재개됩니다.
"""


def _git(args, repo_dir, timeout=60):
    return subprocess.run(
        ["git"] + args, cwd=repo_dir, capture_output=True, text=True, timeout=timeout
    )


def _git_state_in_progress(repo_dir):
    g = os.path.join(repo_dir, ".git")
    for marker in ("rebase-merge", "rebase-apply", "MERGE_HEAD"):
        if os.path.exists(os.path.join(g, marker)):
            return marker
    return None


def _acquire_lock(repo_dir, log):
    path = os.path.join(repo_dir, LOCK_FILE)
    deadline = time.time() + LOCK_WAIT_SECONDS
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return path
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(path) > LOCK_STALE_SECONDS:
                    log.warning("stale push lock 제거 (>%ds)", LOCK_STALE_SECONDS)
                    os.remove(path)
                    continue
            except OSError:
                continue
            if time.time() > deadline:
                return None
            time.sleep(2)


def safe_push(repo_dir, log):
    """Commit a dirty Wrap_NAV.xlsx (if any) and push local commits. True on success."""
    if os.path.exists(os.path.join(repo_dir, HOLD_FILE)):
        log.warning("⛔ %s 존재 — push 보류 중. 수동 해결 후 파일 삭제 필요.", HOLD_FILE)
        return False

    marker = _git_state_in_progress(repo_dir)
    if marker:
        log.error("⛔ git %s 진행 중 — push 중단. 저장소 상태를 먼저 정리하세요.", marker)
        return False

    lock = _acquire_lock(repo_dir, log)
    if lock is None:
        log.error("⛔ push lock 획득 실패 (%ds 대기) — 다른 push 진행 중?", LOCK_WAIT_SECONDS)
        return False
    try:
        return _safe_push_locked(repo_dir, log)
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def _safe_push_locked(repo_dir, log):
    # commit a dirty xlsx exactly like the old watcher did
    if _git(["diff", "--quiet", "--", XLSX], repo_dir).returncode != 0:
        msg = f"update: {XLSX} ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
        add = _git(["add", "--", XLSX], repo_dir)
        if add.returncode != 0:
            log.error("git add 실패: %s", add.stderr.strip())
            return False
        commit = _git(["commit", "-m", msg], repo_dir)
        if commit.returncode != 0:
            log.error("git commit 실패: %s", commit.stderr.strip())
            return False
        log.info("commit: %s", msg)

    ahead = _git(["log", "origin/main..HEAD", "--oneline"], repo_dir)
    if not ahead.stdout.strip():
        log.info("push할 커밋 없음 - 생략")
        return True

    for attempt in range(1, PUSH_ATTEMPTS + 1):
        push = _git(["push", "origin", "main"], repo_dir)
        if push.returncode == 0:
            log.info("✅ GitHub push 성공 (시도 %d)", attempt)
            return True

        log.warning("push 거부 (시도 %d/%d) — origin 동기화", attempt, PUSH_ATTEMPTS)
        fetch = _git(["fetch", "origin", "main"], repo_dir, timeout=120)
        if fetch.returncode != 0:
            log.error("git fetch 실패: %s", fetch.stderr.strip())
            time.sleep(3)
            continue

        # already contains origin (race lost to our own earlier merge) -> just retry
        if _git(["merge-base", "--is-ancestor", "origin/main", "HEAD"], repo_dir).returncode == 0:
            time.sleep(3)
            continue

        base = _git(["merge-base", "HEAD", "origin/main"], repo_dir).stdout.strip()
        if not base:
            log.error("merge-base 계산 실패 — push 중단")
            return False

        ours_xlsx = _git(["diff", "--quiet", base, "HEAD", "--", XLSX], repo_dir).returncode != 0
        theirs_xlsx = _git(["diff", "--quiet", base, "origin/main", "--", XLSX], repo_dir).returncode != 0
        if ours_xlsx and theirs_xlsx:
            hold_path = os.path.join(repo_dir, HOLD_FILE)
            with open(hold_path, "w", encoding="utf-8") as f:
                f.write(HOLD_BODY.format(now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            log.error(
                "⛔ %s가 로컬·원격 양쪽에서 수정됨 — 자동 병합 불가, push 보류. %s 참고.",
                XLSX, HOLD_FILE,
            )
            return False

        our_changed = [
            f for f in _git(["diff", "--name-only", base, "HEAD"], repo_dir).stdout.splitlines() if f
        ]

        _git(["merge", "--no-ff", "--no-commit", "origin/main"], repo_dir, timeout=120)

        # whole-file policy: our commits' files -> ours; leftover conflicts -> theirs
        for f in our_changed:
            _git(["checkout", "HEAD", "--", f], repo_dir)
            _git(["add", "--", f], repo_dir)
        conflicted = [
            f for f in _git(["diff", "--name-only", "--diff-filter=U"], repo_dir).stdout.splitlines() if f
        ]
        for f in conflicted:
            _git(["checkout", "origin/main", "--", f], repo_dir)
            _git(["add", "--", f], repo_dir)

        commit = _git(["commit", "--no-edit"], repo_dir)
        if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr):
            log.error("merge commit 실패: %s", (commit.stderr or commit.stdout).strip())
            _git(["merge", "--abort"], repo_dir)
            return False
        log.info("merge origin/main 완료 (ours: %d개 파일 유지)", len(our_changed))

    log.error("❌ push 재시도 %d회 초과 — 실패.", PUSH_ATTEMPTS)
    return False


if __name__ == "__main__":
    import logging
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ok = safe_push(repo, logging.getLogger("local_safe_push"))
    sys.exit(0 if ok else 1)
