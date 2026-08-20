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


def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


# headless(구독 Claude Code) 엔진 — API 는 백업(OCR_ENGINE=api, 유료 = 사전 승인 필수, 8/20)
OCR_ENGINE = os.getenv("OCR_ENGINE", "headless")            # headless | api(롤백)
OCR_HEADLESS_MODEL = os.getenv("OCR_HEADLESS_MODEL", "claude-sonnet-5")
OCR_HEADLESS_TIMEOUT = _env_int("OCR_HEADLESS_TIMEOUT", 180)
OCR_HEADLESS_MAX_ITEMS = _env_int("OCR_HEADLESS_MAX_ITEMS", 200)
MAX_B64_CHARS = 7_000_000   # stream-json 페이로드 가드 (~5MB 원본 상당)
OCR_SYSTEM = "당신은 이미지 속 텍스트를 정확히 옮겨 적는 OCR 도우미다. 사용자 지시를 그대로 따른다."
MAX_EDGE = 1568                       # 비전 다운스케일 상한 (초과분만 축소)
IMG_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
               ".gif": "image/gif", ".webp": "image/webp"}

# ★PROMPT(지시) 변경 시 PROMPT_VER 를 반드시 bump — 캐시 키 v2 에서 모델명은 제거됨
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


def _headless():
    """어닝봇 headless 어댑터 재사용 (8/18 검증분 — call_multimodal·preflight·예외 위계)."""
    hd = os.path.join(REPO, "execution", "earnings_bot")
    if hd not in sys.path:
        sys.path.insert(0, hd)
    import headless_llm
    return headless_llm


def migrate_cache_keys_v2(st):
    """v1 키 sha(file_sha, PROMPT_VER, model) → v2 sha(file_sha, PROMPT_VER) 무LLM 제자리 이관.
    정확한 v1 기대키가 일치하는 succeeded 행만 갱신 — 재OCR 0건. 멱등."""
    n = 0
    rows = st.execute("SELECT message_id, file_sha, cache_key, model FROM ocr_items"
                      " WHERE status='succeeded'").fetchall()
    for r in rows:
        base_model = (r["model"] or "").split("@", 1)[0]
        if r["cache_key"] == sha(r["file_sha"], PROMPT_VER, base_model):
            st.execute("UPDATE ocr_items SET cache_key=? WHERE message_id=?",
                       (sha(r["file_sha"], PROMPT_VER), r["message_id"]))
            n += 1
    if n:
        st.commit()
        print("캐시 키 이관(v1→v2): %d건 — 재OCR 없음" % n)
    return n


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

    if OCR_ENGINE not in ("headless", "api"):
        sys.exit("OCR_ENGINE=%s 지원 안 함 (headless|api)" % OCR_ENGINE)

    lock = _acquire_lock()
    if lock is None:
        sys.exit("다른 ocr_worker 가 실행 중 — 종료")

    src = sqlite3.connect("file:%s?mode=ro" % DB_SRC, uri=True)
    src.row_factory = sqlite3.Row
    st = open_state()
    if not args.dry_run:
        migrate_cache_keys_v2(st)   # --dry-run 은 무부작용 계약 — 이관도 하지 않는다

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
        # 캐시 키 v2 — 모델명 제거 (엔진 전환이 캐시를 무효화하지 않게, tag_worker 8/5 정책 승계)
        ck = sha(fs, PROMPT_VER)
        cur = st.execute("SELECT cache_key,status FROM ocr_items WHERE message_id=?",
                         (r["id"],)).fetchone()
        if cur and cur["cache_key"] == ck and cur["status"] == "succeeded":
            cached += 1
            continue
        r["_path"], r["_fs"], r["_ck"] = path, fs, ck
        todo.append(r)
    if args.max_items:
        todo = todo[:args.max_items]

    print("대상 %d건 (캐시 재사용 %d · 파일 없음 %d) / 엔진 %s / 모델 %s"
          % (len(todo), cached, missing, OCR_ENGINE,
             OCR_HEADLESS_MODEL if OCR_ENGINE == "headless" else MODEL))
    if args.dry_run or not todo:
        # --retry-failed 대상 0건 등은 정상 종료 (일일 잡 rc 오염 방지)
        return

    if OCR_ENGINE == "headless":
        if len(todo) > OCR_HEADLESS_MAX_ITEMS:
            print("[차단] 대상 %d건 > 상한 %d — 대량 무효화 의심"
                  " (해제는 OCR_HEADLESS_MAX_ITEMS 상향으로만)"
                  % (len(todo), OCR_HEADLESS_MAX_ITEMS))
            sys.exit(78)
        hl = _headless()
        try:
            hl.preflight()
        except Exception as e:  # HeadlessAuthError 포함 — 호출 0회로 즉시 중단
            print("[중단] headless 인증 preflight 실패 — H7: %s" % str(e)[:160])
            sys.exit(75)
        client = None
        engine_errors = (hl.HeadlessAuthError, hl.HeadlessQuotaError)
        fail_model = OCR_HEADLESS_MODEL + "@headless"
    else:
        import anthropic
        client = anthropic.Anthropic(api_key=load_env_key())
        hl = None
        engine_errors = ()
        fail_model = MODEL
    ok = fail = tin = tout = 0
    engine_down = False
    for i, r in enumerate(todo, 1):
        day = r["timestamp"][:10]
        try:
            b64, mt = encode_image(r["_path"])
            if len(b64) > MAX_B64_CHARS:
                raise ValueError("이미지 페이로드 과대 (b64 %d chars)" % len(b64))
            if hl is not None:
                res = hl.call_multimodal(
                    OCR_SYSTEM,
                    [{"type": "image",
                      "source": {"type": "base64", "media_type": mt, "data": b64}},
                     {"type": "text", "text": PROMPT}],
                    model=OCR_HEADLESS_MODEL, timeout_sec=OCR_HEADLESS_TIMEOUT)
                text = res["text"]
                # 실입력 대부분은 cacheCreationInputTokens 에 계상 (8/18 실측)
                in_tok = res["input_tokens"] + res["cache_creation_input_tokens"]
                out_tok = res["output_tokens"]
                used_model = res["resolved_model"] + "@headless"
            else:
                text, usage = call_ocr(client, b64, mt)
                in_tok, out_tok = usage.input_tokens, usage.output_tokens
                used_model = MODEL
            tin += in_tok
            tout += out_tok
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
                 text, used_model, in_tok, out_tok, now()))
            ok += 1
        except engine_errors as e:
            # 인증·쿼터 장애 — 항목 실패로 기록하지 않고 즉시 중단 (다음 실행에서 자연 회수)
            print("  [중단] 엔진 장애: %s" % str(e)[:180])
            engine_down = True
            break
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
                 str(e)[:500], fail_model, now()))
            fail += 1
        st.commit()
        if i % 25 == 0 or i == len(todo):
            print("  %d/%d  ok=%d fail=%d  in=%s out=%s"
                  % (i, len(todo), ok, fail, f"{tin:,}", f"{tout:,}"))
        time.sleep(0.2)

    print("완료: ok=%d fail=%d / 입력 %s · 출력 %s 토큰" % (ok, fail, f"{tin:,}", f"{tout:,}"))
    if engine_down:
        sys.exit(75)
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
