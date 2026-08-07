# -*- coding: utf-8 -*-
"""통합 태그 인덱스 — 리서치노트·어닝콜 전문·실적 분석의 태그를 한 장부로 모은다.

세 코퍼스의 태그 정본이 각각 다른 sqlite 에 흩어져 있어서, `#KLAC` 하나로 전부 훑으려면
매번 여러 DB 를 조인해야 한다. 이 스크립트가 그 조인을 미리 해서 조회 전용 인덱스를 만든다.
**LLM 호출이 전혀 없다** — 이미 붙은 태그를 재배열할 뿐이라 언제 몇 번을 돌려도 무료다.

  입력 : ~/datalake/research_notes/tag_state.sqlite  (+ execution/research_bot/research_notes.db 본문)
         ~/datalake/doc_tag_state.sqlite             (+ transcripts·analyses md 본문)
  출력 : ~/datalake/tag_index.sqlite                 (매 실행 시 통째로 재생성)

사용:
  python3 datalake/tagging/build_tag_index.py
"""
import io
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import tag_docs  # noqa: E402
import tagging_common as tc  # noqa: E402
from dl_common import DATALAKE_ROOT, REPO  # noqa: E402

OUT_PATH = os.path.join(DATALAKE_ROOT, "tag_index.sqlite")
RESEARCH_STATE = os.path.join(DATALAKE_ROOT, "research_notes", "tag_state.sqlite")
RESEARCH_SRC = os.path.join(REPO, "execution", "research_bot", "research_notes.db")
DOC_STATE = os.path.join(DATALAKE_ROOT, "doc_tag_state.sqlite")
SNIPPET_CHARS = 180

