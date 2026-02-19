"""
Wrap_NAV.xlsx 파일 감시 → 변경 시 자동 git commit & push
Windows 시작 시 백그라운드로 실행됨
"""

import time
import subprocess
import logging
import sys
import os
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
WATCH_FILE = "Wrap_NAV.xlsx"
LOG_FILE = os.path.join(REPO_DIR, "watch_wrap_nav.log")
DEBOUNCE_SECONDS = 5  # Excel은 저장 시 여러 번 쓰기 이벤트 발생 → 5초 대기

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)


def git_push():
    """변경사항 감지 시 git add → commit → pull --rebase → push"""
    try:
        # 변경사항 있는지 먼저 확인
        diff = subprocess.run(
            ["git", "diff", "--quiet", WATCH_FILE],
            cwd=REPO_DIR,
        )
        if diff.returncode == 0:
            logging.info("변경사항 없음 - push 생략")
            return

        commit_msg = f"update: Wrap_NAV.xlsx ({datetime.now().strftime('%Y-%m-%d %H:%M')})"

        # git add
        subprocess.run(["git", "add", WATCH_FILE], cwd=REPO_DIR, check=True)
        logging.info(f"git add {WATCH_FILE}")

        # git commit
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logging.error(f"commit 실패: {result.stderr}")
            return
        logging.info(f"commit: {commit_msg}")

        # git pull --rebase
        subprocess.run(
            ["git", "pull", "--rebase", "origin", "main"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )

        # git push
        push = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if push.returncode == 0:
            logging.info("✅ GitHub push 성공")
        else:
            logging.error(f"❌ push 실패: {push.stderr}")

    except Exception as e:
        logging.error(f"오류: {e}")


class WrapNavHandler(FileSystemEventHandler):
    def __init__(self):
        self._last_trigger = 0

    def on_modified(self, event):
        if os.path.basename(event.src_path) != WATCH_FILE:
            return
        # 임시 파일(~$) 무시
        if os.path.basename(event.src_path).startswith("~$"):
            return

        now = time.time()
        # 디바운스: 마지막 이벤트 후 DEBOUNCE_SECONDS 이내면 무시
        if now - self._last_trigger < DEBOUNCE_SECONDS:
            return
        self._last_trigger = now

        logging.info(f"변경 감지: {WATCH_FILE} → {DEBOUNCE_SECONDS}초 후 push")
        time.sleep(DEBOUNCE_SECONDS)
        git_push()


if __name__ == "__main__":
    logging.info(f"=== Wrap_NAV 감시 시작 ===")
    logging.info(f"감시 경로: {os.path.join(REPO_DIR, WATCH_FILE)}")

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
