# -*- coding: utf-8 -*-
"""월별 테마·섹터·종목 언급 추이 집계 → theme_trends.json.

단순 절대건수는 그날 수집량·채널 구성·같은 리포트 재전달에 그대로 오염된다.
그래서 세 지표를 함께 낸다.
  count          해당 테마가 붙은 메시지 수 (중복 제거)
  share          그 달 전체 태깅 메시지 대비 비중
  unique_sources 그 테마를 언급한 서로 다른 출처 채널 수

primary/secondary 를 나눠 담아, 차트 기본선은 primary(핵심 주제)로 그리고
secondary 는 탐색용으로 남긴다.

사용:
  python3 datalake/tagging/build_theme_trends.py
  python3 datalake/tagging/build_theme_trends.py --out /path/theme_trends.json
"""
import argparse
import collections
import datetime as dt
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import tagging_common as tc  # noqa: E402
from dl_common import DATALAKE_ROOT, REPO  # noqa: E402

STATE_DB = os.path.join(DATALAKE_ROOT, "research_notes", "tag_state.sqlite")
SRC_DB = os.path.join(REPO, "execution", "research_bot", "research_notes.db")
OUT_DEFAULT = os.path.join(DATALAKE_ROOT, "research_notes", "theme_trends.json")

MIN_TOTAL_FOR_SHARE = 5  # 표본이 너무 적은 달은 비중을 내지 않는다


def month_of(day):
    return day[:7]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--top-entities", type=int, default=40)
    args = ap.parse_args()

    onto = tc.load_ontology()
    uni = tc.load_universe()
    extra = tc.load_entities_extra()

    st = sqlite3.connect("file:%s?mode=ro" % STATE_DB, uri=True)
    st.row_factory = sqlite3.Row
    src = sqlite3.connect("file:%s?mode=ro" % SRC_DB, uri=True)
    src.row_factory = sqlite3.Row

    source_of = {r["id"]: (r["forward_source"] or "(직접)")
                 for r in src.execute("SELECT id,forward_source FROM messages")}
    src.close()

    day_of = {}
    month_total = collections.Counter()
    for r in st.execute("SELECT message_id,day FROM items WHERE status='succeeded'"):
        day_of[r["message_id"]] = r["day"]
        month_total[month_of(r["day"])] += 1
    if not month_total:
        raise SystemExit("태깅된 메시지가 없습니다 — tag_worker.py 를 먼저 실행하세요.")

    months = sorted(month_total)

    cnt = collections.defaultdict(collections.Counter)         # theme → month → n
    cnt_primary = collections.defaultdict(collections.Counter)
    srcs = collections.defaultdict(lambda: collections.defaultdict(set))
    for r in st.execute("SELECT message_id,theme_id,rank FROM theme_assignments"):
        d = day_of.get(r["message_id"])
        if not d:
            continue
        m = month_of(d)
        cnt[r["theme_id"]][m] += 1
        if r["rank"] == "primary":
            cnt_primary[r["theme_id"]][m] += 1
        srcs[r["theme_id"]][m].add(source_of.get(r["message_id"], ""))

    themes = []
    for tid in onto["order"]:
        meta = onto["themes"][tid]
        if meta.get("parent") is None or tid not in cnt:
            continue
        total = sum(cnt[tid].values())
        themes.append({
            "id": tid,
            "label": meta["label"],
            "parent": meta["parent"],
            "total": total,
            "count": {m: cnt[tid].get(m, 0) for m in months},
            "primary": {m: cnt_primary[tid].get(m, 0) for m in months},
            "share": {m: (round(cnt[tid].get(m, 0) / month_total[m] * 100, 1)
                          if month_total[m] >= MIN_TOTAL_FOR_SHARE else None)
                      for m in months},
            "unique_sources": {m: len(srcs[tid].get(m, ())) for m in months},
        })
    themes.sort(key=lambda t: -t["total"])

    # 대분류 롤업
    parents = collections.defaultdict(collections.Counter)
    for t in themes:
        for m, v in t["count"].items():
            parents[t["parent"]][m] += v
    parent_rows = [{
        "id": p,
        "label": onto["themes"].get(p, {}).get("label", p),
        "total": sum(c.values()),
        "count": {m: c.get(m, 0) for m in months},
    } for p, c in parents.items()]
    parent_rows.sort(key=lambda r: -r["total"])

    # 섹터·종목 (subject 로 승인된 상장 종목만)
    sec = collections.defaultdict(collections.Counter)
    ent = collections.defaultdict(collections.Counter)
    for r in st.execute("SELECT DISTINCT message_id,entity_id FROM entity_occurrences "
                        "WHERE role='subject'"):
        d = day_of.get(r["message_id"])
        if not d:
            continue
        m = month_of(d)
        meta = uni["rows"].get(r["entity_id"])
        if meta:
            sec[meta["sector"]][m] += 1
        ent[r["entity_id"]][m] += 1
    st.close()

    sector_rows = [{"label": s, "total": sum(c.values()),
                    "count": {m: c.get(m, 0) for m in months}}
                   for s, c in sec.items()]
    sector_rows.sort(key=lambda r: -r["total"])

    def ent_name(eid):
        u = uni["rows"].get(eid)
        x = extra["rows"].get(eid)
        return (u or {}).get("name") or (x or {}).get("label_ko") or eid

    entity_rows = [{"id": e, "label": ent_name(e),
                    "sector": uni["rows"].get(e, {}).get("sector", ""),
                    "total": sum(c.values()),
                    "count": {m: c.get(m, 0) for m in months}}
                   for e, c in ent.items()]
    entity_rows.sort(key=lambda r: -r["total"])
    entity_rows = entity_rows[:args.top_entities]

    out = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "ontology_version": onto["version"],
        "months": months,
        "month_total": {m: month_total[m] for m in months},
        "themes": themes,
        "theme_groups": parent_rows,
        "sectors": sector_rows,
        "entities": entity_rows,
    }
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, args.out)
    print("완료: %s (월 %d개 · 테마 %d개 · 섹터 %d개 · 종목 %d개)"
          % (args.out, len(months), len(themes), len(sector_rows), len(entity_rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
