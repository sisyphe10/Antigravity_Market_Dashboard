# -*- coding: utf-8 -*-
"""규칙 기반 개체 매칭만 다시 계산한다 (LLM 재호출 없음).

별칭 사전이나 매칭 규칙을 고쳤을 때 쓴다. 테마 판정과 weak 후보의 문맥 판정은
모델이 내린 결과이므로 그대로 두고, 규칙으로 결정되는 부분만 갈아끼운다.
전량 재태깅(--force)은 같은 결과를 얻는 데 수 시간·수 달러가 더 든다.

  - method IN ('rule_strong','rule_header') 행 → 현재 규칙으로 재생성
  - method='llm_context' 행 중, 이제는 후보로도 잡히지 않는 것 → 제거
    (예: URL 안에서만 매칭되던 개체)

사용: python3 datalake/tagging/recompute_rules.py [--dry-run]
"""
import argparse
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import tagging_common as tc  # noqa: E402
from dl_common import DATALAKE_ROOT, REPO  # noqa: E402
from tag_worker import rule_pass  # noqa: E402

STATE_DB = os.path.join(DATALAKE_ROOT, "research_notes", "tag_state.sqlite")
SRC_DB = os.path.join(REPO, "execution", "research_bot", "research_notes.db")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    uni = tc.load_universe()
    idx = tc.build_alias_index(universe=uni)
    print("별칭 %d개 / universe %s / alias %s"
          % (len(idx["entries"]), uni["hash"], idx["hash"]))

    src = sqlite3.connect("file:%s?mode=ro" % SRC_DB, uri=True)
    src.row_factory = sqlite3.Row
    msgs = {r["id"]: dict(r) for r in src.execute(
        "SELECT id,text_content,article_content FROM messages")}
    src.close()

    st = sqlite3.connect(STATE_DB, timeout=60)
    st.row_factory = sqlite3.Row
    targets = [r["message_id"] for r in st.execute(
        "SELECT message_id FROM items WHERE status='succeeded' ORDER BY message_id")]
    before = st.execute("SELECT COUNT(*) FROM entity_occurrences").fetchone()[0]

    added = dropped_llm = 0
    for i, mid in enumerate(targets, 1):
        m = msgs.get(mid)
        if not m:
            continue
        strong, weak = rule_pass(m, idx)
        if args.dry_run:
            continue
        st.execute("DELETE FROM entity_occurrences WHERE message_id=? "
                   "AND method IN ('rule_strong','rule_header')", (mid,))
        for c in strong:
            st.execute(
                "INSERT OR REPLACE INTO entity_occurrences"
                " (message_id,entity_id,field,span_start,span_end,surface,role,method,confidence)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (mid, c["entity_id"], c["field"], c["start"], c["end"],
                 c["surface"], c["role"], c["method"], 1.0))
            added += 1
        keep = {c["entity_id"] for c in weak}
        cur = st.execute("SELECT entity_id FROM entity_occurrences WHERE message_id=? "
                         "AND method='llm_context'", (mid,)).fetchall()
        for r in cur:
            if r["entity_id"] not in keep:
                st.execute("DELETE FROM entity_occurrences WHERE message_id=? AND entity_id=? "
                           "AND method='llm_context'", (mid, r["entity_id"]))
                dropped_llm += 1
        if i % 500 == 0:
            st.commit()
            print("  %d/%d" % (i, len(targets)), flush=True)
    if not args.dry_run:
        st.commit()
    after = st.execute("SELECT COUNT(*) FROM entity_occurrences").fetchone()[0]
    st.close()
    print("완료: 규칙 개체 %d건 재생성, 후보 밖 llm_context %d건 제거 / 총 %d → %d행"
          % (added, dropped_llm, before, after))
    return 0


if __name__ == "__main__":
    sys.exit(main())
