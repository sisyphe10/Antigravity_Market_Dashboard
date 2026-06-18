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
try:
    import psutil
except ImportError:
    psutil = None
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
# PID 존재 여부만 보면 (1) 죽은 워처가 비정상 종료해 남긴 stale pid, (2) 그 PID가
# 다른 프로세스로 재활용된 경우에 "이미 실행 중"으로 오판해 재기동이 막힌다.
# → PID_FILE을 원자적(O_EXCL) 락으로 쓰고, 충돌 시 그 PID가 *실제로* 살아있는
#   watch_wrap_nav 파이썬 프로세스인지 psutil로 검증한다(레이스 안전 + stale 자가복구).
def _pid_is_watcher(pid):
    """pid가 살아있는 watch_wrap_nav.py 파이썬 프로세스면 True."""
    if pid == os.getpid():
        return False
    if psutil is None:
        # psutil 없으면 보수적 폴백: 살아있으면 워처로 간주
        try:
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
        except Exception:
            pass
        return False
    try:
        p = psutil.Process(pid)
        if "python" not in (p.name() or "").lower():
            return False
        return "watch_wrap_nav" in " ".join(p.cmdline()).lower()
    except Exception:
        return False


def check_single_instance():
    for _ in range(5):
        try:
            fd = os.open(PID_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            atexit.register(lambda: os.remove(PID_FILE) if os.path.exists(PID_FILE) else None)
            return
        except FileExistsError:
            try:
                owner = int(open(PID_FILE).read().strip())
            except (ValueError, OSError):
                owner = None
            if owner is not None and _pid_is_watcher(owner):
                logging.warning(f"이미 실행 중인 워처 (PID {owner}). 종료합니다.")
                sys.exit(0)
            logging.warning(f"stale/foreign pid 파일 (owner={owner}) 제거 후 재시도")
            try:
                os.remove(PID_FILE)
            except OSError:
                pass
    logging.error("single-instance 락 획득 실패 — 종료")
    sys.exit(1)


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
def _make_observer(handler):
    obs = Observer()
    obs.schedule(handler, path=REPO_DIR, recursive=False)
    obs.start()
    return obs


if __name__ == "__main__":
    check_single_instance()

    logging.info("=== Wrap_NAV 감시 시작 ===")
    logging.info(f"PID: {os.getpid()}")
    logging.info(f"감시 경로: {os.path.join(REPO_DIR, WATCH_FILE)}")
    logging.info(f"디바운스: {DEBOUNCE_SECONDS}초, push 정책: local_safe_push sync_and_push (전용 clone, merge-only)")

    handler = WrapNavHandler()
    observer = _make_observer(handler)

    # 절전/재개로 Observer 스레드만 죽고 프로세스는 살아있는 좀비 상태가 되면
    # 파일 변경을 더 이상 감지하지 못한다 → is_alive() 확인 후 자동 재시작.
    try:
        while True:
            time.sleep(5)
            if not observer.is_alive():
                logging.warning("Observer 스레드 death 감지 → 재시작 (절전/재개 추정)")
                try:
                    observer.stop()
                    observer.join(timeout=5)
                except Exception as e:
                    logging.warning(f"기존 observer 정리 중 예외 무시: {e}")
                observer = _make_observer(handler)
                logging.info("Observer 재시작 완료")
    except KeyboardInterrupt:
        observer.stop()
        logging.info("감시 종료")
    observer.join()
