# -*- coding: utf-8 -*-
"""tag_state.sqlite → 연도별 parquet (DuckDB 뷰 등록용).

태그의 정본은 tag_state.sqlite 지만, 집계·검색은 데이터레이크의 다른 데이터셋과
같은 방식(연도별 parquet + build_catalog.py 가 만드는 DuckDB 뷰)으로 노출한다.
Markdown 의 태그는 사람이 읽는 투영일 뿐이고, 기계 질의는 여기를 본다.

생성 데이터셋 (market/<name>/<year>.parquet):
  research_items           메시지 1행 — 날짜·출처채널·유형·길이·테마 수
  research_item_themes     (메시지 × 테마) — rank/confidence/evidence
  research_entity_mentions (메시지 × 개체) — role/method/섹터/표면형

모든 테이블에 date 컬럼을 둔다 (build_catalog 의 기간 통계가 이를 사용).

사용:
  python3 datalake/tagging/export_tags_parquet.py
  python3 datalake/tagging/export_tags_parquet.py --year 2026
"""
import argparse
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import tagging_common as tc  # noqa: E402
from dl_common import DATALAKE_ROOT, dataset_lock, year_path  # noqa: E402

STATE_DB = os.path.join(DATALAKE_ROOT, "research_notes", "tag_state.sqlite")


def _entity_meta(universe, extra):
    meta = {}
    for tk, row in universe["rows"].items():
        meta[tk] = ("listed_company", row["name"], row["sector"])
    for eid, row in extra["rows"].items():
        meta[eid] = (row["type"], row["label_ko"], "")
    return meta


def build_frames(conn, onto, universe, extra):
    import pandas as pd

    meta = _entity_meta(universe, extra)
    src = sqlite3.connect(
        "file:%s?mode=ro" % os.path.join(
            os.path.dirname(os.path.dirname(HERE)), "execution", "research_bot",
            "research_notes.db"),
        uri=True)
    src.row_factory = sqlite3.Row
    msgs = {r["id"]: dict(r) for r in src.execute(
        "SELECT id,timestamp,message_type,forward_source,text_content,url FROM messages")}
    src.close()

    items, themes, ents = [], [], []
    theme_count = {}
    for r in conn.execute("SELECT message_id,theme_id,rank,confidence,evidence "
                          "FROM theme_assignments"):
        m = msgs.get(r["message_id"])
        if not m:
            continue
        t = onto["themes"].get(r["theme_id"])
        theme_count[r["message_id"]] = theme_count.get(r["message_id"], 0) + 1
        themes.append({
            "date": m["timestamp"][:10],
            "message_id": r["message_id"],
            "theme_id": r["theme_id"],
            "theme_parent": (t or {}).get("parent") or r["theme_id"].split(".")[0],
            "theme_label": (t or {}).get("label") or r["theme_id"],
            "rank": r["rank"],
            "confidence": r["confidence"],
            "evidence": r["evidence"],
        })

    for r in conn.execute("SELECT message_id,entity_id,field,span_start,surface,role,"
                          "method,confidence FROM entity_occurrences"):
        m = msgs.get(r["message_id"])
        if not m:
            continue
        kind, name, sector = meta.get(r["entity_id"], ("unknown", r["entity_id"], ""))
        ents.append({
            "date": m["timestamp"][:10],
            "message_id": r["message_id"],
            "entity_id": r["entity_id"],
            "entity_kind": kind,
            "entity_name": name,
            "sector": sector,
            "field": r["field"],
            "role": r["role"],
            "method": r["method"],
            "surface": r["surface"],
            "span_start": r["span_start"],
            "confidence": r["confidence"],
        })

    tagged = {r["message_id"] for r in conn.execute(
        "SELECT message_id FROM items WHERE status='succeeded'")}
    for mid in sorted(tagged):
        m = msgs.get(mid)
        if not m:
            continue
        items.append({
            "date": m["timestamp"][:10],
            "message_id": mid,
            "ts": m["timestamp"],
            "message_type": m["message_type"],
            "forward_source": m["forward_source"] or "",
            "has_url": bool(m["url"]),
            "text_len": len(m["text_content"] or ""),
            "theme_count": theme_count.get(mid, 0),
        })

    return {
        "research_items": pd.DataFrame(items),
        "research_item_themes": pd.DataFrame(themes),
        "research_entity_mentions": pd.DataFrame(ents),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int)
    args = ap.parse_args()

    onto = tc.load_ontology()
    uni = tc.load_universe()
    extra = tc.load_entities_extra()

    conn = sqlite3.connect("file:%s?mode=ro" % STATE_DB, uri=True)
    conn.row_factory = sqlite3.Row
    frames = build_frames(conn, onto, uni, extra)
    conn.close()

    total = 0
    for name, df in frames.items():
        if df.empty:
            print("%s: 0행 (건너뜀)" % name)
            continue
        df["year"] = df["date"].str[:4].astype(int)
        years = [args.year] if args.year else sorted(df["year"].unique())
        with dataset_lock(name):
            for y in years:
                part = df[df["year"] == y].drop(columns=["year"])
                if part.empty:
                    continue
                path = year_path(name, y)
                tmp = path + ".tmp"
                part.to_parquet(tmp, index=False)
                os.replace(tmp, path)
                total += len(part)
                print("%s/%d.parquet ← %d행" % (name, y, len(part)))
    print("완료: %d행" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
