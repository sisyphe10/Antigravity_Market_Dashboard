"""
Wrap_NAV.xlsx 파일 감시 → 변경 시 자동 git commit & push
Windows 시작 시 백그라운드로 실행됨 (중복 실행 방지)
"""

import time
import logging
import sys
import os
import threading
import atexit
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(REPO_DIR, "scripts"))
import local_safe_push  # noqa: E402  (merge-only push policy lives there)

WATCH_FILE = "Wrap_NAV.xlsx"
LOG_FILE = os.path.join(REPO_DIR, "watch_wrap_nav.log")
PID_FILE = os.path.join(REPO_DIR, "watch_wrap_nav.pid")
DEBOUNCE_SECONDS = 8

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
_push_lock = threading.Lock()  # overlapping debounce timers must not interleave


def git_push():
    with _push_lock:
        try:
            # 전용 clone에서 push — 메인 작업트리의 git 상태는 건드리지 않음
            return local_safe_push.sync_and_push(REPO_DIR, log=logging.getLogger())
        except Exception as e:
            logging.error(f"❌ push 실패 (예외): {e}")
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
    logging.info(f"디바운스: {DEBOUNCE_SECONDS}초, push 정책: local_safe_push sync_and_push (전용 clone, merge-only)")

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
