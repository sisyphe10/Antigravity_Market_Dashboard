# -*- coding: utf-8 -*-
"""Taiwan monthly revenue Telegram alert (Sisyphe-Bot).

Runs right after fetch_taiwan_revenue.py inside launchd gha-taiwan-revenue
(23:20 KST daily). Compares (코드, 날짜) keys in taiwan_revenue.csv against a
local seen-state file and sends one Telegram digest for newly announced
company-months. Each line carries the Korean-peer join (taiwan_universe.csv)
and, when Yahoo covers the name, quarter-to-date progress vs the quarterly
revenue consensus.

Rules:
  - First run (no state file): seed all current keys silently, send nothing.
  - Backfill guard: only months within RECENT_MONTHS are alertable; older new
    keys (e.g. catch-up full backfill of a newly curated stock) are marked
    seen silently.
  - State is written only after every chunk sent OK -> a failed send
    self-heals on the next daily run (duplicates possible only if a
    multi-chunk send fails midway, which is accepted).
  - Value restatements (self-heal re-fetch) do not alert; key is company-month.
  - Consensus: Yahoo has no monthly-revenue consensus, so we show
    QTD(발표월까지 누적 월매출) / 분기 매출 컨센서스(avg). Yahoo's "0q" row is
    anchored to (last reported quarter + 1) — verified vs earnings dates; if
    the announced month's quarter is beyond +1q (stale small-cap data) or the
    fetch fails, the consensus part is silently omitted. Fetches are capped by
    CONSENSUS_TIME_CAP so the digest never stalls the job watchdog.

Env (loaded by run_gha_job.sh .env parser): TELEGRAM_SISYPHE_BOT_TOKEN,
TELEGRAM_CHAT_ID. Missing env -> exit 0 with a log line (no hard failure).
"""
import csv
import html
import json
import os
import sys
import tempfile
import time
from datetime import date

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "taiwan_revenue.csv")
UNIVERSE_CSV = os.path.join(ROOT, "taiwan_universe.csv")
STATE_PATH = os.path.join(ROOT, "logs", "launchd", "state",
                          "taiwan_revenue_alert_seen.json")
RECENT_MONTHS = 5          # alert window for 날짜 (YYYY-MM)
CHUNK_LIMIT = 3800         # telegram hard limit 4096, keep headroom
CONSENSUS_TIME_CAP = 240   # sec; stop further yahoo fetches past this budget
API = "https://api.telegram.org/bot{token}/sendMessage"


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


def _qidx(ym):
    """Linear quarter index of 'YYYY-MM'."""
    y, m = ym.split("-")
    return int(y) * 4 + (int(m) - 1) // 3


def consensus_progress(code, market, ym, stock_rows):
    """'분기컨센 대비 34.1% (1/3개월, 8명)' or '' when not derivable.

    stock_rows: all CSV rows of this stock (QTD sum over the target quarter).
    """
    try:
        import yfinance as yf
    except ImportError:
        return ""
    try:
        ticker = code + (".TW" if market == "상장" else ".TWO")
        t = yf.Ticker(ticker)
        qis = t.quarterly_income_stmt
        if qis is None or qis.empty:
            return ""
        anchor = max(c.year * 4 + (c.month - 1) // 3 for c in qis.columns) + 1
        off = _qidx(ym) - anchor
        if off not in (0, 1):
            return ""
        est = t.revenue_estimate
        key = "0q" if off == 0 else "+1q"
        if est is None or est.empty or key not in est.index:
            return ""
        avg = est.loc[key].get("avg")
        n = est.loc[key].get("numberOfAnalysts")
        if avg is None or avg != avg or avg <= 0:
            return ""
        qtd = [r for r in stock_rows
               if _qidx(r["날짜"]) == _qidx(ym) and r["날짜"] <= ym]
        total = sum(float(r["매출_TWD"] or 0) for r in qtd)
        if total <= 0:
            return ""
        n_txt = f", {int(n)}명" if n and n == n else ""
        return (f"분기컨센 대비 {total / avg * 100:.1f}% "
                f"({len(qtd)}/3개월{n_txt})")
    except Exception as e:
        print(f"[taiwan-alert] consensus skip {code}: {type(e).__name__} {e}",
              file=sys.stderr)
        return ""


def fmt_lines(r, cons):
    name = html.escape(r["기업명"])
    cls = html.escape(r["분류"]) if r.get("분류") else ""
    try:
        rev = f'{float(r["매출_TWD"]) / 1e8:,.1f}억TWD'
    except (TypeError, ValueError):
        rev = "-"
    parts = [f'· {name}' + (f' ({cls})' if cls else '') + f' {rev}']
    for label, col in (("YoY", "YoY(%)"), ("MoM", "MoM(%)")):
        v = (r.get(col) or "").strip()
        if v:
            parts.append(f'{label} {v}%')
    lines = [" | ".join(parts)]
    extras = []
    peer = PEERS.get(r["코드"], "")
    if peer:
        extras.append(f'PEER {html.escape(peer)}')
    if cons:
        extras.append(cons)
    if extras:
        lines.append("   ↳ " + " · ".join(extras))
    return lines


def build_messages(alert_rows, all_rows):
    """alert rows -> telegram-sized HTML chunks, grouped by month desc."""
    by_code = {}
    for r in all_rows:
        by_code.setdefault(r["코드"], []).append(r)
    by_month = {}
    for r in alert_rows:
        by_month.setdefault(r["날짜"], []).append(r)

    t0 = time.monotonic()
    blocks = [f"\U0001F1F9\U0001F1FC 대만 월매출 업데이트 ({len(alert_rows)}건)"]
    for ym in sorted(by_month, reverse=True):
        month_rows = sorted(by_month[ym],
                            key=lambda r: -float(r["매출_TWD"] or 0))
        y, m = ym.split("-")
        lines = [f"<b><u>{y}년 {int(m)}월분 ({len(month_rows)}건)</u></b>"]
        for r in month_rows:
            cons = ""
            if time.monotonic() - t0 < CONSENSUS_TIME_CAP:
                cons = consensus_progress(r["코드"], r.get("시장", ""),
                                          ym, by_code.get(r["코드"], []))
            lines += fmt_lines(r, cons)
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

    msgs = build_messages(alertable, rows)
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
