"""
Wrap_NAV.xlsx 파일 감시 → 변경 시 자동 git commit & push
Windows 시작 시 백그라운드로 실행됨
"""

import time
import subprocess
import logging
import sys
import os
import threading
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
WATCH_FILE = "Wrap_NAV.xlsx"
LOG_FILE = os.path.join(REPO_DIR, "watch_wrap_nav.log")
DEBOUNCE_SECONDS = 8   # Excel 저장 후 파일 잠금 해제까지 여유 확보
MAX_RETRIES = 3        # git 실패 시 재시도 횟수
RETRY_INTERVAL = 3     # 재시도 간격 (초)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)


def git_push():
    """git add → commit → pull --rebase → push (실패 시 재시도)"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # 변경사항 있는지 확인
            diff = subprocess.run(
                ["git", "diff", "--quiet", WATCH_FILE],
                cwd=REPO_DIR,
            )
            if diff.returncode == 0:
                logging.info("변경사항 없음 - push 생략")
                return True

            commit_msg = f"update: Wrap_NAV.xlsx ({datetime.now().strftime('%Y-%m-%d %H:%M')})"

            # git add
            add = subprocess.run(
                ["git", "add", WATCH_FILE],
                cwd=REPO_DIR,
                capture_output=True, text=True,
            )
            if add.returncode != 0:
                raise RuntimeError(f"git add 실패: {add.stderr.strip()}")

            # git commit
            commit = subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=REPO_DIR,
                capture_output=True, text=True,
            )
            if commit.returncode != 0:
                raise RuntimeError(f"git commit 실패: {commit.stderr.strip()}")
            logging.info(f"commit: {commit_msg}")

            # git pull --rebase
            subprocess.run(
                ["git", "pull", "--rebase", "origin", "main"],
                cwd=REPO_DIR,
                capture_output=True, text=True, timeout=60,
            )

            # git push
            push = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=REPO_DIR,
                capture_output=True, text=True, timeout=60,
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


class WrapNavHandler(FileSystemEventHandler):
    def __init__(self):
        self._lock = threading.Lock()   # 스레드 안전한 디바운스
        self._timer = None              # 대기 중인 타이머

    def on_modified(self, event):
        filename = os.path.basename(event.src_path)

        # 대상 파일 외 무시 (임시 파일 ~$ 포함)
        if filename != WATCH_FILE or filename.startswith("~$"):
            return

        with self._lock:
            # 기존 타이머 취소 (디바운스 리셋)
            if self._timer is not None:
                self._timer.cancel()

            # 새 타이머 시작 (DEBOUNCE_SECONDS 후 git_push 실행)
            self._timer = threading.Timer(DEBOUNCE_SECONDS, self._run_push)
            self._timer.daemon = True
            self._timer.start()
            logging.info(f"변경 감지: {WATCH_FILE} → {DEBOUNCE_SECONDS}초 후 push")

    def _run_push(self):
        git_push()


if __name__ == "__main__":
    logging.info("=== Wrap_NAV 감시 시작 ===")
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
