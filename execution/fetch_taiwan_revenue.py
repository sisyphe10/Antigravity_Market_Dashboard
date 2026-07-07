# -*- coding: utf-8 -*-
"""Taiwan monthly revenue collector (FinMind primary, TWSE/TPEx official cross-check).

Modes:
  python execution/fetch_taiwan_revenue.py                # incremental: rolling re-fetch of recent months
  python execution/fetch_taiwan_revenue.py --backfill     # full history from 2016-01
  python execution/fetch_taiwan_revenue.py --crosscheck   # compare CSV vs official TWSE/TPEx snapshot (log only)

Output: taiwan_revenue.csv (repo root, utf-8-sig), one row per company-month,
sorted by (날짜, 발표일, 코드) so newly announced months append at the bottom.

Auth (all optional — anonymous works at 300 req/hr):
  FINMIND_USER / FINMIND_PASSWORD  -> POST /api/v4/login for a fresh token (survives 7-day token expiry)
  FINMIND_TOKEN                    -> used as-is
  Locally, C:/Users/user/.secrets/finmind_api_keys.env is loaded if present.
"""
import argparse
import csv
import os
import sys
import time
from datetime import date, timedelta

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "taiwan_revenue.csv")
UNIVERSE_CSV = os.path.join(ROOT, "taiwan_universe.csv")
SECRETS_ENV = r"C:\Users\user\.secrets\finmind_api_keys.env"

API_DATA = "https://api.finmindtrade.com/api/v4/data"
API_LOGIN = "https://api.finmindtrade.com/api/v4/login"
TWSE_SNAPSHOT = "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"
TPEX_SNAPSHOT = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"

BACKFILL_START = "2016-01-01"
BACKFILL_MIN_MONTH = "2016-01"
ROLLING_DAYS = 100          # incremental window: re-fetch recent months to self-heal restatements
PACING_SEC = 0.35
RETRIES = 3

COLUMNS = ["날짜", "발표일", "코드", "기업명", "시장", "섹터", "분류",
           "매출_TWD", "MoM(%)", "YoY(%)", "누계YoY(%)"]


def load_universe():
    """Curation list from taiwan_universe.csv (user-editable, like universe_tickers.csv)."""
    with open(UNIVERSE_CSV, encoding="utf-8-sig", newline="") as f:
        stocks = list(csv.DictReader(f))
    codes = [s["코드"] for s in stocks]
    assert len(codes) == len(set(codes)), "duplicate stock code in taiwan_universe.csv"
    return stocks


TAIWAN_STOCKS = load_universe()
STOCK_META = {s["코드"]: s for s in TAIWAN_STOCKS}


