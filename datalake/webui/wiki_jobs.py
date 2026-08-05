# -*- coding: utf-8 -*-
"""위키 headless 문답 비동기 잡 큐 — 단일 worker, sqlite 영속.

저장은 기존 webui_chats.sqlite 에 테이블을 추가한다 (chats 스키마 불변).
설계 근거: 잡이 chat_id 를 참조하므로 같은 파일이 정합성에 유리하고 WAL도 하나만 관리.

동시 실행 1개 — 구독 쿼터를 자가치료 진단·아침 다이제스트와 나눠 쓰기 때문.
재시작 시 running 잡은 재실행하지 않고 failed(server_restart) 로 확정한다 (쿼터 이중소모 방지).
"""
import json
import os
import sqlite3
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
DATALAKE_ROOT = os.path.expanduser(os.getenv("DATALAKE_ROOT", "~/datalake"))
DB_PATH = os.path.join(DATALAKE_ROOT, "webui_chats.sqlite")

WORKER_ID = uuid.uuid4().hex[:12]     # 이 프로세스의 워커 식별자
_worker_thread = None
_lock = threading.Lock()
_wake = threading.Event()
_db_ready = False


def _con():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    return con


def init_db():
    con = _con()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS wiki_jobs ("
                    "id TEXT PRIMARY KEY, request_id TEXT UNIQUE, chat_id TEXT,"
                    "question TEXT NOT NULL, history TEXT, status TEXT NOT NULL,"
                    "answer TEXT, steps TEXT, meta TEXT, error TEXT,"
                    "notified INTEGER DEFAULT 0, created_at REAL NOT NULL,"
                    "started_at REAL, finished_at REAL)")
        con.execute("CREATE INDEX IF NOT EXISTS ix_wiki_jobs_status"
                    " ON wiki_jobs(status, created_at)")
        cols = [r[1] for r in con.execute("PRAGMA table_info(wiki_jobs)")]
        if "worker" not in cols:
            con.execute("ALTER TABLE wiki_jobs ADD COLUMN worker TEXT")
        # ★살아있는 다른 워커의 잡까지 죽이지 않도록 '충분히 오래된 running' 만 정리한다
        #   (codex 지적: 종전엔 무조건 전체 running 을 failed 로 덮었다)
        cutoff = time.time() - (int(os.getenv("WIKI_TIMEOUT_SEC", "900")) + 300)
        n = con.execute(
            "UPDATE wiki_jobs SET status='failed', error='server_restart', finished_at=?"
            " WHERE status='running' AND (started_at IS NULL OR started_at < ?)",
            (time.time(), cutoff)).rowcount
        con.commit()
        if n:
            print("[wiki_jobs] restart recovery: running %d -> failed" % n, flush=True)
    finally:
        con.close()


def _row_to_dict(row):
    d = dict(row)
    for k in ("steps", "meta", "history"):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except ValueError:
                pass
    d["steps"] = d.get("steps") or []
    d["meta"] = d.get("meta") or {}
    return d


def submit(question, history=None, chat_id=None, request_id=None):
    """잡 등록. 같은 request_id 가 이미 있으면 그 잡을 그대로 돌려준다(멱등)."""
    init_once()
    con = _con()
    try:
        if request_id:
            row = con.execute("SELECT * FROM wiki_jobs WHERE request_id=?",
                              (request_id,)).fetchone()
            if row:
                return _row_to_dict(row)
        jid = uuid.uuid4().hex[:16]
        con.execute(
            "INSERT INTO wiki_jobs(id, request_id, chat_id, question, history, status,"
            " created_at) VALUES(?,?,?,?,?,'queued',?)",
            (jid, request_id, chat_id, question,
             json.dumps(history or [], ensure_ascii=False), time.time()))
        con.commit()
    finally:
        con.close()
    _wake.set()
    return get(jid)


