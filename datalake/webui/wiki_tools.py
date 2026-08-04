# -*- coding: utf-8 -*-
"""위키 문답 도구 구현 — API 루프와 headless(MCP) 백엔드가 공유하는 정본.

노출 3종 (2026-08-05 headless 전환 설계):
  run_sql      : market.duckdb 읽기전용 SELECT (최대 200행)
  search_notes : md 코퍼스 정규식 검색 (SEARCH_ROOTS 한정, 기본 40건)
  tag_search   : tag_index.sqlite 태그 검색

★read_file / list_datasets 는 의도적으로 제외한다 — headless 쪽은 Claude Code
  네이티브 Read/Glob 이 offset·대용량 처리를 더 잘하고, --add-dir 로 경로가 닫힌다.

★이 모듈은 MCP stdio 서버에 임포트되므로 **stdout 으로 절대 출력하지 않는다**
  (JSON-RPC 스트림이 깨진다). 진단 출력은 stderr 로만.
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dl_common import CATALOG_DIR, DATALAKE_ROOT, DUCKDB_PATH, REPO  # noqa: E402

WIKI_DIR = os.path.join(REPO, "architecture", "wiki")
TAG_INDEX_PATH = os.path.join(DATALAKE_ROOT, "tag_index.sqlite")

SEARCH_ROOTS = [
    os.path.join(DATALAKE_ROOT, "research_notes"),
    os.path.join(DATALAKE_ROOT, "transcripts"),
    os.path.join(DATALAKE_ROOT, "analyses"),
    os.path.join(DATALAKE_ROOT, "notion_study"),
    os.path.join(DATALAKE_ROOT, "reports"),
    CATALOG_DIR,
    WIKI_DIR,
]

# ── run_sql ────────────────────────────────────────────────────────
_SQL_FORBIDDEN = re.compile(
    r"\b(ATTACH|COPY|EXPORT|INSTALL|LOAD|CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|PRAGMA|SET)\b",
    re.I)


def _sandboxed_connect():
    """읽기전용 + 외부접근 차단. _SQL_FORBIDDEN 키워드 필터만으로는
    read_text('/…/.env') 같은 SELECT 파일함수를 막지 못하므로 런타임 SET 으로 잠근다.
    ★순서 주의: allowed_directories 를 먼저 좁힌 뒤 external_access 를 끈다
      (끄고 나면 재활성화 불가)."""
    import duckdb
    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    con.execute("SET autoinstall_known_extensions=false")
    con.execute("SET autoload_known_extensions=false")
    con.execute("SET enable_external_access=false")
    return con


def run_sql(sql):
    if _SQL_FORBIDDEN.search(sql or ""):
        return "ERROR: SELECT만 허용됩니다."
    try:
        con = _sandboxed_connect()
    except Exception as e:
        return "ERROR: DB 연결 실패(카탈로그 갱신 중일 수 있음, 잠시 후 재시도): %s" % e
    try:
        df = con.execute(sql).fetchdf()
    except Exception as e:
        return "ERROR: %s: %s" % (type(e).__name__, e)
    finally:
        con.close()
    if len(df) > 200:
        return df.head(200).to_csv(index=False) + "\n... (총 %d행 중 200행 표시)" % len(df)
    return df.to_csv(index=False) if not df.empty else "(0행)"


# ── search_notes ───────────────────────────────────────────────────
def search_notes(pattern, max_results=40):
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return "ERROR: 잘못된 정규식 — %s" % e
    max_results = max(1, min(int(max_results or 40), 200))
    hits = []
    for root in SEARCH_ROOTS:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for fn in sorted(files):
                if not fn.endswith(".md"):
                    continue
                fp = os.path.join(dirpath, fn)
                try:
                    with open(fp, encoding="utf-8", errors="replace") as fh:
                        for i, line in enumerate(fh, 1):
                            if rx.search(line):
                                hits.append("%s:%d: %s" % (fp, i, line.strip()[:200]))
                                if len(hits) >= max_results:
                                    return "\n".join(hits)
                except OSError:
                    continue
    return "\n".join(hits) if hits else "(매칭 없음)"


# ── tag_search ─────────────────────────────────────────────────────
def _tag_conn():
    if not os.path.exists(TAG_INDEX_PATH):
        return None
    con = sqlite3.connect("file:%s?mode=ro" % TAG_INDEX_PATH, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _tag_norm(q):
    return re.sub(r"\s+", "", (q or "").strip().lstrip("#")).lower()


def _resolve_tags(con, q, limit=12):
    """질의 → 실제 태그 키 목록. 정확히 일치하면 그것만, 아니면 부분 일치."""
    key = _tag_norm(q)
    if not key:
        return []
    row = con.execute("SELECT tag FROM labels WHERE tag=?", (key,)).fetchone()
    if row:
        return [row["tag"]]
    like = "%" + key + "%"
    return [r["tag"] for r in con.execute(
        "SELECT tag FROM labels WHERE tag LIKE ? ORDER BY freq DESC LIMIT ?", (like, limit))]


def tag_search(q, limit=20):
    con = _tag_conn()
    if con is None:
        return {"error": "태그 인덱스가 아직 생성되지 않았습니다", "matched": [], "results": []}
    try:
        keys = _resolve_tags(con, q)
        if not keys:
            return {"matched": [], "results": [], "total": 0}
        ph = ",".join("?" * len(keys))
        matched = [dict(r) for r in con.execute(
            "SELECT tag, label, kind, freq FROM labels WHERE tag IN (%s)"
            " ORDER BY freq DESC" % ph, keys)]
        total = con.execute(
            "SELECT count(*) FROM (SELECT 1 FROM hits WHERE tag IN (%s)"
            " GROUP BY rel_path, anchor)" % ph, keys).fetchone()[0]
        rows = con.execute(
            "SELECT corpus, doc_date, rel_path, anchor, title, snippet FROM hits"
            " WHERE tag IN (%s) GROUP BY rel_path, anchor"
            " ORDER BY doc_date DESC, rel_path LIMIT ?" % ph,
            keys + [max(1, min(int(limit), 100))]).fetchall()
        return {"matched": matched, "total": total, "results": [dict(r) for r in rows]}
    finally:
        con.close()