def _load_secrets_env():
    """Load KEY=VALUE lines from the local secrets file into os.environ (local runs only)."""
    if not os.path.exists(SECRETS_ENV):
        return
    with open(SECRETS_ENV, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def resolve_token():
    """Fresh login token > static token > anonymous."""
    _load_secrets_env()
    user, pw = os.environ.get("FINMIND_USER"), os.environ.get("FINMIND_PASSWORD")
    if user and pw:
        try:
            r = requests.post(API_LOGIN, data={"user_id": user, "password": pw}, timeout=30)
            tok = r.json().get("token")
            if tok:
                print("[auth] fresh token via login API")
                return tok
            print(f"[auth] login failed ({r.json().get('msg')}), falling back")
        except Exception as e:
            print(f"[auth] login error ({e}), falling back")
    tok = os.environ.get("FINMIND_TOKEN")
    if tok:
        print("[auth] static FINMIND_TOKEN")
        return tok
    print("[auth] anonymous (300 req/hr)")
    return None


def fetch_stock(code, start_date, token):
    """One stock's monthly revenue rows from FinMind. Returns list of dicts or None on failure."""
    params = {"dataset": "TaiwanStockMonthRevenue", "data_id": code, "start_date": start_date}
    if token:
        params["token"] = token
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(API_DATA, params=params, timeout=30)
            body = r.json()
            if r.status_code == 200 and body.get("status") == 200:
                return body.get("data", [])
            # 402 = rate limit on FinMind side
            print(f"[fetch] {code} attempt {attempt}: HTTP {r.status_code} / {body.get('msg')}")
        except Exception as e:
            print(f"[fetch] {code} attempt {attempt}: {e}")
        time.sleep(2 * attempt)
    return None


def read_existing():
    rows = {}
    if not os.path.exists(CSV_PATH):
        return rows
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        for rec in csv.DictReader(f):
            rows[(rec["코드"], rec["날짜"])] = rec
    return rows


def merge(existing, code, api_rows):
    """Merge API rows into existing dict. New revenue wins (restatement self-heal);
    발표일 is first-seen and never overwritten once set."""
    changed = 0
    for d in api_rows:
        ym = f"{d['revenue_year']}-{d['revenue_month']:02d}"
        if ym < BACKFILL_MIN_MONTH:
            continue
        key = (code, ym)
        old = existing.get(key)
        ann = (d.get("create_time") or "").strip()
        if old is None:
            m = STOCK_META[code]
            existing[key] = {"날짜": ym, "발표일": ann, "코드": code, "기업명": m["기업명"],
                             "시장": m["시장"], "섹터": m["섹터"], "분류": m["분류"],
                             "매출_TWD": str(int(d["revenue"]))}
            changed += 1
        else:
            new_rev = str(int(d["revenue"]))
            if old["매출_TWD"] != new_rev:
                print(f"[restate] {code} {ym}: {old['매출_TWD']} -> {new_rev}")
                old["매출_TWD"] = new_rev
                changed += 1
            if not old.get("발표일") and ann:
                old["발표일"] = ann
    return changed


def compute_derived(rows):
    """Recompute MoM/YoY/cumulative-YoY across each stock's full series."""
    by_stock = {}
    for (code, ym), rec in rows.items():
        y, m = map(int, ym.split("-"))
        by_stock.setdefault(code, {})[(y, m)] = int(rec["매출_TWD"])

    def fmt(cur, base):
        return f"{(cur / base - 1) * 100:+.1f}" if base else ""

    for (code, ym), rec in rows.items():
        y, m = map(int, ym.split("-"))
        series = by_stock[code]
        cur = series[(y, m)]
        prev = series.get((y, m - 1) if m > 1 else (y - 1, 12))
        yago = series.get((y - 1, m))
        rec["MoM(%)"] = fmt(cur, prev)
        rec["YoY(%)"] = fmt(cur, yago)
        # cumulative YoY: Jan..m sums, only when both years have all months
        this_ms = [series.get((y, k)) for k in range(1, m + 1)]
        last_ms = [series.get((y - 1, k)) for k in range(1, m + 1)]
        if all(v is not None for v in this_ms + last_ms):
            rec["누계YoY(%)"] = fmt(sum(this_ms), sum(last_ms))
        else:
            rec["누계YoY(%)"] = ""


def write_csv(rows):
    ordered = sorted(rows.values(), key=lambda r: (r["날짜"], r["발표일"], r["코드"]))
    tmp = CSV_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(ordered)
    os.replace(tmp, CSV_PATH)
    return len(ordered)


def run_collect(backfill):
    token = resolve_token()
    if backfill:
        start = BACKFILL_START
    else:
        start = (date.today() - timedelta(days=ROLLING_DAYS)).isoformat()
    print(f"[run] mode={'backfill' if backfill else 'incremental'} start_date={start} stocks={len(TAIWAN_STOCKS)}")

    rows = read_existing()
    n_before = len(rows)
    # per-stock catch-up: if a stock's stored history is staler than the rolling
    # window (repeated failures) or absent (newly curated), extend its window
    latest_by_code = {}
    for code, ym in rows:
        if ym > latest_by_code.get(code, ""):
            latest_by_code[code] = ym
    failed, changed = [], 0
    for s in TAIWAN_STOCKS:
        code = s["코드"]
        stock_start = start
        if not backfill:
            latest = latest_by_code.get(code)
            if not latest:
                stock_start = BACKFILL_START
                print(f"[catch-up] {code}: no history, full backfill")
            else:
                y, m = map(int, latest.split("-"))
                prev_first = date(y if m > 1 else y - 1, m - 1 if m > 1 else 12, 1).isoformat()
                if prev_first < stock_start:
                    stock_start = prev_first
                    print(f"[catch-up] {code}: stale since {latest}, start={stock_start}")
        data = fetch_stock(code, stock_start, token)
        if data is None:
            failed.append(code)
            continue
        try:
            changed += merge(rows, code, data)
        except Exception as e:
            # isolate per-stock schema surprises so one stock can't kill the run
            print(f"[fetch] {code} merge error: {e}")
            failed.append(code)
        time.sleep(PACING_SEC)

    if failed:
        print(f"[warn] failed stocks ({len(failed)}): {','.join(failed)}")
    if len(failed) > len(TAIWAN_STOCKS) // 2:
        print("[fatal] more than half of the stocks failed - aborting without writing")
        sys.exit(1)
    if n_before and len(rows) < n_before:
        # history must never shrink; a shrink means a broken read/merge, not real data
        print(f"[fatal] row count would shrink {n_before} -> {len(rows)} - aborting without writing")
        sys.exit(1)

    compute_derived(rows)
    n = write_csv(rows)
    print(f"[done] rows={n} changed={changed} failed={len(failed)}")


def run_crosscheck():
    """Compare stored revenue vs official TWSE/TPEx latest-month snapshot. Log only."""
    rows = read_existing()
    if not rows:
        print("[crosscheck] no CSV yet")
        return
    official, official_names = {}, {}
    for url in (TWSE_SNAPSHOT, TPEX_SNAPSHOT):
        try:
            for rec in requests.get(url, timeout=60).json():
                roc = rec.get("資料年月", "")
                if len(roc) >= 5:
                    ym = f"{int(roc[:3]) + 1911}-{roc[3:5]}"
                    official[(rec["公司代號"], ym)] = int(rec["營業收入-當月營收"]) * 1000  # 천TWD -> TWD
                    official_names[rec["公司代號"]] = rec["公司名稱"]
        except Exception as e:
            print(f"[crosscheck] snapshot fetch failed ({url}): {e}")
    # code-reassignment / rename guard: official Chinese name must match curation
    for code, meta in STOCK_META.items():
        off_name = official_names.get(code)
        if off_name and meta.get("중문명") and off_name != meta["중문명"]:
            print(f"[crosscheck] NAME MISMATCH {code}: curation='{meta['중문명']}' official='{off_name}'"
                  f" - check taiwan_universe.csv (rename or code reassignment?)")
        if official_names and not off_name:
            print(f"[crosscheck] {code} ({meta['기업명']}) absent from official snapshot - delisted/merged?")
    mismatch = checked = missing = 0
    for key, off_rev in official.items():
        if key[0] not in STOCK_META:
            continue
        ours = rows.get(key)
        if ours is None:
            print(f"[crosscheck] missing in CSV: {key}")
            missing += 1
            continue
        checked += 1
        our_rev = int(ours["매출_TWD"])
        if off_rev and abs(our_rev - off_rev) / off_rev > 0.005:
            print(f"[crosscheck] MISMATCH {key}: ours={our_rev} official={off_rev}")
            mismatch += 1
    print(f"[crosscheck] checked={checked} mismatch={mismatch} missing={missing}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--crosscheck", action="store_true")
    args = ap.parse_args()
    if args.crosscheck:
        run_crosscheck()
    else:
        run_collect(args.backfill)
