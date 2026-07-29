# -*- coding: utf-8 -*-
"""md 문서 태깅 워커 — 어닝콜 전문·실적 분석 시트에 리서치노트와 같은 태그를 붙인다.

리서치노트(tag_worker.py)는 텔레그램 메시지 단위로 태깅하지만, 여기는 긴 md 문서가
대상이라 **청크 단위**로 태깅한다. 콜 전문 한 건이 4만자를 넘어 문서 하나에 태그를
하나만 붙이면 "#HBM 으로 검색했을 때 그 대목이 어디였는지"를 잃기 때문이다.

온톨로지·별칭사전·프롬프트·정제·저장 스키마는 tag_worker 를 그대로 재사용한다
(태그 어휘가 갈리면 코퍼스 간 검색이 균일하지 않다).

  정본 : ~/datalake/doc_tag_state.sqlite   (청크별 테마·개체)
  투영 : 각 md 의 frontmatter (themes/tickers/sectors/orgs) — 재생성 가능한 캐시

사용:
  python3 datalake/tagging/tag_docs.py --dry-run           # 대상·토큰 견적만
  python3 datalake/tagging/tag_docs.py                     # 미처리분 전부
  python3 datalake/tagging/tag_docs.py --kind analyses --max-items 20
  python3 datalake/tagging/tag_docs.py --project           # frontmatter 재투영만
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import tagging_common as tc  # noqa: E402
import tag_worker as tw  # noqa: E402
from dl_common import DATALAKE_ROOT  # noqa: E402

DOC_TAGGER_VERSION = "1.0.0"
STATE_DB = os.path.join(DATALAKE_ROOT, "doc_tag_state.sqlite")
BATCH = int(os.getenv("DOC_TAG_BATCH", "8"))
CHUNK_CHARS = int(os.getenv("DOC_TAG_CHUNK", "4000"))
MIN_CHUNK = 120

# kind → 루트 디렉토리 (datalake 상대)
SOURCES = {
    "transcripts": "transcripts",   # 어닝콜 한국어 번역 전문
    "analyses": "analyses",         # 분기 실적 1-page 분석
}
MANAGED_KEYS = ("themes", "tickers", "sectors", "orgs", "people",
                "tag_schema_version", "tag_status")

DOC_SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (
  chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
  rel_path TEXT NOT NULL, chunk_no INTEGER NOT NULL,
  kind TEXT, doc_date TEXT, ticker TEXT, title TEXT, char_len INTEGER,
  UNIQUE (rel_path, chunk_no)
);
CREATE INDEX IF NOT EXISTS idx_docs_path ON docs(rel_path);
CREATE INDEX IF NOT EXISTS idx_docs_kind ON docs(kind);
"""


# --------------------------------------------------------------------------- #
# md 파싱
# --------------------------------------------------------------------------- #
FM_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.S)


def parse_md(text):
    """(frontmatter dict, body) — 값은 문자열로만 (따옴표·JSON 리스트는 그대로)."""
    m = FM_RE.match(text)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).split("\n"):
        if not line.strip() or line.startswith("#") or ":" not in line:
            continue
        if line[0] in " \t":          # 중첩 블록은 건드리지 않는다
            continue
        k, v = line.split(":", 1)
        fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, text[m.end():]


def doc_title(fm, body):
    if fm.get("title"):
        return fm["title"][:120]
    for line in body.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()[:120]
    return ""


def split_chunks(body, target=CHUNK_CHARS):
    """문단 경계 우선, 초장문 문단은 강제 분할."""
    chunks, cur = [], ""
    for para in body.split("\n\n"):
        while len(para) > target * 2:
            head, para = para[:target], para[target:]
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(head)
        if cur and len(cur) + len(para) + 2 > target:
            chunks.append(cur)
            cur = para
        else:
            cur = (cur + "\n\n" + para) if cur else para
    if cur:
        chunks.append(cur)
    return [c.strip() for c in chunks if len(c.strip()) >= MIN_CHUNK]