SCHEMA = """
CREATE TABLE IF NOT EXISTS hits (
  tag TEXT NOT NULL,          -- 정규화 키 (소문자·공백제거)
  kind TEXT NOT NULL,         -- ticker | theme | sector | org | person
  corpus TEXT NOT NULL,       -- note | transcript | analysis | weekly | comment | monthly | target
  doc_date TEXT,
  rel_path TEXT NOT NULL,
  anchor TEXT,                -- 문서 안 위치 (rn-id / chunk 번호)
  title TEXT,
  snippet TEXT
);
CREATE INDEX IF NOT EXISTS idx_hits_tag ON hits(tag, doc_date DESC);
CREATE TABLE IF NOT EXISTS labels (
  tag TEXT PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL, freq INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_labels_freq ON labels(freq DESC);
CREATE TABLE IF NOT EXISTS aliases (
  alias TEXT PRIMARY KEY, tag TEXT NOT NULL, label TEXT
);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""

WS_RE = re.compile(r"\s+")


def norm(tag):
    """검색 키 정규화 — 대소문자·공백 무시. '#KLAC' 과 'klac' 이 같은 키가 된다."""
    return WS_RE.sub("", (tag or "").strip().lstrip("#")).lower()


def snippet_of(text):
    s = WS_RE.sub(" ", (text or "").strip())
    return s[:SNIPPET_CHARS]


class Index:
    def __init__(self, conn):
        self.conn = conn
        self.labels = {}          # key → (kind, label, freq)

    def add(self, tag_label, kind, corpus, doc_date, rel_path, anchor, title, snippet):
        key = norm(tag_label)
        if not key:
            return
        self.conn.execute(
            "INSERT INTO hits (tag,kind,corpus,doc_date,rel_path,anchor,title,snippet)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (key, kind, corpus, doc_date, rel_path, anchor, title, snippet))
        cur = self.labels.get(key)
        self.labels[key] = (kind, tag_label if not cur else cur[1], (cur[2] if cur else 0) + 1)

    def flush_labels(self):
        for key, (kind, label, freq) in self.labels.items():
            self.conn.execute(
                "INSERT INTO labels (tag,kind,label,freq) VALUES (?,?,?,?)"
                " ON CONFLICT(tag) DO UPDATE SET freq=freq+excluded.freq",
                (key, kind, label, freq))


def entity_tags(entity_id, uni, extra):
    """개체 id → [(표시라벨, kind)]. 티커는 'NASDAQ:KLAC' 와 'KLAC' 둘 다 색인."""
    u = uni["rows"].get(entity_id) or {}
    x = extra["rows"].get(entity_id) or {}
    name = u.get("name") or x.get("label_ko") or entity_id
    if name == entity_id and ":" in entity_id \
            and entity_id.split(":", 1)[0] in ("inst", "person", "private"):
        name = entity_id.split(":", 1)[1]          # 미등록 개체는 접두어만 벗겨 표시
    if entity_id.startswith("inst:") or entity_id.startswith("private:"):
        return [(name, "org")], None
    if entity_id.startswith("person:"):
        return [(name, "person")], None
    out = [(entity_id, "ticker")]
    sym = entity_id.split(":", 1)[1] if ":" in entity_id else entity_id
    if sym:
        out.append((sym, "ticker"))
    if name and name != entity_id:
        out.append((name, "ticker"))          # 한글 종목명으로도 검색되게
    return out, (u.get("sector") or None)


def index_research(idx, onto, uni, extra):
    if not (os.path.exists(RESEARCH_STATE) and os.path.exists(RESEARCH_SRC)):
        print("  리서치노트: 소스 없음 — 건너뜀")
        return 0
    st = sqlite3.connect("file:%s?mode=ro" % RESEARCH_STATE, uri=True)
    st.row_factory = sqlite3.Row
    src = sqlite3.connect("file:%s?mode=ro" % RESEARCH_SRC, uri=True)
    src.row_factory = sqlite3.Row
    texts = {r["id"]: (r["timestamp"], r["text_content"])
             for r in src.execute("SELECT id,timestamp,text_content FROM messages")}
    days = {r["message_id"]: r["day"] for r in st.execute(
        "SELECT message_id, day FROM items WHERE status='succeeded'")}
    n = 0
    for mid, day in days.items():
        ts, text = texts.get(mid, (day, ""))
        rel = "research_notes/%s/%s.md" % (day[:4], day)
        anchor = "rn-id: %s" % mid
        title = "리서치노트 %s %s" % (day, (ts or "")[11:16])
        snip = snippet_of(text)
        for r in st.execute("SELECT theme_id FROM theme_assignments WHERE message_id=?", (mid,)):
            meta = onto["themes"].get(r["theme_id"]) or {}
            idx.add(meta.get("label") or r["theme_id"], "theme", "note", day, rel, anchor, title, snip)
            n += 1
        for r in st.execute(
                "SELECT DISTINCT entity_id FROM entity_occurrences"
                " WHERE role!='incidental' AND message_id=?", (mid,)):
            tags, sector = entity_tags(r["entity_id"], uni, extra)
            for label, kind in tags:
                idx.add(label, kind, "note", day, rel, anchor, title, snip)
                n += 1
            if sector:
                idx.add(sector, "sector", "note", day, rel, anchor, title, snip)
                n += 1
    st.close()
    src.close()
    return n


def index_docs(idx, onto, uni, extra):
    if not os.path.exists(DOC_STATE):
        print("  전문·분석: 소스 없음 — 건너뜀")
        return 0
    st = sqlite3.connect("file:%s?mode=ro" % DOC_STATE, uri=True)
    st.row_factory = sqlite3.Row
    chunk_cache = {}
    n = 0
    rows = st.execute(
        "SELECT d.chunk_id, d.rel_path, d.chunk_no, d.kind, d.doc_date, d.title"
        " FROM docs d JOIN items i ON i.message_id = d.chunk_id"
        " WHERE i.status='succeeded'").fetchall()
    for d in rows:
        rel, cno = d["rel_path"], d["chunk_no"]
        if rel not in chunk_cache:
            path = os.path.join(DATALAKE_ROOT, rel)
            try:
                _fm, body = tag_docs.parse_md(io.open(path, encoding="utf-8").read())
                chunk_cache[rel] = tag_docs.split_chunks(body)
            except OSError:
                chunk_cache[rel] = []
        chunks = chunk_cache[rel]
        snip = snippet_of(chunks[cno]) if cno < len(chunks) else ""
        corpus = {"transcripts": "transcript", "analyses": "analysis"}.get(d["kind"], d["kind"])
        title = d["title"] or os.path.basename(rel)
        anchor = "chunk %d" % cno
        cid = d["chunk_id"]
        for r in st.execute("SELECT theme_id FROM theme_assignments WHERE message_id=?", (cid,)):
            meta = onto["themes"].get(r["theme_id"]) or {}
            idx.add(meta.get("label") or r["theme_id"], "theme", corpus,
                    d["doc_date"], rel, anchor, title, snip)
            n += 1
        for r in st.execute(
                "SELECT DISTINCT entity_id FROM entity_occurrences"
                " WHERE role!='incidental' AND message_id=?", (cid,)):
            tags, sector = entity_tags(r["entity_id"], uni, extra)
            for label, kind in tags:
                idx.add(label, kind, corpus, d["doc_date"], rel, anchor, title, snip)
                n += 1
            if sector:
                idx.add(sector, "sector", corpus, d["doc_date"], rel, anchor, title, snip)
                n += 1
    st.close()
    return n


ALIAS_CSV = os.path.join(HERE, "search_aliases.csv")


def load_search_aliases(conn):
    """검색 전용 별칭 (#MS -> 모건스탠리). 본문 매칭 사전과 무관 — 오탐 없이 검색만 넓힌다."""
    if not os.path.exists(ALIAS_CSV):
        return 0
    import csv
    n = 0
    with io.open(ALIAS_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            a, t = norm(row.get("alias")), norm(row.get("target"))
            if a and t and a != t:
                conn.execute("INSERT OR REPLACE INTO aliases (alias, tag, label) VALUES (?,?,?)",
                             (a, t, (row.get("target") or "").strip()))
                n += 1
    return n


def main():
    onto = tc.load_ontology()
    uni = tc.load_universe()
    extra = tc.load_entities_extra()

    tmp = OUT_PATH + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    conn = sqlite3.connect(tmp)
    conn.executescript(SCHEMA)
    idx = Index(conn)

    print("태그 인덱스 재생성")
    n1 = index_research(idx, onto, uni, extra)
    print("  리서치노트: %s 건" % format(n1, ","))
    n2 = index_docs(idx, onto, uni, extra)
    print("  전문·분석 : %s 건" % format(n2, ","))
    idx.flush_labels()
    na = load_search_aliases(conn)
    print("  검색 별칭 : %d 건" % na)
    conn.execute("INSERT OR REPLACE INTO meta (k,v) VALUES ('built_at', datetime('now','localtime'))")
    conn.commit()
    tags = conn.execute("SELECT count(*) FROM labels").fetchone()[0]
    conn.close()
    os.replace(tmp, OUT_PATH)          # 조회 중에도 안전하게 교체
    print("완료: hits %s · 태그 %s 종" % (format(n1 + n2, ","), format(tags, ",")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
