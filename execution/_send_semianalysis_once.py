"""SemiAnalysis 신규 글 1회 수동 발송 (봇 _run_source_job 로직 복제).

ra-sisyphe-bot 의 정규 발송과 동일: fetch_new_posts(번역) → format_message →
split_for_telegram → 구독자 전송 → commit_state. cron(09:00/21:00 KST)을
기다리지 않고 즉시 보낼 때 사용.

사용법 (VM):
    cd /home/ubuntu/Antigravity_Market_Dashboard
    set -a && . ./.env && set +a
    PYTHONIOENCODING=utf-8 python3 execution/_send_semianalysis_once.py

state 에 없는 글만 발송하고, 성공 후 commit_state 로 GUID 적재하므로
다음 cron 에서 중복 발송되지 않음. 봇 재시작 불필요 (state 파일만 갱신).
"""
import os
import sys
import json
import time

REPO = "/home/ubuntu/Antigravity_Market_Dashboard"
sys.path.insert(0, os.path.join(REPO, "execution"))

import requests

from sources import semianalysis as adapter
from sources.base import split_for_telegram

LABEL = "SemiAnalysis"
ICON = "📊"


def _load_env_token() -> str:
    token = os.getenv("TELEGRAM_RA_SISYPHE_BOT_TOKEN")
    if token:
        return token
    with open(os.path.join(REPO, ".env"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("TELEGRAM_RA_SISYPHE_BOT_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("TELEGRAM_RA_SISYPHE_BOT_TOKEN not found")


def _load_subscribers() -> list:
    with open(os.path.join(REPO, "subscribers_ra_sisyphe.json"), encoding="utf-8") as f:
        d = json.load(f)
    return d if isinstance(d, list) else list(d.keys())


def main():
    token = _load_env_token()
    subs = _load_subscribers()
    api = f"https://api.telegram.org/bot{token}/sendMessage"

    posts = adapter.fetch_new_posts(update_state=False)
    print(f"new posts: {len(posts)}")
    if not posts:
        print("아무 신규 글 없음 — 종료")
        return

    send_errors = []
    for p in posts:
        full = adapter.format_message(p, LABEL, ICON)
        print(f"  -> {p['title'][:60]} ({len(full)} chars)")
        for chat_id in subs:
            for chunk in split_for_telegram(full, 4000):
                r = requests.post(api, data={
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": "true",
                }, timeout=30)
                if not r.ok:
                    send_errors.append(f"chat={chat_id}: {r.status_code} {r.text[:200]}")
                    print(f"    FAIL chat={chat_id}: {r.status_code} {r.text[:200]}")
                time.sleep(0.5)  # rate limit 여유

    if send_errors:
        print(f"전송 실패 {len(send_errors)}건 — state 미커밋")
        sys.exit(1)

    adapter.commit_state(posts)
    print(f"SENT {len(posts)}건, state committed")


if __name__ == "__main__":
    main()