def ticker_entity(fm, uni_index):
    """frontmatter 의 ticker(예: KLAC) → 유니버스 entity_id(NASDAQ:KLAC)."""
    t = (fm.get("ticker") or "").strip().upper()
    return uni_index.get(t) if t else None


def build_ticker_index(uni):
    idx = {}
    for eid in uni["rows"]:
        if ":" not in eid:
            continue
        sym = eid.split(":", 1)[1].upper()
        idx.setdefault(sym, eid)          # 먼저 등장한 거래소를 대표로
        idx.setdefault(eid.upper(), eid)
    return idx


# --------------------------------------------------------------------------- #
# 대상 수집
# --------------------------------------------------------------------------- #
def iter_docs(kinds):
    for kind in kinds:
        root = os.path.join(DATALAKE_ROOT, SOURCES[kind])
        for dirpath, _dirs, files in os.walk(root):
            for name in sorted(files):
                if name.endswith(".md"):
                    path = os.path.join(dirpath, name)
                    yield kind, path, os.path.relpath(path, DATALAKE_ROOT)


def register_chunks(st, kind, rel, fm, body, title):
    """청크를 docs 에 등록하고 [(chunk_id, text)] 반환. 줄어든 청크는 정리."""
    chunks = split_chunks(body)
    doc_date = (fm.get("date") or fm.get("filed_at") or "")[:10]
    ticker = (fm.get("ticker") or "").strip().upper()
    out = []
    for i, text in enumerate(chunks):
        st.execute(
            "INSERT INTO docs (rel_path,chunk_no,kind,doc_date,ticker,title,char_len)"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(rel_path,chunk_no) DO UPDATE SET kind=excluded.kind,"
            " doc_date=excluded.doc_date, ticker=excluded.ticker, title=excluded.title,"
            " char_len=excluded.char_len",
            (rel, i, kind, doc_date, ticker, title, len(text)))
        row = st.execute("SELECT chunk_id FROM docs WHERE rel_path=? AND chunk_no=?",
                         (rel, i)).fetchone()
        out.append((row["chunk_id"], text))
    stale = st.execute("SELECT chunk_id FROM docs WHERE rel_path=? AND chunk_no>=?",
                       (rel, len(chunks))).fetchall()
    for r in stale:
        cid = r["chunk_id"]
        st.execute("DELETE FROM theme_assignments WHERE message_id=?", (cid,))
        st.execute("DELETE FROM entity_occurrences WHERE message_id=?", (cid,))
        st.execute("DELETE FROM items WHERE message_id=?", (cid,))
        st.execute("DELETE FROM docs WHERE chunk_id=?", (cid,))
    return out, doc_date, ticker


# --------------------------------------------------------------------------- #
# frontmatter 투영
# --------------------------------------------------------------------------- #
def _yaml_list(values):
    return json.dumps(sorted(values), ensure_ascii=False)


