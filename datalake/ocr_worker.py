# -*- coding: utf-8 -*-
"""리서치노트 이미지 OCR 워커 — 캐시 정본 ocr_state.sqlite, md는 투영.

research_notes.db 의 사진/이미지 첨부를 Haiku 비전으로 옮겨 적는다(표 포함).
같은 파일은 두 번 호출하지 않는다 (캐시 키 = 파일 sha + 프롬프트 버전 + 모델).
산출은 export_research_notes.py(md 투영)와 tag_worker.py(태깅 입력)가 소비한다.

tag_worker 와 동일한 설계 원칙: exporter 는 매일 어제+오늘을 통째로 재생성하는
멱등 구조라 LLM 을 넣으면 재과금된다 — 정본은 이 캐시, md 는 투영만.

사용:
  venv/bin/python3 datalake/ocr_worker.py                     # 미처리 전량
  venv/bin/python3 datalake/ocr_worker.py --date 2026-07-30
  venv/bin/python3 datalake/ocr_worker.py --dry-run           # 견적만 (DB 무부작용)
  venv/bin/python3 datalake/ocr_worker.py --retry-failed
"""
import argparse
import base64
import datetime as dt
import fcntl
import hashlib
import io
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dl_common import NOTES_DIR, REPO  # noqa: E402
from export_research_notes import resolve_media_path  # noqa: E402

DB_SRC = os.path.join(REPO, "execution", "research_bot", "research_notes.db")
STATE_PATH = os.path.join(NOTES_DIR, "ocr_state.sqlite")
LOCK_PATH = os.path.join(NOTES_DIR, "ocr_state.lock")

MODEL = os.getenv("OCR_MODEL", "claude-haiku-4-5")
PROMPT_VER = "ocr-v1"
MAX_ATTEMPTS = 3
MAX_EDGE = 1568                       # 비전 다운스케일 상한 (초과분만 축소)
IMG_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
               ".gif": "image/gif", ".webp": "image/webp"}

