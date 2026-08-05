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
import csv
import io
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dl_common import CATALOG_DIR, DATALAKE_ROOT, DUCKDB_PATH, MARKET_DIR, REPO  # noqa: E402

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
MAX_ROWS = 200
MAX_OUT_CHARS = 200000
SQL_TIMEOUT_SEC = int(os.getenv("WIKI_SQL_TIMEOUT", "60"))

# ★화이트리스트: 선행 주석·공백을 걷어낸 뒤 SELECT/WITH 로 시작해야만 통과.
#   종전 키워드 블랙리스트는 CALL·DESCRIBE·SHOW 등을 못 막았다 (codex 지적, 실증됨).
_SQL_ALLOWED = re.compile(r"^(?:\s|--[^\n]*\n|/\*.*?\*/)*(SELECT|WITH)\b", re.I | re.S)

# ★파일접근 테이블함수 차단. allowed_directories 안이라도 파일 원문을 돌려주면 안 된다
#   (read_blob 으로 market.duckdb 를 읽는 것이 실증됐다).
_SQL_FILE_FN = re.compile(
    r"\b(read_blob|read_text|read_csv\w*|read_json\w*|read_ndjson\w*|read_parquet"
    r"|read_xlsx|parquet_scan|csv_scan|sniff_csv|glob|duckdb_settings|duckdb_extensions"
    r"|install_extension|load_extension|postgres_scan|mysql_scan|sqlite_scan|delta_scan"
    r"|iceberg_scan|st_read)\s*\(", re.I)

# 방어 2겹째 — 화이트리스트를 뚫는 변형이 나와도 쓰기·설정 구문은 막는다
_SQL_FORBIDDEN = re.compile(
    r"\b(ATTACH|DETACH|COPY|EXPORT|IMPORT|INSTALL|LOAD|CREATE|INSERT|UPDATE|DELETE"
    r"|DROP|ALTER|PRAGMA|SET|RESET|CALL|VACUUM|CHECKPOINT)\b", re.I)


def _sandboxed_connect():
    """읽기전용 + 외부접근 차단 + 자원 상한.

    ★순서 주의: allowed_directories 를 먼저 좁힌 뒤 external_access 를 끈다
      (끄고 나면 세션 내 재활성화 불가).
    """
    import duckdb
    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    con.execute("SET allowed_directories=['%s']" % MARKET_DIR)
    con.execute("SET autoinstall_known_extensions=false")
    con.execute("SET autoload_known_extensions=false")
    con.execute("SET memory_limit='2GB'")
    con.execute("SET threads=2")
    con.execute("SET enable_external_access=false")
    return con


def _validate_sql(sql):
    """통과하면 None, 막히면 사용자에게 보여줄 사유 문자열."""
    q = (sql or "").strip()
    if not q:
        return "ERROR: 빈 쿼리입니다."
    body = q.rstrip(";").strip()
    if ";" in body:
        return "ERROR: 한 번에 하나의 조회문만 실행할 수 있습니다."
    if not _SQL_ALLOWED.match(body):
        return "ERROR: SELECT 또는 WITH 로 시작하는 조회만 허용됩니다."
    if _SQL_FILE_FN.search(body):
        return "ERROR: 파일·확장 접근 함수는 사용할 수 없습니다. 등록된 뷰만 조회하세요."
    if _SQL_FORBIDDEN.search(body):
        return "ERROR: 조회 외 구문은 허용되지 않습니다."
    return None


def run_sql(sql):
    bad = _validate_sql(sql)
    if bad:
        return bad
    try:
        con = _sandboxed_connect()
    except Exception as e:
        return "ERROR: DB 연결 실패(카탈로그 갱신 중일 수 있음, 잠시 후 재시도): %s" % e

    import threading
    timed_out = {"v": False}

    def _kill():
        timed_out["v"] = True
        try:
            con.interrupt()
        except Exception:
            pass

    timer = threading.Timer(SQL_TIMEOUT_SEC, _kill)
    timer.start()
    try:
        cur = con.execute(sql.strip().rstrip(";"))
        cols = [d[0] for d in (cur.description or [])]
        # ★전량 materialize(fetchdf) 대신 필요한 만큼만 — 거대 결과가 메모리를 밀어내지 않게
        rows = cur.fetchmany(MAX_ROWS + 1)
    except Exception as e:
        if timed_out["v"]:
            return "ERROR: 쿼리가 %d초를 넘겨 중단됐습니다. 조건을 좁혀 주세요." % SQL_TIMEOUT_SEC
        return "ERROR: %s: %s" % (type(e).__name__, e)
    finally:
        timer.cancel()
        try:
            con.close()
        except Exception:
            pass

    if not rows:
        return "(0행)"
    more = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow(["" if v is None else str(v) for v in r])
        if buf.tell() > MAX_OUT_CHARS:
            return (buf.getvalue()[:MAX_OUT_CHARS]
                    + "\n... (출력이 너무 커서 잘렸습니다. 컬럼을 줄이거나 집계해 주세요)")
    out = buf.getvalue()
    if more:
        out += "... (총 %d행 초과 — 상위 %d행만 표시)" % (MAX_ROWS, MAX_ROWS)
    return out


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
