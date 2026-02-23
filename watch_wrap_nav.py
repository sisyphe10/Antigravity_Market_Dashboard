"""
Wrap_NAV.xlsx 파일 감시 → 변경 시 자동 git commit & push
Windows 시작 시 백그라운드로 실행됨 (중복 실행 방지)
"""

import time
import subprocess
import logging
import sys
import os
import threading
import atexit
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
WATCH_FILE = "Wrap_NAV.xlsx"
LOG_FILE = os.path.join(REPO_DIR, "watch_wrap_nav.log")
PID_FILE = os.path.join(REPO_DIR, "watch_wrap_nav.pid")
DEBOUNCE_SECONDS = 8
MAX_RETRIES = 3
RETRY_INTERVAL = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)


# ── 중복 실행 방지 ─────────────────────────────────────
def check_single_instance():
    if os.path.exists(PID_FILE):
        with open(PID_FILE) as f:
            old_pid = int(f.read().strip())
        # 기존 PID가 실제로 실행 중인지 확인
        try:
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, old_pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                logging.warning(f"이미 실행 중 (PID {old_pid}). 종료합니다.")
                sys.exit(0)
        except Exception:
            pass  # PID 확인 실패 시 무시하고 계속 실행

    # 현재 PID 기록
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    # 종료 시 PID 파일 삭제
    atexit.register(lambda: os.remove(PID_FILE) if os.path.exists(PID_FILE) else None)


# ── git push ───────────────────────────────────────────
def git_push():
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # 아직 commit 안 된 변경사항이 있으면 commit
            diff = subprocess.run(
                ["git", "diff", "--quiet", WATCH_FILE],
                cwd=REPO_DIR,
            )
            if diff.returncode != 0:
                commit_msg = f"update: Wrap_NAV.xlsx ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
                add = subprocess.run(
                    ["git", "add", WATCH_FILE],
                    cwd=REPO_DIR, capture_output=True, text=True,
                )
                if add.returncode != 0:
                    raise RuntimeError(f"git add 실패 (exit {add.returncode}): {add.stderr.strip()}")
                commit = subprocess.run(
                    ["git", "commit", "-m", commit_msg],
                    cwd=REPO_DIR, capture_output=True, text=True,
                )
                if commit.returncode != 0:
                    raise RuntimeError(f"git commit 실패: {commit.stderr.strip()}")
                logging.info(f"commit: {commit_msg}")

            # push 안 된 commit이 없으면 생략
            ahead = subprocess.run(
                ["git", "log", "origin/main..HEAD", "--oneline"],
                cwd=REPO_DIR, capture_output=True, text=True,
            )
            if not ahead.stdout.strip():
                logging.info("push할 커밋 없음 - 생략")
                return True

            # pull --rebase 후 push
            subprocess.run(
                ["git", "pull", "--rebase", "origin", "main"],
                cwd=REPO_DIR, capture_output=True, text=True, timeout=60,
            )
            push = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=REPO_DIR, capture_output=True, text=True, timeout=60,
            )
            if push.returncode == 0:
                logging.info("✅ GitHub push 성공")
                return True
            else:
                raise RuntimeError(f"git push 실패: {push.stderr.strip()}")

        except Exception as e:
            logging.warning(f"⚠️ 시도 {attempt}/{MAX_RETRIES} 실패: {e}")
            if attempt < MAX_RETRIES:
                logging.info(f"{RETRY_INTERVAL}초 후 재시도...")
                time.sleep(RETRY_INTERVAL)
            else:
                logging.error("❌ 최대 재시도 횟수 초과. push 실패.")
                return False


# ── 파일 감시 핸들러 ───────────────────────────────────
class WrapNavHandler(FileSystemEventHandler):
    def __init__(self):
        self._lock = threading.Lock()
        self._timer = None

    def on_modified(self, event):
        filename = os.path.basename(event.src_path)
        if filename != WATCH_FILE or filename.startswith("~$"):
            return

        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SECONDS, self._run_push)
            self._timer.daemon = True
            self._timer.start()
        logging.info(f"변경 감지: {WATCH_FILE} → {DEBOUNCE_SECONDS}초 후 push")

    def _run_push(self):
        git_push()


# ── 메인 ──────────────────────────────────────────────
if __name__ == "__main__":
    check_single_instance()

    logging.info("=== Wrap_NAV 감시 시작 ===")
    logging.info(f"PID: {os.getpid()}")
    logging.info(f"감시 경로: {os.path.join(REPO_DIR, WATCH_FILE)}")
    logging.info(f"디바운스: {DEBOUNCE_SECONDS}초, 최대 재시도: {MAX_RETRIES}회")

    handler = WrapNavHandler()
    observer = Observer()
    observer.schedule(handler, path=REPO_DIR, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logging.info("감시 종료")
    observer.join()
