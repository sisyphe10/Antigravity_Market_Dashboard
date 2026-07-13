# -*- coding: utf-8 -*-
"""mirror_sheets.py — Google Sheets → datalake CSV 미러 (가계부 Phase 0+2 폴링).

시지프·선유듀오 스프레드시트의 **모든 탭**을 ~/datalake/sheets/<시트>/<탭>.csv 로
전량 미러한다. 20분 주기 launchd(datalake-sheets-mirror)로 돌며, 매회 전체
덮어쓰기(멱등)·원자적 쓰기(tmp→os.replace). 시점 이력은 주 1회 datalake 백업
repo push 가 보존한다. 시트에서 삭제된 탭의 잔존 csv 는 정리한다.

인증 = repo .env 의 GOOGLE_SERVICE_ACCOUNT_KEY (sisyphe 봇과 동일 서비스계정,
여기서는 spreadsheets.readonly 스코프로 읽기만).
"""
import csv
import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dl_common import DATALAKE_ROOT, REPO  # noqa: E402

SHEETS = {
    # 폴더명: (스프레드시트 ID, 설명)
    "sisyphe": ("1V41yiwO4VrVUhjhqHyu8JGsuGcqw6pZen0NHdxzXHGs", "시지프 가계부·운동"),
    "seonyuduo": ("1w6q3UwUER7oINuk50LyMzgF2K0Fbt2wgSVJ34vImo0g", "선유듀오 공유 가계부"),
}
OUT_ROOT = os.path.join(DATALAKE_ROOT, "sheets")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def load_service_account_info():
    """repo .env 에서 GOOGLE_SERVICE_ACCOUNT_KEY(홑따옴표 원문 JSON)를 파싱."""
    env_path = os.path.join(REPO, ".env")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("GOOGLE_SERVICE_ACCOUNT_KEY="):
                continue
            val = line.split("=", 1)[1].strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                val = val[1:-1]
            return json.loads(val)
    raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_KEY not found in .env")


def safe_filename(name):
    """탭 이름 → 파일명 (한글 유지, OS 금지문자만 치환)."""
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "_unnamed"


def atomic_write_csv(path, rows):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows(rows)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def mirror_one(svc, folder, sheet_id):
    meta = svc.spreadsheets().get(
        spreadsheetId=sheet_id, fields="sheets.properties.title"
    ).execute()
    titles = [s["properties"]["title"] for s in meta.get("sheets", [])]
    out_dir = os.path.join(OUT_ROOT, folder)
    written = []
    for title in titles:
        rng = "'" + title.replace("'", "''") + "'"
        values = svc.spreadsheets().values().get(
            spreadsheetId=sheet_id, range=rng,
            valueRenderOption="FORMATTED_VALUE",
        ).execute().get("values", [])
        fname = safe_filename(title) + ".csv"
        atomic_write_csv(os.path.join(out_dir, fname), values)
        written.append(fname)
        print(f"[mirror] {folder}/{fname}: {len(values)}행")
    # 시트에서 사라진 탭의 잔존 csv 정리
    if os.path.isdir(out_dir):
        for f in os.listdir(out_dir):
            if f.endswith(".csv") and f not in written:
                os.remove(os.path.join(out_dir, f))
                print(f"[mirror] {folder}/{f}: 시트에 없는 탭 — 제거")
    return len(written)


def main():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_info(
        load_service_account_info(), scopes=SCOPES
    )
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

    errors = []
    for folder, (sheet_id, desc) in SHEETS.items():
        for attempt in range(3):  # 일시 장애(read timeout 등)는 재시도로 흡수 — 알림은 3회 연속 실패만
            try:
                n = mirror_one(svc, folder, sheet_id)
                print(f"[mirror] {folder}({desc}): 탭 {n}개 완료")
                break
            except Exception as e:  # noqa: BLE001 — 시트 단위 격리, 실패는 집계 후 비정상 종료
                if attempt < 2:
                    print(f"[mirror] {folder} {attempt + 1}차 실패, 재시도: {e}", file=sys.stderr)
                    time.sleep(15 * (attempt + 1))
                else:
                    errors.append(f"{folder}: {e}")
                    print(f"[mirror] {folder} 실패: {e}", file=sys.stderr)
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
