# -*- coding: utf-8 -*-
"""뷰어 수집기 공용 헬퍼 — 경로·오늘날짜·원자적 저장·키 로더 (2026-07-22 데일리화).

Windows(개발)·macmini(운영 launchd) 양쪽에서 동작:
- REPO: env DASH_REPO > 플랫폼 기본값 (Windows C:\\... / mac ~/Antigravity_Market_Dashboard)
- 시크릿: env > REPO/secrets/api_keys.env > ~/.secrets/*.env
- 저장: .tmp 작성 후 os.replace — 수집 도중 실패해도 기존 산출물 보존
"""
import os
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("DASH_REPO") or (
    r"C:\Users\user\Antigravity_Market_Dashboard" if os.name == "nt"
    else os.path.expanduser("~/Antigravity_Market_Dashboard"))


def dash_env():
    """대시보드 execution 모듈 import·KRX 인증 파일 경로 준비."""
    import sys
    p = os.path.join(REPO, "execution")
    if p not in sys.path:
        sys.path.insert(0, p)
    os.environ.setdefault("KRX_LOGIN_FILE", os.path.join(REPO, "secrets", "data.krx.txt"))


def today_ymd():
    return date.today().strftime("%Y%m%d")


def atomic_to_csv(df, path, **kw):
    tmp = path + ".tmp"
    df.to_csv(tmp, **kw)
    os.replace(tmp, path)


def atomic_json_dump(obj, path, **kw):
    import json
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, **kw)
    os.replace(tmp, path)


def load_key(name):
    v = os.environ.get(name)
    if v:
        return v
    cands = [os.path.join(REPO, "secrets", "api_keys.env"),
             os.path.join(REPO, ".env")]
    sec = os.path.expanduser("~/.secrets")
    if os.path.isdir(sec):
        cands += [os.path.join(sec, f) for f in sorted(os.listdir(sec)) if f.endswith(".env")]
    for p in cands:
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s.startswith(name + "="):
                        return s.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            continue
    return None
