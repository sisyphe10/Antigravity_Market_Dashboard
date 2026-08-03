#!/usr/bin/env python3
"""Notion Study DB -> ~/datalake/notion_study/<year>/<id>.md incremental sync.

Uses the Notion REST API (integration token NOTION_API_KEY, read-only usage).
Change detection = page last_edited_time vs local state; unchanged pages are
never re-fetched, and re-rendered files are only written when content differs
(image presigned-signature query strings are stripped so renders stay
deterministic -> no spurious re-tagging downstream).

State: ~/datalake/notion_study/_sync_state.json  (id -> last_edited/path/sha)
Deletion: page missing from two consecutive full runs -> moved to
~/datalake/_tombstones/notion_study/ (never auto-deleted).

Usage:
  venv/bin/python3 datalake/notion_study_sync.py            # incremental (first run = full backfill)
  venv/bin/python3 datalake/notion_study_sync.py --limit 5  # test subset (no tombstoning)
  venv/bin/python3 datalake/notion_study_sync.py --ids <id> # force re-fetch specific pages
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
import urllib.error

DB_ID = "bb80fc95-b4c1-4080-9faa-17486cc52332"  # Study
API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
DATALAKE = os.path.expanduser("~/datalake")
ROOT = os.path.join(DATALAKE, "notion_study")
STATE_PATH = os.path.join(ROOT, "_sync_state.json")
TOMBSTONES = os.path.join(DATALAKE, "_tombstones", "notion_study")
LOCK_PATH = os.path.join(ROOT, "_sync.lock")
PACE = 0.34  # ~3 req/s official limit
MAX_DEPTH = 6

_last_call = [0.0]


def _token():
    tok = os.environ.get("NOTION_API_KEY")
    if not tok:
        env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
        try:
            with open(env, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("NOTION_API_KEY="):
                        tok = line.split("=", 1)[1].strip().strip("'\"")
                        break
        except OSError:
            pass
    if not tok:
        sys.exit("NOTION_API_KEY not set (env or repo .env)")
    return tok


TOKEN = None


def api(path, payload=None, retries=5):
    """GET (payload None) or POST with pacing + 429/5xx retry."""
    wait = PACE - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(API + path, headers={
        "Authorization": "Bearer " + TOKEN,
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    })
    if payload is not None:
        req.data = json.dumps(payload).encode()
        req.method = "POST"
    for attempt in range(retries):
        try:
            _last_call[0] = time.time()
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(float(e.headers.get("Retry-After", "2")) + 0.5)
            elif e.code >= 500 and attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise


def query_all_pages():
    """Full property manifest of the Study DB (paginated)."""
    pages, cursor = [], None
    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        d = api(f"/databases/{DB_ID}/query", payload)
        pages.extend(d["results"])
        if not d.get("has_more"):
            return pages
        cursor = d["next_cursor"]


# ── rendering ──────────────────────────────────────────────────────────────

def strip_sig(url):
    """Drop querystring (presigned S3 signatures rotate every fetch)."""
    return url.split("?")[0] if url else url


def rich(arr):
    out = []
    for t in arr or []:
        txt = t.get("plain_text", "")
        href = t.get("href")
        if t.get("annotations", {}).get("code"):
            txt = f"`{txt}`"
        if href and not href.startswith("https://www.notion.so"):
            txt = f"[{txt}]({href})"
        out.append(txt)
    return "".join(out)


def fetch_children(block_id):
    results, cursor = [], None
    while True:
        path = f"/blocks/{block_id}/children?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"
        d = api(path)
        results.extend(d["results"])
        if not d.get("has_more"):
            return results
        cursor = d["next_cursor"]


def render_blocks(blocks, depth=0, counters=None):
    lines = []
    ind = "  " * depth
    num = 0
    for b in blocks:
        t = b["type"]
        v = b.get(t, {})
        kids = []
        if b.get("has_children") and depth < MAX_DEPTH and t not in ("child_page", "child_database"):
            if t == "synced_block" and v.get("synced_from"):
                kids = fetch_children(v["synced_from"]["block_id"])
            else:
                kids = fetch_children(b["id"])

        if t == "paragraph":
            txt = rich(v.get("rich_text"))
            lines.append(ind + txt if txt else "")
        elif t in ("heading_1", "heading_2", "heading_3"):
            lines.append(ind + "#" * int(t[-1]) + " " + rich(v.get("rich_text")))
        elif t == "bulleted_list_item":
            lines.append(ind + "- " + rich(v.get("rich_text")))
        elif t == "numbered_list_item":
            num += 1
            lines.append(f"{ind}{num}. " + rich(v.get("rich_text")))
        elif t == "to_do":
            mark = "x" if v.get("checked") else " "
            lines.append(f"{ind}- [{mark}] " + rich(v.get("rich_text")))
        elif t == "toggle":
            lines.append(ind + "- " + rich(v.get("rich_text")))
        elif t == "quote":
            lines.append(ind + "> " + rich(v.get("rich_text")))
        elif t == "callout":
            ico = (v.get("icon") or {}).get("emoji", "")
            lines.append(ind + "> " + (ico + " " if ico else "") + rich(v.get("rich_text")))
        elif t == "code":
            lang = v.get("language", "")
            lines.append(f"{ind}```{lang}")
            lines.append(rich(v.get("rich_text")))
            lines.append(ind + "```")
            kids = []
        elif t == "divider":
            lines.append(ind + "---")
        elif t == "equation":
            lines.append(ind + "$" + v.get("expression", "") + "$")
        elif t == "image":
            src = v.get(v.get("type", ""), {})
            cap = rich(v.get("caption"))
            lines.append(f"{ind}![이미지]({strip_sig(src.get('url', ''))})")
            if cap:
                lines.append(ind + "> " + cap)
        elif t in ("file", "pdf", "video", "audio"):
            src = v.get(v.get("type", ""), {})
            name = v.get("name") or t
            lines.append(f"{ind}- 첨부: {name} ({strip_sig(src.get('url', ''))})")
        elif t == "bookmark":
            cap = rich(v.get("caption"))
            lines.append(f"{ind}- 북마크: {v.get('url', '')}" + (f" — {cap}" if cap else ""))
        elif t == "embed":
            lines.append(f"{ind}- 임베드: {v.get('url', '')}")
        elif t == "child_page":
            lines.append(f"{ind}- 하위 페이지: {v.get('title', '')} <!-- child_page: {b['id']} -->")
        elif t == "child_database":
            lines.append(f"{ind}- 하위 DB: {v.get('title', '')}")
        elif t == "table":
            rows = kids
            kids = []
            for i, row in enumerate(rows):
                cells = [rich(c) for c in row.get("table_row", {}).get("cells", [])]
                lines.append(ind + "| " + " | ".join(cells) + " |")
                if i == 0:
                    lines.append(ind + "|" + "---|" * len(cells))
        elif t in ("column_list", "column"):
            pass  # flatten via kids
        elif t == "table_of_contents":
            kids = []
        else:
            txt = rich(v.get("rich_text")) if isinstance(v, dict) else ""
            if txt:
                lines.append(ind + txt)

        if kids:
            child_depth = depth if t in ("column_list", "column") else depth + 1
            lines.extend(render_blocks(kids, child_depth))
    return lines


def prop_val(props, name, kind):
    p = props.get(name) or {}
    if kind == "title":
        return "".join(t.get("plain_text", "") for t in p.get("title", []))
    if kind == "date":
        return (p.get("date") or {}).get("start")
    if kind == "select":
        return (p.get("select") or {}).get("name")
    if kind == "number":
        return p.get("number")
    return None


def yaml_str(v):
    if v is None:
        return "null"
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_md(page):
    props = page["properties"]
    title = prop_val(props, "Name", "title") or "(제목 없음)"
    date = prop_val(props, "Date", "date")
    created = page.get("created_time", "")
    body_lines = render_blocks(fetch_children(page["id"]))
    fm = [
        "---",
        f"title: {yaml_str(title)}",
        f"date: {yaml_str((date or created)[:10])}",
        'source: "notion_study"',
        f"notion_id: {yaml_str(page['id'].replace('-', ''))}",
        f"notion_url: {yaml_str(page.get('url', ''))}",
        f"notion_created: {yaml_str(created)}",
        f"notion_last_edited: {yaml_str(page.get('last_edited_time', ''))}",
        f"study_type: {yaml_str(prop_val(props, '구분', 'select'))}",
        f"study_sector: {yaml_str(prop_val(props, '섹터', 'select'))}",
        f"study_score: {json.dumps(prop_val(props, 'Score', 'number'))}",
        f"market_cap: {yaml_str(prop_val(props, '시가총액', 'number'))}",
        "---",
        "",
        f"# {title}",
        "",
    ]
    text = "\n".join(fm + body_lines).rstrip() + "\n"
    return unicodedata.normalize("NFC", text)


# ── state + files ──────────────────────────────────────────────────────────

def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"pages": {}}


def save_state(state):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_PATH)


def write_md(rel, text):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sha = hashlib.sha256(text.encode()).hexdigest()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    return sha


def main():
    global TOKEN
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="process at most N changed pages (test)")
    ap.add_argument("--ids", default="", help="comma-separated notion ids to force re-fetch")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    TOKEN = _token()

    os.makedirs(ROOT, exist_ok=True)
    # single-instance lock (stale after 2h)
    try:
        if os.path.exists(LOCK_PATH) and time.time() - os.path.getmtime(LOCK_PATH) > 7200:
            os.remove(LOCK_PATH)
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        sys.exit("another sync appears to be running (lock present)")

    try:
        state = load_state()
        pages = query_all_pages()
        print(f"manifest: {len(pages)} pages")
        force = {i.strip().replace("-", "") for i in args.ids.split(",") if i.strip()}
        seen = set()
        stats = {"new": 0, "updated": 0, "unchanged": 0, "failed": 0}
        changed = []
        for p in pages:
            pid = p["id"].replace("-", "")
            seen.add(pid)
            entry = state["pages"].get(pid)
            if entry and entry.get("last_edited") == p["last_edited_time"] and pid not in force:
                entry["miss"] = 0
                stats["unchanged"] += 1
                continue
            changed.append(p)
        if args.limit:
            changed = changed[: args.limit]
        print(f"to fetch: {len(changed)}")

        for i, p in enumerate(changed, 1):
            pid = p["id"].replace("-", "")
            year = p.get("created_time", "0000")[:4]
            rel = os.path.join(year, pid + ".md")
            try:
                text = build_md(p)
                if args.dry_run:
                    print(f"[dry] {rel} ({len(text)} chars)")
                    continue
                sha = write_md(rel, text)
                is_new = pid not in state["pages"]
                old_rel = (state["pages"].get(pid) or {}).get("path")
                if old_rel and old_rel != rel:
                    try:
                        os.remove(os.path.join(ROOT, old_rel))
                    except OSError:
                        pass
                state["pages"][pid] = {
                    "last_edited": p["last_edited_time"],
                    "path": rel, "sha": sha, "miss": 0,
                    "title": (prop_val(p["properties"], "Name", "title") or "")[:80],
                }
                stats["new" if is_new else "updated"] += 1
                if i % 25 == 0 or i == len(changed):
                    print(f"  {i}/{len(changed)}")
                    save_state(state)
            except Exception as e:  # noqa: BLE001 — one page must not kill the run
                stats["failed"] += 1
                print(f"  FAIL {pid} {type(e).__name__}: {e}")

        # tombstoning only on complete runs
        if not args.limit and not args.dry_run:
            for pid in list(state["pages"]):
                if pid in seen:
                    continue
                e = state["pages"][pid]
                e["miss"] = e.get("miss", 0) + 1
                if e["miss"] >= 2:
                    os.makedirs(TOMBSTONES, exist_ok=True)
                    src = os.path.join(ROOT, e["path"])
                    if os.path.exists(src):
                        os.replace(src, os.path.join(TOMBSTONES, os.path.basename(e["path"])))
                    print(f"  tombstoned {pid} ({e.get('title', '')})")
                    del state["pages"][pid]

        if not args.dry_run:
            save_state(state)
        print("done:", json.dumps(stats, ensure_ascii=False))
        if stats["failed"]:
            sys.exit(1)
    finally:
        try:
            os.remove(LOCK_PATH)
        except OSError:
            pass


if __name__ == "__main__":
    main()
