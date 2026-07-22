# -*- coding: utf-8 -*-
"""기존 Notion 분석 페이지 → 맥미니 datalake md 백필 (2026-07-22 사용자 결정).

Universe Earnings DB의 전체 페이지에서 1-page 분석 본문(컨퍼런스콜 전문 섹션
이전까지)을 추출해 ~/datalake/analyses/YYYY/YYYY-MM-DD_TICKER_<acc6>.md 로
저장한다. Notion 페이지는 동결 아카이브로 유지(삭제·수정 안 함).
전문(transcript)은 이미 transcripts/ 에 있으므로 제외.

사용: venv/bin/python3 -m execution.earnings_bot.backfill_analyses_md [--force] [--dry-run] [--limit N]
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

DATALAKE_ROOT = os.path.expanduser(os.getenv("DATALAKE_ROOT", "~/datalake"))
ANALYSES_DIR = os.path.join(DATALAKE_ROOT, "analyses")
TRANSCRIPT_MARKER = "컨퍼런스콜 전문"
API = "https://api.notion.com/v1"
PACE_SEC = 0.35  # Notion 3req/s 제한


class NotionHTTP:
    """notion_publisher와 동일한 raw HTTP 방식 (SDK 버전 비의존)."""

    def __init__(self, key):
        self.h = {"Authorization": f"Bearer {key}", "Notion-Version": "2022-06-28",
                  "Content-Type": "application/json"}

    def _req(self, url, body=None, method="GET"):
        time.sleep(PACE_SEC)
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                     headers=self.h, method=method)
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))

    def query_db(self, dbid, cursor=None):
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        return self._req(f"{API}/databases/{dbid}/query", body, "POST")

    def children(self, block_id, cursor=None):
        qs = "page_size=100" + (f"&start_cursor={urllib.parse.quote(cursor)}" if cursor else "")
        return self._req(f"{API}/blocks/{block_id}/children?{qs}")


def _rt_text(rich):
    out = []
    for r in rich or []:
        t = r.get("plain_text", "")
        ann = r.get("annotations", {})
        if ann.get("code"):
            t = f"`{t}`"
        if ann.get("bold"):
            t = f"**{t}**"
        out.append(t)
    return "".join(out)


def _prop_text(p):
    if not p:
        return ""
    t = p.get("type")
    if t == "title":
        return _rt_text(p["title"])
    if t == "rich_text":
        return _rt_text(p["rich_text"])
    if t == "select":
        return (p["select"] or {}).get("name", "")
    if t == "date":
        return ((p["date"] or {}).get("start") or "")[:10]
    if t == "url":
        return p["url"] or ""
    return ""


def _iter_blocks(cli, block_id):
    cursor = None
    while True:
        resp = cli.children(block_id, cursor)
        yield from resp.get("results", [])
        if not resp.get("has_more"):
            return
        cursor = resp.get("next_cursor")


def _block_md(cli, b):
    t = b.get("type")
    d = b.get(t) or {}
    rt = _rt_text(d.get("rich_text"))
    if t == "paragraph":
        return rt
    if t in ("heading_1", "heading_2", "heading_3"):
        return f"{'#' * int(t[-1])} {rt}"
    if t == "bulleted_list_item":
        return f"- {rt}"
    if t == "numbered_list_item":
        return f"1. {rt}"
    if t == "quote":
        return f"> {rt}"
    if t == "callout":
        return f"> {rt}"
    if t == "divider":
        return "---"
    if t == "toggle":
        return rt
    if t == "code":
        return f"```\n{rt}\n```"
    if t == "table":
        rows = []
        for i, row in enumerate(_iter_blocks(cli, b["id"])):
            # cell 자체가 rich_text 리스트 — _rt_text에 통째로 전달
            cells = [_rt_text(cell) for cell in (row.get("table_row") or {}).get("cells", [])]
            cells = [c.replace("|", "\\|").replace("\n", " ") for c in cells]
            rows.append("| " + " | ".join(cells) + " |")
            if i == 0:
                rows.append("|" + "---|" * len(cells))
        return "\n".join(rows)
    return ""


def page_to_md(cli, page):
    props = page.get("properties", {})
    meta = {
        "title": _prop_text(props.get("이름")),
        "ticker": _prop_text(props.get("Ticker")),
        "quarter": _prop_text(props.get("Quarter")),
        "type": _prop_text(props.get("Type")),
        "severity": _prop_text(props.get("Severity")),
        "accession": _prop_text(props.get("Accession")),
        "date": _prop_text(props.get("Filed Date")) or (page.get("created_time") or "")[:10],
        "source_url": _prop_text(props.get("Source URL")),
        "notion_page_id": page["id"],
    }
    lines = []
    for b in _iter_blocks(cli, page["id"]):
        t = b.get("type")
        d = b.get(t) or {}
        if t in ("heading_1", "heading_2", "heading_3") and TRANSCRIPT_MARKER in _rt_text(d.get("rich_text")):
            break  # 전문 섹션부터는 transcripts/ md가 정본 — 제외
        md = _block_md(cli, b)
        lines.append(md)
    body = "\n\n".join(x for x in lines if x is not None)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    fm = "\n".join(f'{k}: "{v}"' for k, v in meta.items() if v)
    return meta, f"---\n{fm}\n---\n\n{body}\n"


def out_path(meta):
    date = meta["date"] or "0000-00-00"
    acc6 = re.sub(r"\D", "", meta.get("accession", ""))[-6:] or "000000"
    ticker = meta.get("ticker") or "UNKNOWN"
    return os.path.join(ANALYSES_DIR, date[:4], f"{date}_{ticker}_{acc6}.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    key = os.getenv("NOTION_EARNINGS_API_KEY")
    dbid = os.getenv("NOTION_EARNINGS_DATABASE_ID")
    if not (key and dbid):
        print("ERROR: NOTION_EARNINGS_API_KEY / NOTION_EARNINGS_DATABASE_ID 필요")
        return 1
    cli = NotionHTTP(key)

    pages, cursor = [], None
    while True:
        resp = cli.query_db(dbid, cursor)
        pages += resp.get("results", [])
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    print(f"Notion 페이지 {len(pages)}건")

    saved = skipped = failed = 0
    for i, page in enumerate(pages):
        if args.limit and saved >= args.limit:
            break
        try:
            meta, md = page_to_md(cli, page)
            path = out_path(meta)
            if os.path.exists(path) and not args.force:
                skipped += 1
                continue
            print(f"  [{i+1}/{len(pages)}] {meta['title']} → {os.path.relpath(path, DATALAKE_ROOT)}"
                  f" ({len(md):,}자){' [dry]' if args.dry_run else ''}", flush=True)
            if not args.dry_run:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(md)
                os.replace(tmp, path)
            saved += 1
        except Exception as e:
            failed += 1
            print(f"  ✗ {page.get('id')}: {type(e).__name__}: {e}", flush=True)
    print(f"완료: 저장 {saved} / 스킵 {skipped} / 실패 {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
