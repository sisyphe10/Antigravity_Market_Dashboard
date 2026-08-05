# -*- coding: utf-8 -*-
"""Taiwan monthly revenue Telegram alert (Sisyphe-Bot).

Runs right after fetch_taiwan_revenue.py inside launchd gha-taiwan-revenue
(23:20 KST daily). Compares (코드, 날짜) keys in taiwan_revenue.csv against a
local seen-state file and sends one Telegram digest for newly announced
company-months. Each stock gets a second line with the Korean-peer join
(taiwan_universe.csv 한국PEER).

Bullets follow the active-ETF alert convention (boutique_etf/alert.py C안):
'•'+2sp for the stock line, '◦'+1sp for the sub line — proportional-font
alignment fix. (컨센서스 대비 표시는 2026-08-05 사용자 지시로 제거.)

Rules:
  - First run (no state file): seed all current keys silently, send nothing.
  - Backfill guard: only months within RECENT_MONTHS are alertable; older new
    keys (e.g. catch-up full backfill of a newly curated stock) are marked
    seen silently.
  - State is written only after every chunk sent OK -> a failed send
    self-heals on the next daily run (duplicates possible only if a
    multi-chunk send fails midway, which is accepted).
  - Value restatements (self-heal re-fetch) do not alert; key is company-month.

Env (loaded by run_gha_job.sh .env parser): TELEGRAM_SISYPHE_BOT_TOKEN,
TELEGRAM_CHAT_ID. Missing env -> exit 0 with a log line (no hard failure).
"""
import csv
import html
import json
import os
import sys
import tempfile
from datetime import date

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "taiwan_revenue.csv")
UNIVERSE_CSV = os.path.join(ROOT, "taiwan_universe.csv")
STATE_PATH = os.path.join(ROOT, "logs", "launchd", "state",
                          "taiwan_revenue_alert_seen.json")
RECENT_MONTHS = 5          # alert window for 날짜 (YYYY-MM)
CHUNK_LIMIT = 3800         # telegram hard limit 4096, keep headroom
API = "https://api.telegram.org/bot{token}/sendMessage"

BULLET1 = "•"   # • 1단계(종목) — boutique_etf/alert.py 규약 공유
BULLET2 = "◦"   # ◦ 2단계(PEER) — 속 빈 점
GAP1 = "  "          # ◦ 가 • 보다 넓어 1단계만 공백 2칸(첫 글자 위치 정렬)
GAP2 = " "


def month_key(code, ym):
    return f"{code}|{ym}"


def load_rows():
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_state():
    if not os.path.exists(STATE_PATH):
        return None
    with open(STATE_PATH, encoding="utf-8") as f:
        return set(json.load(f)["seen"])


def save_state(seen):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STATE_PATH), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"seen": sorted(seen)}, f, ensure_ascii=False)
    os.replace(tmp, STATE_PATH)


def recent_cutoff_ym(today=None):
    """YYYY-MM string RECENT_MONTHS months before today (inclusive window)."""
    t = today or date.today()
    total = t.year * 12 + (t.month - 1) - (RECENT_MONTHS - 1)
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def load_peers():
    """코드 -> 한국PEER from taiwan_universe.csv (render-time join, like taiwan_table)."""
    try:
        with open(UNIVERSE_CSV, encoding="utf-8-sig", newline="") as f:
            return {row["코드"]: (row.get("한국PEER") or "").strip()
                    for row in csv.DictReader(f)}
    except OSError:
        return {}


PEERS = load_peers()


def fmt_lines(r):
    name = html.escape(r["기업명"])
    cls = html.escape(r["분류"]) if r.get("분류") else ""
    try:
        rev = f'{float(r["매출_TWD"]) / 1e8:,.1f}억TWD'
    except (TypeError, ValueError):
        rev = "-"
    parts = [name + (f' ({cls})' if cls else '') + f' {rev}']
    for label, col in (("YoY", "YoY(%)"), ("MoM", "MoM(%)")):
        v = (r.get(col) or "").strip()
        if v:
            parts.append(f'{label} {v}%')
    lines = [BULLET1 + GAP1 + " | ".join(parts)]
    peer = PEERS.get(r["코드"], "")
    if peer:
        lines.append(BULLET2 + GAP2 + f'PEER {html.escape(peer)}')
    return lines


def build_messages(rows):
    """rows -> list of telegram-sized HTML chunks, grouped by month desc."""
    by_month = {}
    for r in rows:
        by_month.setdefault(r["날짜"], []).append(r)
    blocks = [f"\U0001F1F9\U0001F1FC 대만 월매출 업데이트 ({len(rows)}건)"]
    for ym in sorted(by_month, reverse=True):
        month_rows = sorted(by_month[ym],
                            key=lambda r: -float(r["매출_TWD"] or 0))
        y, m = ym.split("-")
        lines = [f"<b><u>{y}년 {int(m)}월분 ({len(month_rows)}건)</u></b>"]
        for r in month_rows:
            lines += fmt_lines(r)
        blocks.append("\n".join(lines))
    msgs, cur = [], ""
    for b in blocks:
        cand = (cur + "\n\n" + b) if cur else b
        if len(cand) > CHUNK_LIMIT and cur:
            msgs.append(cur)
            cur = b
        else:
            cur = cand
    if cur:
        msgs.append(cur)
    return msgs


def send(token, chat_id, text):
    r = requests.post(API.format(token=token),
                      data={"chat_id": chat_id, "parse_mode": "HTML",
                            "text": text},
                      timeout=30)
    ok = r.status_code == 200 and r.json().get("ok")
    if not ok:
        print(f"[taiwan-alert] send 실패 status={r.status_code} "
              f"body={r.text[:200]}", file=sys.stderr)
    return ok


def main():
    rows = load_rows()
    keys_now = {month_key(r["코드"], r["날짜"]) for r in rows}
    seen = load_state()
    if seen is None:
        save_state(keys_now)
        print(f"[taiwan-alert] 상태 파일 최초 생성(발송 없음): "
              f"{len(keys_now)}키 seed")
        return 0

    new_keys = keys_now - seen
    if not new_keys:
        print("[taiwan-alert] 신규 발표 없음")
        return 0

    cutoff = recent_cutoff_ym()
    alertable = [r for r in rows
                 if month_key(r["코드"], r["날짜"]) in new_keys
                 and r["날짜"] >= cutoff]
    stale_keys = {k for k in new_keys if k.split("|", 1)[1] < cutoff}
    if not alertable:
        save_state(seen | new_keys)
        print(f"[taiwan-alert] 신규 {len(new_keys)}키 전부 {cutoff} 이전 "
              f"(백필) — 무발송 처리")
        return 0

    token = os.environ.get("TELEGRAM_SISYPHE_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[taiwan-alert] TELEGRAM env 미설정 — 발송 스킵(상태 미변경)",
              file=sys.stderr)
        return 0

    msgs = build_messages(alertable)
    for m in msgs:
        if not send(token, chat_id, m):
            return 1
    save_state(seen | new_keys)
    print(f"[taiwan-alert] 발송 완료: 신규 {len(alertable)}건"
          + (f" (+백필 {len(stale_keys)}키 무발송)" if stale_keys else "")
          + f", 메시지 {len(msgs)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