def get(job_id):
    init_once()          # 폴링 중 워커가 죽어 있으면 여기서 되살린다
    con = _con()
    try:
        row = con.execute("SELECT * FROM wiki_jobs WHERE id=?", (job_id,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        con.close()


def queue_depth():
    con = _con()
    try:
        return con.execute(
            "SELECT count(*) FROM wiki_jobs WHERE status='queued'").fetchone()[0]
    finally:
        con.close()


def recent_failures(n=3):
    """최근 종료된 잡 n건이 전부 실패면 True (쿼터 소진 의심 신호)."""
    con = _con()
    try:
        rows = con.execute(
            "SELECT status FROM wiki_jobs WHERE status IN ('succeeded','failed','timeout')"
            " ORDER BY finished_at DESC LIMIT ?", (n,)).fetchall()
        return len(rows) == n and all(r["status"] != "succeeded" for r in rows)
    finally:
        con.close()


def _claim_job():
    """queued 1건을 원자적으로 running 으로 전환하고 그 행을 돌려준다.

    ★종전엔 SELECT 와 UPDATE 가 분리돼 있어, 프로세스가 둘이면 같은 잡을
      중복 실행할 수 있었다 (codex 지적). 단일 UPDATE ... RETURNING 으로 바꾼다.
    """
    con = _con()
    try:
        row = con.execute(
            "UPDATE wiki_jobs SET status='running', started_at=?, worker=?"
            " WHERE id = (SELECT id FROM wiki_jobs WHERE status='queued'"
            "             ORDER BY created_at LIMIT 1)"
            " RETURNING *", (time.time(), WORKER_ID)).fetchone()
        con.commit()
        return _row_to_dict(row) if row else None
    finally:
        con.close()


def _run_one(job):
    import headless_backend
    try:
        out = headless_backend.run_question(job["question"],
                                            history=job.get("history") or [])
    except Exception as e:
        out = {"ok": False, "status": "failed", "answer": "", "steps": [], "meta": {},
               "error": "%s: %s" % (type(e).__name__, e)}
    con = _con()
    try:
        con.execute(
            "UPDATE wiki_jobs SET status=?, answer=?, steps=?, meta=?, error=?,"
            " finished_at=? WHERE id=?",
            (out.get("status") or ("succeeded" if out.get("ok") else "failed"),
             out.get("answer") or "",
             json.dumps(out.get("steps") or [], ensure_ascii=False),
             json.dumps(out.get("meta") or {}, ensure_ascii=False),
             out.get("error"), time.time(), job["id"]))
        con.commit()
    finally:
        con.close()
    return out


def _esc(s):
    import html as _h
    return _h.escape(str(s), quote=False)


def _send_tg(token, chat, text, parse_mode=None):
    """텔레그램 발송. 성공 True. 실패는 로그만 (알림은 best-effort)."""
    try:
        import urllib.parse
        import urllib.request
        payload = {"chat_id": chat, "text": text, "disable_web_page_preview": "true"}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        data = urllib.parse.urlencode(payload).encode()
        urllib.request.urlopen("https://api.telegram.org/bot%s/sendMessage" % token,
                               data=data, timeout=15).read()
        return True
    except Exception as e:
        print("[wiki_jobs] telegram send 실패(parse_mode=%s): %s" % (parse_mode, e),
              flush=True)
        return False


def _md_to_tg_html(md):
    """위키 답변 마크다운 → 텔레그램 HTML. ## 제목/**굵게** → <b>, 표 → <pre> 고정폭."""
    import re as _re
    out, table = [], []

    def _flush():
        if table:
            out.append("<pre>" + _esc("\n".join(table)) + "</pre>")
            table.clear()

    for ln in md.splitlines():
        if ln.lstrip().startswith("|"):
            table.append(ln.strip())
            continue
        _flush()
        s = _esc(ln)
        m = _re.match(r"^\s*#{1,6}\s+(.*)$", s)
        if m:
            out.append("<b>" + m.group(1).replace("**", "").strip() + "</b>")
            continue
        s = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        out.append(s)
    _flush()
    return "\n".join(out)


def _notify(job_id):
    """완료 알림(텔레그램). notified 플래그로 1회만 발송."""
    job = get(job_id)
    if not job:
        return
    con = _con()
    try:
        n = con.execute("UPDATE wiki_jobs SET notified=1 WHERE id=? AND notified=0",
                        (job_id,)).rowcount
        con.commit()
    finally:
        con.close()
    if not n:
        return
    token = os.getenv("TELEGRAM_SISYPHE_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    if job["status"] == "succeeded":
        head = "📚 위키 답변 완료"
        ans = job.get("answer") or ""
        body = _md_to_tg_html(ans[:3000])
        if len(ans) > 3000:
            body += "\n…(이하 생략 — 전문은 /wiki 대화 이력)"
    else:
        head = "⚠️ 위키 답변 실패 (%s)" % job["status"]
        body = _esc((job.get("error") or "")[:300])
        if recent_failures(3):
            body += "\n\n★최근 3건 연속 실패 — 구독 쿼터 소진 의심"
    text = "<b>%s</b>\n\nQ. %s\n\n%s" % (head, _esc((job.get("question") or "")[:200]), body)
    if not _send_tg(token, chat, text, parse_mode="HTML"):
        # HTML 파싱 거부 등 → 평문 폴백 (알림 유실 방지)
        plain = "%s\n\nQ. %s\n\n%s" % (head, (job.get("question") or "")[:200],
                                       (job.get("answer") or job.get("error") or "")[:3000])
        _send_tg(token, chat, plain)


def _worker():
    # ★바깥 while 을 try 로 감싼다 — 종전엔 _con()/_notify() 예외 하나로 스레드가
    #   조용히 죽고 큐가 영구 정지했다 (codex 지적).
    while True:
        try:
            _worker_tick()
        except Exception as e:
            print("[wiki_jobs] worker tick 예외: %s: %s" % (type(e).__name__, e), flush=True)
            time.sleep(3)


def _worker_tick():
    while True:
        _wake.wait(timeout=5)
        _wake.clear()
        while True:
            job = _claim_job()
            if not job:
                break
            try:
                _run_one(job)
            except Exception as e:
                print("[wiki_jobs] worker error: %s: %s" % (type(e).__name__, e),
                      flush=True)
            _notify(job["id"])


def init_once():
    """DB 초기화 1회 + 워커 생존 보장.

    ★종전엔 플래그 하나로 '한 번 띄웠다'만 기록해서, 스레드가 죽어도 아무도 몰랐다.
      이제 매 호출마다 살아있는지 확인하고 죽었으면 되살린다 (codex 지적).
    """
    global _worker_thread, _db_ready
    with _lock:
        if not _db_ready:
            init_db()
            _db_ready = True
        if _worker_thread is None or not _worker_thread.is_alive():
            if _worker_thread is not None:
                print("[wiki_jobs] ★워커 스레드가 죽어 있어 재기동합니다", flush=True)
            _worker_thread = threading.Thread(target=_worker, daemon=True, name="wiki-jobs")
            _worker_thread.start()


def worker_alive():
    return _worker_thread is not None and _worker_thread.is_alive()
