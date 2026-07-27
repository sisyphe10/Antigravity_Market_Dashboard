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
import json
import os
import shutil
import sqlite3
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dl_common import NOTES_DIR, REPO

DB_PATH = os.path.join(REPO, "execution", "research_bot", "research_notes.db")
MEDIA_OUT = os.path.join(NOTES_DIR, "media")
# 태그 캐시 (datalake/tagging/tag_worker.py 가 만든다). 없으면 태그 없이 생성.
TAG_DB = os.path.join(NOTES_DIR, "tag_state.sqlite")
TAG_SCHEMA_VERSION = 1

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
    """봇 media 파일을 datalake로 복사, md에서 쓸 상대경로 반환 (없으면 None).

    문서 첨부는 원본 파일명이라 같은 날 basename 충돌 가능 → 메시지 id를
    prefix로 붙여 유일화한다.
    """
    src = resolve_media_path(msg.get("media_path"))
    if not src:
        return None
    uid = msg.get("telegram_message_id") or msg.get("id") or "0"
    fname = f"{uid}_{os.path.basename(src)}"
    dst_dir = os.path.join(MEDIA_OUT, day)
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, fname)
    if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
        shutil.copy2(src, dst)
    return f"../media/{day}/{fname}"


def _yaml_list(values):
    """YAML flow sequence 를 JSON 배열로 직렬화.

    직접 따옴표를 붙이면 '식품,음료,담배' 같은 값이 세 원소로 파싱된다.
    JSON 배열은 유효한 YAML flow sequence 이므로 이스케이프가 안전하다.
    """
    return json.dumps(values, ensure_ascii=False)


def load_tags(day):
    """해당 날짜 메시지들의 태그를 캐시에서 읽는다 (LLM 호출 없음).

    반환: {message_id: {"themes": [label…], "entities": [(id, name, sector, role)…]}}
    캐시가 없거나 읽기에 실패하면 빈 dict — 태그 없이 기존과 동일하게 렌더링한다.
    """
    if not os.path.exists(TAG_DB):
        return {}
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tagging"))
        import tagging_common as tc
        onto = tc.load_ontology()
        uni = tc.load_universe()
        extra = tc.load_entities_extra()
        conn = sqlite3.connect("file:%s?mode=ro" % TAG_DB, uri=True)
        conn.row_factory = sqlite3.Row
    except Exception as e:  # noqa: BLE001
        print("  (태그 캐시 사용 안 함: %s)" % str(e)[:120])
        return {}

    out = {}
    try:
        # 태깅에 성공했지만 테마·개체가 하나도 안 붙은 메시지(이미지만 있는 항목 등)도
        # '처리 완료'다. 빈 엔트리를 먼저 깔아야 tag_status 가 partial 로 오판되지 않는다.
        for r in conn.execute("SELECT message_id FROM items WHERE day=? AND status='succeeded'",
                              (day,)):
            out[r["message_id"]] = {"themes": [], "entities": []}
        rows = conn.execute(
            "SELECT t.message_id, t.theme_id, t.rank FROM theme_assignments t"
            " JOIN items i ON i.message_id=t.message_id"
            " WHERE i.day=? AND i.status='succeeded'"
            " ORDER BY t.rank DESC, t.theme_id", (day,)).fetchall()
        for r in rows:
            meta = onto["themes"].get(r["theme_id"])
            label = (meta or {}).get("label") or r["theme_id"]
            out.setdefault(r["message_id"], {"themes": [], "entities": []})
            if label not in out[r["message_id"]]["themes"]:
                out[r["message_id"]]["themes"].append(label)

        rows = conn.execute(
            "SELECT DISTINCT e.message_id, e.entity_id, e.role FROM entity_occurrences e"
            " JOIN items i ON i.message_id=e.message_id"
            " WHERE i.day=? AND i.status='succeeded'"
            " ORDER BY e.entity_id", (day,)).fetchall()
        for r in rows:
            u = uni["rows"].get(r["entity_id"])
            x = extra["rows"].get(r["entity_id"])
            name = (u or {}).get("name") or (x or {}).get("label_ko") or r["entity_id"]
            sector = (u or {}).get("sector", "")
            out.setdefault(r["message_id"], {"themes": [], "entities": []})
            ent = (r["entity_id"], name, sector, r["role"])
            if ent not in out[r["message_id"]]["entities"]:
                out[r["message_id"]]["entities"].append(ent)
    finally:
        conn.close()
    return out


def _item_tag_line(tag):
    """항목 바로 아래에 붙는 사람이 읽는 태그 줄."""
    parts = []
    if tag.get("themes"):
        parts.append(" ".join("#" + t.replace(" ", "") for t in tag["themes"]))
    subjects = [e for e in tag.get("entities", []) if e[3] == "subject"]
    if subjects:
        parts.append("종목·기관: " + ", ".join(
            "%s(%s)" % (name, eid) for eid, name, _sec, _r in subjects))
    sources = [e for e in tag.get("entities", []) if e[3] == "source"]
    if sources:
        parts.append("출처: " + ", ".join(name for _e, name, _s, _r in sources))
    return " · ".join(parts)


def render_day(day, messages, tags=None):
    lines = [
        "---",
        f"date: {day}",
        f"count: {len(messages)}",
    ]
    sources = sorted({m["forward_source"] for m in messages if m.get("forward_source")})
    if sources:
        lines.append("sources: " + _yaml_list(sources))

    tags = tags or {}
    if tags:
        themes, tickers, sectors, orgs, people = set(), set(), set(), set(), set()
        for m in messages:
            t = tags.get(m["id"])
            if not t:
                continue
            themes.update(t["themes"])
            for eid, name, sector, role in t["entities"]:
                if role != "subject":
                    continue
                if eid.startswith("inst:"):
                    orgs.add(name)
                elif eid.startswith("person:"):
                    people.add(name)
                elif eid.startswith("private:"):
                    orgs.add(name)
                else:
                    tickers.add(eid)
                    if sector:
                        sectors.add(sector)
        covered = sum(1 for m in messages if m["id"] in tags)
        lines.append("themes: " + _yaml_list(sorted(themes)))
        lines.append("tickers: " + _yaml_list(sorted(tickers)))
        lines.append("sectors: " + _yaml_list(sorted(sectors)))
        lines.append("orgs: " + _yaml_list(sorted(orgs)))
        lines.append("people: " + _yaml_list(sorted(people)))
        lines.append("tag_schema_version: %d" % TAG_SCHEMA_VERSION)
        lines.append("tag_status: %s" % ("complete" if covered == len(messages) else "partial"))
    lines += ["---", "", f"# Research Notes 원문 — {day}", ""]

    for i, m in enumerate(messages, 1):
        ts = m["timestamp"][11:16] if len(m.get("timestamp", "")) >= 16 else ""
        head = f"## [{i}] {ts} · {TYPE_LABEL.get(m.get('message_type'), m.get('message_type'))}"
        if m.get("forward_source"):
            head += f" · 전달: {m['forward_source']}"
        lines.append(head)
        # [n] 은 날짜 내 정렬 순번이라 늦게 도착한 메시지로 바뀔 수 있다.
        # 안정 식별자는 이 주석 (캐시·수정의 기준 키).
        lines.append("<!-- rn-id: %s -->" % m["id"])
        tag = tags.get(m["id"]) if tags else None
        if tag:
            tag_line = _item_tag_line(tag)
            if tag_line:
                lines.append(tag_line)
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
        f.write(render_day(day, messages, load_tags(day)))
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
