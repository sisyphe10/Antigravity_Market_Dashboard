# -*- coding: utf-8 -*-
"""Research Notes 원문 텔레그램 메시지 → 일별 .md 아카이브.

소스: execution/research_bot/research_notes.db (messages 테이블 — 원문 텍스트·URL·
스크랩 기사본문·전달출처·미디어 경로 전부 보존돼 있음).
출력: ~/datalake/research_notes/YYYY/YYYY-MM-DD.md + media/YYYY-MM-DD/ 사본.

- 일 단위 멱등: 해당 날짜 파일을 통째로 재생성 (부분 append 없음)
- 기본 실행 = 어제+오늘 재생성 (23:20 타이머 — 23:00 요약 후 도착분도 다음 실행이 회수)
- --all = DB 전 기간 백필, --date YYYY-MM-DD = 특정일

사용:
  python3 datalake/export_research_notes.py            # 어제+오늘
  python3 datalake/export_research_notes.py --all      # 전량 백필
  python3 datalake/export_research_notes.py --date 2026-07-01
"""
import argparse
import os
import shutil
import sqlite3
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dl_common import NOTES_DIR, REPO

DB_PATH = os.path.join(REPO, "execution", "research_bot", "research_notes.db")
MEDIA_OUT = os.path.join(NOTES_DIR, "media")

TYPE_LABEL = {"text": "텍스트", "photo": "사진", "document": "파일"}


def fetch_dates(conn):
    rows = conn.execute("SELECT DISTINCT substr(timestamp,1,10) d FROM messages ORDER BY d").fetchall()
    return [r[0] for r in rows]


def fetch_messages(conn, day):
    rows = conn.execute(
        "SELECT * FROM messages WHERE timestamp LIKE ? ORDER BY timestamp, id",
        (day + "%",),
    ).fetchall()
    return [dict(r) for r in rows]


def resolve_media_path(src):
    """DB에 저장된 media 절대경로 해석. VM 시절 경로(/home/ubuntu/...)는
    'research_bot/' 이후 상대경로를 현재 레포 기준으로 재구성한다."""
    if not src:
        return None
    if os.path.exists(src):
        return src
    marker = "research_bot" + ("/" if "/" in src else os.sep)
    idx = src.find(marker)
    if idx >= 0:
        rel = src[idx + len(marker):].replace("/", os.sep)
        cand = os.path.join(REPO, "execution", "research_bot", rel)
        if os.path.exists(cand):
            return cand
    return None


def copy_media(msg, day):
    """봇 media 파일을 datalake로 복사, md에서 쓸 상대경로 반환 (없으면 None)."""
    src = resolve_media_path(msg.get("media_path"))
    if not src:
        return None
    dst_dir = os.path.join(MEDIA_OUT, day)
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, os.path.basename(src))
    if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
        shutil.copy2(src, dst)
    return f"../media/{day}/{os.path.basename(src)}"


def render_day(day, messages):
    lines = [
        "---",
        f"date: {day}",
        f"count: {len(messages)}",
    ]
    sources = sorted({m["forward_source"] for m in messages if m.get("forward_source")})
    if sources:
        lines.append("sources: [" + ", ".join(f'"{s}"' for s in sources) + "]")
    lines += ["---", "", f"# Research Notes 원문 — {day}", ""]

    for i, m in enumerate(messages, 1):
        ts = m["timestamp"][11:16] if len(m.get("timestamp", "")) >= 16 else ""
        head = f"## [{i}] {ts} · {TYPE_LABEL.get(m.get('message_type'), m.get('message_type'))}"
        if m.get("forward_source"):
            head += f" · 전달: {m['forward_source']}"
        lines.append(head)
        lines.append("")
        if m.get("text_content"):
            lines.append(m["text_content"].strip())
            lines.append("")
        if m.get("url"):
            lines.append(f"링크: {m['url']}")
            lines.append("")
        rel = copy_media(m, day)
        if rel:
            lines.append(f"첨부: [{os.path.basename(rel)}]({rel})")
            lines.append("")
        if m.get("article_content"):
            lines.append("<details><summary>기사 본문</summary>")
            lines.append("")
            lines.append(m["article_content"].strip())
            lines.append("")
            lines.append("</details>")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def export_day(conn, day):
    messages = fetch_messages(conn, day)
    if not messages:
        return 0
    out_dir = os.path.join(NOTES_DIR, day[:4])
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{day}.md")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(render_day(day, messages))
    os.replace(tmp, path)
    return len(messages)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="DB 전 기간 백필")
    ap.add_argument("--date", help="특정일만 (YYYY-MM-DD)")
    args = ap.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB 없음 — {DB_PATH}")
        return 1
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    if args.all:
        days = fetch_dates(conn)
    elif args.date:
        datetime.strptime(args.date, "%Y-%m-%d")
        days = [args.date]
    else:
        today = date.today()
        days = [(today - timedelta(days=1)).isoformat(), today.isoformat()]

    total_msgs = written = 0
    for day in days:
        n = export_day(conn, day)
        if n:
            written += 1
            total_msgs += n
    conn.close()
    print(f"완료: {written}일 / 메시지 {total_msgs}건 → {NOTES_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
