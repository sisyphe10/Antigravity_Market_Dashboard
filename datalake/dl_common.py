# -*- coding: utf-8 -*-
"""datalake 공용 헬퍼 — 경로·parquet 병합·KRX 로그인.

모든 datalake 스크립트가 공유한다. 데이터 루트는 env DATALAKE_ROOT
(기본 ~/datalake). 레포 루트는 이 파일 위치에서 self-locate.
"""
import contextlib
import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATALAKE_ROOT = os.path.expanduser(os.getenv("DATALAKE_ROOT", "~/datalake"))

MARKET_DIR = os.path.join(DATALAKE_ROOT, "market")
NOTES_DIR = os.path.join(DATALAKE_ROOT, "research_notes")
SNAP_DIR = os.path.join(DATALAKE_ROOT, "snapshots")
CATALOG_DIR = os.path.join(DATALAKE_ROOT, "catalog")
DUCKDB_PATH = os.path.join(MARKET_DIR, "market.duckdb")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def dataset_dir(name):
    d = os.path.join(MARKET_DIR, name)
    os.makedirs(d, exist_ok=True)
    return d


def year_path(name, year):
    return os.path.join(dataset_dir(name), f"{int(year)}.parquet")


@contextlib.contextmanager
def dataset_lock(name, timeout_sec=1800, stale_sec=7200):
    """데이터셋 단위 프로세스 간 락 (mkdir 원자성 — 백필·daily·수동 실행 동시 쓰기 방지).

    timeout까지 재시도, mtime이 stale_sec 넘은 락은 회수. 실패 시 RuntimeError.
    """
    import time
    lock_dir = os.path.join(dataset_dir(name), ".merge.lock")
    deadline = time.time() + timeout_sec
    while True:
        try:
            os.mkdir(lock_dir)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock_dir) > stale_sec:
                    stale = lock_dir + f".stale.{os.getpid()}"
                    os.rename(lock_dir, stale)
                    os.rmdir(stale)
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                raise RuntimeError(f"{name} 병합 락 획득 실패 ({timeout_sec}s 초과)")
            time.sleep(2)
    try:
        yield
    finally:
        try:
            os.rmdir(lock_dir)
        except OSError:
            pass


def merge_into_year_files(name, df, key_cols):
    """df(반드시 'date' datetime 컬럼 보유)를 연도별 parquet에 upsert.

    같은 key_cols 조합은 새 값으로 대체(self-heal). 데이터셋 락 하에
    원자적 교체(pid 고유 tmp→rename). 반환: {year: (기존행수, 최종행수)}
    """
    import pandas as pd

    if df is None or df.empty:
        return {}
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    out = {}
    with dataset_lock(name):
        for year, chunk in df.groupby(df["date"].dt.year):
            path = year_path(name, year)
            before = 0
            if os.path.exists(path):
                old = pd.read_parquet(path)
                before = len(old)
                merged = pd.concat([old, chunk], ignore_index=True)
            else:
                merged = chunk
            merged = merged.drop_duplicates(subset=key_cols, keep="last")
            merged = merged.sort_values(key_cols).reset_index(drop=True)
            tmp = path + f".{os.getpid()}.tmp"
            merged.to_parquet(tmp, index=False)
            os.replace(tmp, path)
            out[int(year)] = (before, len(merged))
    return out


def load_api_key(name):
    """API 키 로드: env → secrets/api_keys.env → secrets/<NAME>.txt. 값 미출력."""
    key = os.environ.get(name, "").strip()
    if key:
        return key
    candidates = [os.path.join(REPO, "secrets", "api_keys.env"),
                  os.path.join(REPO, "secrets", f"{name}.txt")]
    for path in candidates:
        if not os.path.exists(path):
            continue
        raw = open(path, encoding="utf-8-sig").read().strip()
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith(name):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
        # <NAME>.txt에 키 값만 단독으로 들어있는 경우
        if path.endswith(f"{name}.txt") and raw and "=" not in raw and "\n" not in raw:
            return raw
    return ""


# ───────────────────── KRX 로그인 pykrx ─────────────────────
_KNOWN_ID = {"krx_id", "id", "user", "username", "userid", "login", "loginid"}
_KNOWN_PW = {"krx_pw", "pw", "pass", "password", "passwd", "pwd", "krx_pwd"}


def _load_krx_creds():
    """fetch_krx_valuation.py와 동일 우선순위. 값은 절대 출력 금지."""
    kid = os.environ.get("KRX_ID", "").strip()
    kpw = os.environ.get("KRX_PW", "").strip()
    if kid and kpw:
        return kid, kpw
    path = os.environ.get("KRX_LOGIN_FILE", os.path.join(REPO, "secrets", "data.krx.txt"))
    if not os.path.exists(path):
        return None, None
    try:
        raw = open(path, encoding="utf-8-sig").read()
    except OSError:
        return None, None
    fid = fpw = None
    for line in raw.splitlines():
        m = re.match(r"\s*([A-Za-z_][\w]*)\s*[=:]\s*(.+?)\s*$", line)
        if not m:
            continue
        k, v = m.group(1).lower(), m.group(2).strip().strip('"').strip("'")
        if k in _KNOWN_PW:
            fpw = v
        elif k in _KNOWN_ID:
            fid = v
    if not (fid and fpw):
        toks = [t.strip().strip('"').strip("'")
                for t in re.split(r"[\s:,\r\n\t]+", raw.strip()) if t.strip()]
        if len(toks) >= 2:
            fid, fpw = toks[0], toks[1]
    return (fid, fpw) if (fid and fpw) else (None, None)


def load_pykrx():
    """자격증명 설정 후 pykrx.stock 로드 (import 출력 억제). 실패 시 RuntimeError."""
    kid, kpw = _load_krx_creds()
    if not (kid and kpw):
        raise RuntimeError("KRX 자격증명 없음 (env KRX_ID/KRX_PW 또는 secrets/data.krx.txt)")
    os.environ["KRX_ID"] = kid
    os.environ["KRX_PW"] = kpw
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        from pykrx import stock
    return stock