def project_doc(st, rel, uni, extra, onto):
    """상태 DB 의 태그를 md frontmatter 로 투영. 변경 시 True.

    표기는 리서치노트(export_research_notes.render_day)와 동일하게 맞춘다 —
    테마는 한글 라벨, 개체는 subject 역할만, inst/person/private 은 orgs·people 로.
    """
    path = os.path.join(DATALAKE_ROOT, rel)
    if not os.path.exists(path):
        return False
    rows = st.execute("SELECT chunk_id FROM docs WHERE rel_path=?", (rel,)).fetchall()
    ids = [r["chunk_id"] for r in rows]
    if not ids:
        return False
    ph = ",".join("?" * len(ids))
    themes = set()
    for r in st.execute(
            "SELECT DISTINCT theme_id FROM theme_assignments WHERE message_id IN (%s)" % ph, ids):
        meta = onto["themes"].get(r["theme_id"]) or {}
        themes.add(meta.get("label") or r["theme_id"])
    ents = {r["entity_id"] for r in st.execute(
        "SELECT DISTINCT entity_id FROM entity_occurrences"
        " WHERE role='subject' AND message_id IN (%s)" % ph, ids)}
    done = {r["message_id"] for r in st.execute(
        "SELECT message_id FROM items WHERE status='succeeded' AND message_id IN (%s)" % ph, ids)}

    tickers, orgs, people, sectors = set(), set(), set(), set()
    for e in ents:
        u = uni["rows"].get(e) or {}
        x = extra["rows"].get(e) or {}
        name = u.get("name") or x.get("label_ko") or e
        if e.startswith("inst:") or e.startswith("private:"):
            orgs.add(name)
        elif e.startswith("person:"):
            people.add(name)
        else:
            tickers.add(e)
            if u.get("sector"):
                sectors.add(u["sector"])

    with open(path, encoding="utf-8") as f:
        raw = f.read()
    m = FM_RE.match(raw)
    if not m:
        return False
    kept = [ln for ln in m.group(1).split("\n")
            if not any(ln.startswith(k + ":") for k in MANAGED_KEYS)]
    kept += [
        "themes: " + _yaml_list(themes),
        "tickers: " + _yaml_list(tickers),
        "sectors: " + _yaml_list(sectors),
        "orgs: " + _yaml_list(orgs),
        "people: " + _yaml_list(people),
        "tag_schema_version: 1",
        "tag_status: %s" % ("complete" if len(done) == len(ids) else "partial"),
    ]
    new = "---\n" + "\n".join(kept) + "\n---\n" + raw[m.end():]
    if new == raw:
        return False
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(new)
    os.replace(tmp, path)
    return True


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=sorted(SOURCES), action="append",
                    help="대상 코퍼스 (기본: 전부)")
    ap.add_argument("--dry-run", action="store_true", help="호출 없이 대상·토큰 견적만")
    ap.add_argument("--project", action="store_true", help="LLM 없이 frontmatter 재투영만")
    ap.add_argument("--max-items", type=int, help="이번 실행에서 처리할 청크 상한")
    ap.add_argument("--max-docs", type=int, help="대상 문서 수 상한 (테스트용)")
    ap.add_argument("--force", action="store_true", help="캐시 무시하고 재태깅")
    ap.add_argument("--retry-failed", action="store_true")
    args = ap.parse_args()

    kinds = args.kind or sorted(SOURCES)
    onto = tc.load_ontology()
    uni = tc.load_universe()
    extra = tc.load_entities_extra()
    idx = tc.build_alias_index(universe=uni, extra=extra)
    uni_index = build_ticker_index(uni)
    tw.save_result.alias_index = idx
    system = tw.build_system_prompt(onto)
    prompt_hash = tw.sha(system, tw.TAGGER_VERSION, DOC_TAGGER_VERSION)

    st = tw.open_state(STATE_DB)
    st.executescript(DOC_SCHEMA)

    docs = list(iter_docs(kinds))
    if args.max_docs:
        docs = docs[:args.max_docs]

    todo, cached, touched = [], 0, []
    for kind, path, rel in docs:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        fm, body = parse_md(raw)
        title = doc_title(fm, body)
        chunks, doc_date, ticker = register_chunks(st, kind, rel, fm, body, title)
        touched.append(rel)
        subject = ticker_entity(fm, uni_index)
        for cid, text in chunks:
            ch = tw.sha(text, "", "")
            ck = tw.sha(ch, tw.TAGGER_VERSION, DOC_TAGGER_VERSION, prompt_hash,
                        onto["hash"], uni["hash"], idx["hash"])
            cur = st.execute("SELECT cache_key,status FROM items WHERE message_id=?",
                             (cid,)).fetchone()
            if (not args.force and cur and cur["cache_key"] == ck
                    and cur["status"] == "succeeded"):
                cached += 1
                continue
            if args.retry_failed and (not cur or cur["status"] == "succeeded"):
                continue
            todo.append({"id": cid, "text_content": text, "article_content": None,
                         "forward_source": None, "timestamp": doc_date or "1970-01-01",
                         "_content_hash": ch, "_cache_key": ck, "_subject": subject,
                         "_rel": rel})
    st.commit()

    if args.project:
        n = sum(1 for rel in touched if project_doc(st, rel, uni, extra, onto))
        print("frontmatter 재투영: %d/%d 문서 갱신" % (n, len(touched)))
        return 0

    if args.max_items:
        todo = todo[:args.max_items]

    est_in = sum(len(m["text_content"]) for m in todo) // 2
    est_in += len(system) // 2 * (len(todo) // BATCH + 1)
    print("문서 %d건 / 청크 대상 %d개 (캐시 재사용 %d) / 배치 %d / 추정 입력 토큰 ~%s"
          % (len(docs), len(todo), cached, BATCH, format(est_in, ",")))
    if args.dry_run:
        return 0
    if not todo:
        n = sum(1 for rel in touched if project_doc(st, rel, uni, extra, onto))
        print("신규 없음 — frontmatter %d건 갱신" % n)
        return 0

    import anthropic
    client = anthropic.Anthropic(api_key=tw.load_env_key())
    cur = st.execute(
        "INSERT INTO tag_runs (started_at,model,tagger_version,prompt_hash,ontology_version,"
        "ontology_hash,universe_hash,alias_hash,items_total) VALUES (?,?,?,?,?,?,?,?,?)",
        (tw.now(), tw.MODEL, "%s+doc%s" % (tw.TAGGER_VERSION, DOC_TAGGER_VERSION),
         prompt_hash, onto["version"], onto["hash"], uni["hash"], idx["hash"], len(todo)))
    run_id = cur.lastrowid
    st.commit()

    ok = fail = tin = tout = tcache = 0
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        prepared = []
        for m in batch:
            strong, weak = tw.rule_pass(m, idx)
            if m["_subject"]:            # 문서 주인공 종목은 규칙으로 강제 부여
                strong.append({"entity_id": m["_subject"], "field": "meta",
                               "start": 0, "end": 0, "surface": m["_subject"],
                               "role": "subject", "method": "rule_frontmatter"})
            prepared.append((m, strong, weak))
        blocks = [tw.render_message_block(m, weak, uni, extra) for m, _, weak in prepared]
        try:
            out, usage = tw.call_llm(client, system, blocks)
            tin += getattr(usage, "input_tokens", 0) or 0
            tout += getattr(usage, "output_tokens", 0) or 0
            tcache += getattr(usage, "cache_read_input_tokens", 0) or 0
            by_mid = {int(r.get("message_id", -1)): r for r in (out or {}).get("results", [])}
            for m, strong, weak in prepared:
                res = by_mid.get(m["id"])
                if res is None:
                    tw.mark_failed(st, m, m["timestamp"][:10], m["_cache_key"],
                                   m["_content_hash"], run_id, "missing in batch response")
                    fail += 1
                    continue
                res = tw.sanitize(res, onto, weak)
                tw.save_result(st, m, m["timestamp"][:10], m["_cache_key"],
                               m["_content_hash"], run_id, strong, weak, res)
                ok += 1
            st.commit()
        except Exception as e:  # noqa: BLE001
            for m, _, _ in prepared:
                tw.mark_failed(st, m, m["timestamp"][:10], m["_cache_key"],
                               m["_content_hash"], run_id, e)
            fail += len(prepared)
            st.commit()
            print("  배치 실패 (%d건): %s" % (len(prepared), str(e)[:160]))
        print("  %d/%d  ok=%d fail=%d  in=%s out=%s cache=%s"
              % (min(i + BATCH, len(todo)), len(todo), ok, fail,
                 format(tin, ","), format(tout, ","), format(tcache, ",")), flush=True)

    st.execute("UPDATE tag_runs SET finished_at=?, items_ok=?, items_failed=?, input_tokens=?,"
               " output_tokens=?, cache_read_tokens=? WHERE run_id=?",
               (tw.now(), ok, fail, tin, tout, tcache, run_id))
    st.commit()

    projected = sum(1 for rel in sorted({m["_rel"] for m in todo}) if project_doc(st, rel, uni, extra, onto))
    print("완료: ok=%d fail=%d / 입력 %s · 출력 %s · 캐시읽기 %s 토큰 / frontmatter %d건 갱신"
          % (ok, fail, format(tin, ","), format(tout, ","), format(tcache, ","), projected))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
