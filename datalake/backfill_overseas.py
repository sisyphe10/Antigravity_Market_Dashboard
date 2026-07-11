# -*- coding: utf-8 -*-
"""해외 유니버스 종목 과거 일봉 백필 (yfinance).

universe_tickers.csv에서 해외 거래소 종목을 추출해 상장일부터 전 기간 수집.
데이터셋: overseas_ohlcv (수정 종가 adj_close + 원종가 close 병행).

거래소 → yahoo 심볼 매핑:
  NASDAQ/NYSE/NYSEAMERICAN → 그대로, TYO → .T, TPE → .TW, HKG → .HK(4자리 0패딩),
  ETR → .DE, EPA → .PA, AMS → .AS, TSE → .TO

사용:
  python3 datalake/backfill_overseas.py            # 전체 (기수집 심볼 skip)
  python3 datalake/backfill_overseas.py --symbols AAPL,7203.T   # 특정 심볼 재수집
"""
import argparse
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dl_common import REPO, dataset_dir, merge_into_year_files

UNIVERSE_CSV = os.path.join(REPO, "universe_tickers.csv")
DATASET = "overseas_ohlcv"
PACE_SEC = 1.0  # yahoo 페이싱

SUFFIX = {"NASDAQ": "", "NYSE": "", "NYSEAMERICAN": "",
          "TYO": ".T", "TPE": ".TW", "HKG": ".HK",
          "ETR": ".DE", "EPA": ".PA", "AMS": ".AS", "TSE": ".TO"}
DOMESTIC = {"KRX", "KOSDAQ", "KOSPI"}


def load_overseas_universe():
    """universe_tickers.csv → [(yahoo_symbol, 원본표기, 기업명)]. 사명 내 쉼표로
    컬럼이 밀린 행이 있어 ':' 포함 필드를 티커로 간주한다."""
    out, seen = [], set()
    with open(UNIVERSE_CSV, encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if not row or row[0].startswith("#"):
                continue
            tick_field = next((c for c in row if ":" in c and c.split(":")[0].isupper()), None)
            if not tick_field:
                continue
            exch, _, code = tick_field.partition(":")
            if exch in DOMESTIC or exch not in SUFFIX:
                continue
            code = code.strip()
            if exch == "HKG":
                code = code.zfill(4)
            symbol = code + SUFFIX[exch]
            if symbol in seen:
                continue
            seen.add(symbol)
            name = row[row.index(tick_field) + 1] if row.index(tick_field) + 1 < len(row) else ""
            out.append((symbol, tick_field, name.strip()))
    return out


def fetch_symbol(symbol):
    import pandas as pd
    import yfinance as yf
    raw = yf.download(symbol, period="max", interval="1d",
                      auto_adjust=False, progress=False, threads=False)
    if raw is None or raw.empty:
        return None
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = raw.reset_index().rename(columns={
        "Date": "date", "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Adj Close": "adj_close", "Volume": "volume"})
    keep = [c for c in ("date", "open", "high", "low", "close", "adj_close", "volume")
            if c in df.columns]
    return df[keep]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", help="쉼표구분 yahoo 심볼 — 재수집")
    args = ap.parse_args()

    universe = load_overseas_universe()
    print(f"해외 유니버스: {len(universe)}종목", flush=True)

    import pandas as pd
    done_file = os.path.join(dataset_dir(DATASET), ".backfilled_symbols")
    done = set()
    if os.path.exists(done_file):
        done = set(open(done_file, encoding="utf-8").read().split())

    targets = universe
    if args.symbols:
        want = set(args.symbols.split(","))
        targets = [u for u in universe if u[0] in want]
        done -= want

    ok = fail = 0
    for i, (symbol, orig, name) in enumerate(targets, 1):
        if symbol in done:
            continue
        time.sleep(PACE_SEC)
        try:
            df = fetch_symbol(symbol)
        except Exception as e:
            print(f"  ! {symbol}: {type(e).__name__}: {e}", flush=True)
            fail += 1
            continue
        if df is None or df.empty:
            print(f"  - {symbol}: 데이터 없음", flush=True)
        else:
            df["symbol"] = symbol
            df["source_ticker"] = orig
            df["name"] = name
            merge_into_year_files(DATASET, df, ["date", "symbol"])
            ok += 1
        done.add(symbol)
        tmp = done_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(done)))
        os.replace(tmp, done_file)
        if i % 20 == 0:
            print(f"진행 {i}/{len(targets)} (성공 {ok}, 실패 {fail})", flush=True)

    print(f"완료: 성공 {ok}, 실패 {fail}, 누적 심볼 {len(done)}", flush=True)
    return 0 if fail < len(targets) else 1


if __name__ == "__main__":
    sys.exit(main())