PROMPT = (
    "이미지는 한국 주식 리서치 텔레그램 채널에 공유된 자료다.\n"
    "1) 이미지 안에 텍스트가 있으면 그대로 옮겨 적어라 (요약 금지, 표는 마크다운 표로).\n"
    "2) 텍스트가 거의 없는 차트·사진이면 무엇을 보여주는지 1~2문장으로만 기술하라.\n"
    "옮겨 적기/기술 외의 해설·의견은 쓰지 마라. 원문이 한국어면 한국어로, 영어면 영어 그대로."
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS ocr_items (
  message_id INTEGER PRIMARY KEY,
  day TEXT, media_file TEXT, file_sha TEXT, cache_key TEXT,
  status TEXT, ocr_text TEXT, error TEXT, attempts INTEGER DEFAULT 0,
  model TEXT, in_tokens INTEGER, out_tokens INTEGER, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ocr_day ON ocr_items(day);
"""


def load_env_key(name="ANTHROPIC_API_KEY"):
    if os.getenv(name):
        return os.getenv(name)
    path = os.path.join(REPO, ".env")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    raise RuntimeError("%s not found (env or .env)" % name)


def sha(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()[:20]


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def _acquire_lock():
    fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:20]


def encode_image(path):
    """(b64, media_type). 장변 1568 초과·gif/webp 는 JPEG 로 재인코딩."""
    ext = os.path.splitext(path)[1].lower()
    data = open(path, "rb").read()
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        if max(im.size) > MAX_EDGE or ext in (".gif", ".webp"):
            im.thumbnail((MAX_EDGE, MAX_EDGE))
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="JPEG", quality=88)
            return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"
    except Exception:  # noqa: BLE001 — PIL 실패 시 원본 그대로
        pass
    return base64.standard_b64encode(data).decode(), MEDIA_TYPES.get(ext, "image/jpeg")


def call_ocr(client, b64, media_type, max_retries=4):
    last = None
    for attempt in range(max_retries):
        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=3000,
                messages=[{"role": "user", "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": PROMPT},
                ]}])
            text = "".join(c.text for c in resp.content
                           if getattr(c, "type", None) == "text").strip()
            return text, resp.usage
        except Exception as e:  # noqa: BLE001
            last = e
            msg = str(e).lower()
            if "rate" in msg or "overloaded" in msg or "529" in msg or "429" in msg:
                time.sleep(min(60, 2 ** attempt * 5))
                continue
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            break
    raise last


def open_state():
    st = sqlite3.connect(STATE_PATH)
    st.row_factory = sqlite3.Row
    st.executescript(SCHEMA)
    return st


def pick_targets(src, args):
    q = ("SELECT id, timestamp, media_path FROM messages"
         " WHERE message_type IN ('photo','document') AND media_path IS NOT NULL")
    params = []
    if args.date:
        q += " AND timestamp LIKE ?"
        params.append(args.date + "%")
    q += " ORDER BY timestamp, id"
    rows = [dict(r) for r in src.execute(q, params)]
    return [r for r in rows if (r["media_path"] or "").lower().endswith(IMG_EXTS)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--max-items", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--retry-failed", action="store_true")
    args = ap.parse_args()

    lock = _acquire_lock()
    if lock is None:
        sys.exit("다른 ocr_worker 가 실행 중 — 종료")

    src = sqlite3.connect("file:%s?mode=ro" % DB_SRC, uri=True)
    src.row_factory = sqlite3.Row
    st = open_state()

    rows = pick_targets(src, args)
    if args.retry_failed:
        bad = {r["message_id"] for r in st.execute(
            "SELECT message_id FROM ocr_items WHERE status IN ('failed','dead_letter')")}
        rows = [r for r in rows if r["id"] in bad]

    todo, cached, missing = [], 0, 0
    for r in rows:
        path = resolve_media_path(r["media_path"])
        if not path:
            missing += 1
            continue
        fs = file_sha(path)
        ck = sha(fs, PROMPT_VER, MODEL)
        cur = st.execute("SELECT cache_key,status FROM ocr_items WHERE message_id=?",
                         (r["id"],)).fetchone()
        if cur and cur["cache_key"] == ck and cur["status"] == "succeeded":
            cached += 1
            continue
        r["_path"], r["_fs"], r["_ck"] = path, fs, ck
        todo.append(r)
    if args.max_items:
        todo = todo[:args.max_items]

    print("대상 %d건 (캐시 재사용 %d · 파일 없음 %d) / 모델 %s"
          % (len(todo), cached, missing, MODEL))
    if args.dry_run or not todo:
        # --retry-failed 대상 0건 등은 정상 종료 (일일 잡 rc 오염 방지)
        return

    import anthropic
    client = anthropic.Anthropic(api_key=load_env_key())
    ok = fail = tin = tout = 0
    for i, r in enumerate(todo, 1):
        day = r["timestamp"][:10]
        try:
            b64, mt = encode_image(r["_path"])
            text, usage = call_ocr(client, b64, mt)
            tin += usage.input_tokens
            tout += usage.output_tokens
            st.execute(
                "INSERT INTO ocr_items (message_id,day,media_file,file_sha,cache_key,"
                " status,ocr_text,error,attempts,model,in_tokens,out_tokens,updated_at)"
                " VALUES (?,?,?,?,?,'succeeded',?,NULL,0,?,?,?,?)"
                " ON CONFLICT(message_id) DO UPDATE SET day=excluded.day,"
                " media_file=excluded.media_file, file_sha=excluded.file_sha,"
                " cache_key=excluded.cache_key, status='succeeded',"
                " ocr_text=excluded.ocr_text, error=NULL, attempts=0,"
                " model=excluded.model, in_tokens=excluded.in_tokens,"
                " out_tokens=excluded.out_tokens, updated_at=excluded.updated_at",
                (r["id"], day, os.path.basename(r["_path"]), r["_fs"], r["_ck"],
                 text, MODEL, usage.input_tokens, usage.output_tokens, now()))
            ok += 1
        except Exception as e:  # noqa: BLE001
            st.execute(
                "INSERT INTO ocr_items (message_id,day,media_file,file_sha,cache_key,"
                " status,ocr_text,error,attempts,model,updated_at)"
                " VALUES (?,?,?,?,?,'failed',NULL,?,1,?,?)"
                " ON CONFLICT(message_id) DO UPDATE SET attempts=attempts+1,"
                " error=excluded.error, updated_at=excluded.updated_at,"
                " status=CASE WHEN attempts+1>=%d THEN 'dead_letter' ELSE 'failed' END"
                % MAX_ATTEMPTS,
                (r["id"], day, os.path.basename(r["_path"]), r["_fs"], r["_ck"],
                 str(e)[:500], MODEL, now()))
            fail += 1
        st.commit()
        if i % 25 == 0 or i == len(todo):
            print("  %d/%d  ok=%d fail=%d  in=%s out=%s"
                  % (i, len(todo), ok, fail, f"{tin:,}", f"{tout:,}"))
        time.sleep(0.2)

    print("완료: ok=%d fail=%d / 입력 %s · 출력 %s 토큰" % (ok, fail, f"{tin:,}", f"{tout:,}"))
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
