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
      * Wrap_NAV.xlsx changed on BOTH sides since merge-base -> 3-way
        sheet-level merge via merge_wrap_nav.py (NEW/AUM row semantics,
        local user side wins same-key edits). Only if THAT declares a
        domain conflict (or Excel holds a write lock) -> HOLD file, loud
        log, keep the local commit unpushed.
      * otherwise merge --no-ff --no-commit; files OUR commits changed -> ours,
        every other conflict -> theirs (the remote actor is authoritative for
        files we didn't touch); commit; retry push.
  - Cross-process lockfile so watcher / button / sessions don't interleave.

sync_and_push() additionally isolates the unattended actors (watcher, manual
button, .bat) into a DEDICATED CLONE (~/.wrapnav_pushclone) so their git
operations never touch the main working tree a Claude session may be using.
KEY: the user's Excel copy forked from the MAIN repo's HEAD xlsx while the
clone tracks origin — committing the user file verbatim would read missing
remote rows as deletions and clobber them on a clean fast-forward, so every
sync runs a file-level 3-way (base=main HEAD xlsx, ours=user file,
theirs=clone xlsx) BEFORE committing. Remote rows folded in by the merge are
copied back to the user's file (only if the user hasn't saved meanwhile, and
Excel isn't locking it). The HOLD marker is mirrored into the main repo for
visibility; deleting the main-repo copy resumes pushing.

While the HOLD file exists every push attempt is skipped — resolve the xlsx
divergence manually (see HOLD file body), delete the HOLD file, save again.
"""

import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime

XLSX = "Wrap_NAV.xlsx"
HOLD_FILE = "Wrap_NAV_push.HOLD"
LOCK_FILE = os.path.join(".git", "local_safe_push.lock")
LOCK_STALE_SECONDS = 300
LOCK_WAIT_SECONDS = 90
PUSH_ATTEMPTS = 3
DEFAULT_CLONE_DIR = os.path.expanduser("~/.wrapnav_pushclone")

HOLD_BODY = """Wrap_NAV.xlsx push HOLD — {now}

원격(origin/main)과 로컬이 merge-base 이후 둘 다 Wrap_NAV.xlsx를 수정했고,
시트 병합(merge_wrap_nav)으로도 자동 해결하지 못했습니다 (로컬 변경은 보존됨).

수동 해결 절차:
  1. git fetch origin main
  2. 원격 xlsx에 뭐가 추가됐는지 확인: git log --oneline HEAD..origin/main -- Wrap_NAV.xlsx
  3. 보통은: 원격 버전을 받고(NEW/AUM 원격 행 확인) 로컬에서 추가했던
     NEW/AUM 행을 다시 입력(add_aum.py 재실행 등) 후 commit
  4. 이 파일(Wrap_NAV_push.HOLD)을 삭제하면 자동 push가 재개됩니다.
"""


def _git(args, repo_dir, timeout=60):
    return subprocess.run(
        ["git"] + args, cwd=repo_dir, capture_output=True, text=True, timeout=timeout
    )


def _git_show_blob(ref, repo_dir, out_path):
    """git show <ref>:Wrap_NAV.xlsx -> binary file."""
    with open(out_path, "wb") as f:
        r = subprocess.run(
            ["git", "show", f"{ref}:{XLSX}"], cwd=repo_dir, stdout=f,
            stderr=subprocess.PIPE, timeout=60,
        )
    return r.returncode == 0


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


def _write_hold(repo_dir, log, reason):
    hold_path = os.path.join(repo_dir, HOLD_FILE)
    with open(hold_path, "w", encoding="utf-8") as f:
        f.write(HOLD_BODY.format(now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        f.write(f"\n보류 사유: {reason}\n")
    log.error("⛔ push 보류 (%s) — %s 참고.", reason, HOLD_FILE)


def _try_domain_merge(repo_dir, base, log):
    """3-way sheet merge of base/HEAD/origin xlsx. Returns merged temp path or None."""
    try:
        import merge_wrap_nav  # same scripts/ dir; needs pandas+openpyxl
    except ImportError as e:
        log.warning("merge_wrap_nav 사용 불가 (%s) — HOLD로 폴백", e)
        return None

    tmpdir = tempfile.mkdtemp(prefix="wrapnav_merge_")
    paths = {}
    for label, ref in (("base", base), ("ours", "HEAD"), ("theirs", "origin/main")):
        paths[label] = os.path.join(tmpdir, f"{label}.xlsx")
        if not _git_show_blob(ref, repo_dir, paths[label]):
            log.error("%s xlsx 추출 실패 (%s)", label, ref)
            return None
    out = os.path.join(tmpdir, "merged.xlsx")
    try:
        merge_wrap_nav.merge_files(
            paths["base"], paths["ours"], paths["theirs"], out,
            prefer="ours", log=lambda m: log.info("[merge_wrap_nav] %s", m),
        )
        return out
    except merge_wrap_nav.MergeConflict as e:
        log.error("xlsx 도메인 병합 충돌: %s — HOLD로 폴백", e)
        return None
    except Exception as e:
        log.error("xlsx 도메인 병합 오류: %s: %s — HOLD로 폴백", type(e).__name__, e)
        return None


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
        merged_xlsx = None
        if ours_xlsx and theirs_xlsx:
            merged_xlsx = _try_domain_merge(repo_dir, base, log)
            if merged_xlsx is None:
                _write_hold(repo_dir, log, f"{XLSX} 양쪽 수정 — 시트 병합 실패/충돌, 수동 해결 필요")
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

        if merged_xlsx:
            try:
                shutil.copyfile(merged_xlsx, os.path.join(repo_dir, XLSX))
            except PermissionError:
                _git(["merge", "--abort"], repo_dir)
                _write_hold(repo_dir, log,
                            f"Excel이 {XLSX}를 잠그고 있어 병합 결과를 쓰지 못함 — "
                            "Excel을 닫고 HOLD 삭제 후 다시 저장하면 재개")
                return False
            _git(["add", "--", XLSX], repo_dir)
            log.info("✅ %s 시트 병합 적용 (로컬+원격 행 모두 보존)", XLSX)

        commit = _git(["commit", "--no-edit"], repo_dir)
        if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr):
            log.error("merge commit 실패: %s", (commit.stderr or commit.stdout).strip())
            _git(["merge", "--abort"], repo_dir)
            return False
        log.info("merge origin/main 완료 (ours: %d개 파일 유지)", len(our_changed))

    log.error("❌ push 재시도 %d회 초과 — 실패.", PUSH_ATTEMPTS)
    return False


# ── dedicated push clone (watcher/button isolation) ────


def _file_hash(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_clone(main_repo, clone_dir, log):
    if os.path.isdir(os.path.join(clone_dir, ".git")):
        return True
    url = _git(["remote", "get-url", "origin"], main_repo).stdout.strip()
    if not url:
        log.error("origin URL 확인 실패 — clone 생성 불가")
        return False
    log.info("push 전용 clone 생성 중: %s (1회성, 수 분 소요 가능)", clone_dir)
    r = subprocess.run(
        ["git", "clone", "--filter=blob:none", "--no-tags", url, clone_dir],
        capture_output=True, text=True, timeout=1800,
    )
    if r.returncode != 0:
        log.error("clone 실패: %s", r.stderr.strip()[-300:])
        return False
    log.info("clone 생성 완료")
    return True


def sync_and_push(main_repo, clone_dir=DEFAULT_CLONE_DIR, log=None):
    """Watcher/button entry point: push the main repo's xlsx via the clone."""
    if log is None:
        import logging
        log = logging.getLogger("local_safe_push")

    main_hold = os.path.join(main_repo, HOLD_FILE)
    clone_hold = os.path.join(clone_dir, HOLD_FILE)

    if os.path.exists(main_hold):
        log.warning("⛔ %s 존재 — push 보류 중. 수동 해결 후 파일 삭제 필요.", HOLD_FILE)
        return False
    if os.path.exists(clone_hold):  # user deleted the main-repo copy -> resume
        os.remove(clone_hold)
        log.info("HOLD 해제 감지 — push 재개")

    # the main repo only gets READ here, but a half-finished merge would make
    # its HEAD xlsx (= our 3-way base) unreliable
    marker = _git_state_in_progress(main_repo)
    if marker:
        log.warning("메인 repo가 git %s 진행 중 — 이번 회차 건너뜀", marker)
        return False

    # A Claude session may hold committed-but-unpushed xlsx work in the main
    # repo; pushing the shared file from here would race it. Stand down.
    unpushed = _git(["log", "--oneline", "origin/main..HEAD", "--", XLSX], main_repo)
    if unpushed.stdout.strip():
        log.info("메인 repo에 미push xlsx 커밋 존재 — 세션이 push 예정, 워처는 대기")
        return True

    if not _ensure_clone(main_repo, clone_dir, log):
        return False
    marker = _git_state_in_progress(clone_dir)
    if marker:
        log.error("⛔ clone이 git %s 진행 중 — push 중단", marker)
        return False

    lock = _acquire_lock(clone_dir, log)
    if lock is None:
        log.error("⛔ push lock 획득 실패 (%ds 대기) — 다른 push 진행 중?", LOCK_WAIT_SECONDS)
        return False
    try:
        return _sync_and_push_locked(main_repo, clone_dir, main_hold, clone_hold, log)
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def _sync_and_push_locked(main_repo, clone_dir, main_hold, clone_hold, log):
    fetch = _git(["fetch", "origin", "main"], clone_dir, timeout=120)
    if fetch.returncode != 0:
        log.warning("clone fetch 실패 (%s) — stale 기준으로 진행, push 시 재동기화",
                    fetch.stderr.strip()[-120:])
    _git(["merge", "--ff-only", "origin/main"], clone_dir)

    # File-level 3-way: the user's copy forked from the main repo's HEAD xlsx,
    # while the clone tracks origin. Copying the user file in verbatim would
    # make git read missing remote rows as deletions and clobber them on a
    # clean fast-forward — so merge BEFORE committing, every time.
    src = os.path.join(main_repo, XLSX)
    dst = os.path.join(clone_dir, XLSX)
    src_hash = _file_hash(src)
    if src_hash == _file_hash(dst):
        log.info("xlsx 동일 — push할 변경 없음")
        return True

    try:
        import merge_wrap_nav
    except ImportError as e:
        log.error("merge_wrap_nav 사용 불가 (%s) — push 중단", e)
        return False

    tmpdir = tempfile.mkdtemp(prefix="wrapnav_sync_")
    base = os.path.join(tmpdir, "base.xlsx")
    ours = os.path.join(tmpdir, "ours.xlsx")
    merged = os.path.join(tmpdir, "merged.xlsx")
    if not _git_show_blob("HEAD", main_repo, base):
        log.error("메인 repo HEAD xlsx 추출 실패 — push 중단")
        return False
    try:
        shutil.copyfile(src, ours)
        merge_wrap_nav.merge_files(
            base, ours, dst, merged, prefer="ours",
            log=lambda m: log.info("[merge_wrap_nav] %s", m),
        )
        shutil.copyfile(merged, dst)
    except merge_wrap_nav.MergeConflict as e:
        _write_hold(clone_dir, log, f"시트 병합 충돌: {e}")
        shutil.copyfile(clone_hold, main_hold)
        log.error("⛔ %s 를 메인 폴더에 생성 — 해결 후 삭제하면 재개됩니다.", HOLD_FILE)
        return False
    except OSError as e:
        log.error("xlsx 병합/복사 실패 (%s) — push 중단", e)
        return False

    ok = _safe_push_locked(clone_dir, log)

    if os.path.exists(clone_hold):  # surface the HOLD where the user can see it
        shutil.copyfile(clone_hold, main_hold)
        log.error("⛔ %s 를 메인 폴더에 생성 — 해결 후 삭제하면 재개됩니다.", HOLD_FILE)

    if ok and not merge_wrap_nav.files_equal(merged, ours):
        # the merge folded in remote rows -> sync them back to the user's copy,
        # but never overwrite an Excel save that happened meanwhile
        try:
            if _file_hash(src) == src_hash:
                shutil.copyfile(merged, src)
                log.info("🔄 원격 행 역동기화 완료 (%s 갱신)", XLSX)
            else:
                log.warning("역동기화 보류 — 사용자 저장이 먼저 감지됨 (다음 push 때 병합)")
        except PermissionError:
            log.warning("역동기화 보류 — Excel이 %s 잠금 (다음 저장 때 재시도)", XLSX)
    return ok


if __name__ == "__main__":
    import logging
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ok = sync_and_push(repo, log=logging.getLogger("local_safe_push"))
    sys.exit(0 if ok else 1)
