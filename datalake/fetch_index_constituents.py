# -*- coding: utf-8 -*-
"""KOSPI200·KOSDAQ150 구성 종목 스냅샷 적재.

pykrx get_index_portfolio_deposit_file(지수코드) — 1028=코스피 200, 2203=코스닥 150.
종목명은 kr_marcap 최신일에서 조인. (date, index_name, ticker) upsert —
재실행하면 스냅샷이 이력으로 누적되고, 최신 구성은 MAX(date) 필터로 조회.

사용: venv/bin/python3 datalake/fetch_index_constituents.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dl_common import load_pykrx, merge_into_year_files, year_path

import pandas as pd

# (지수코드, index_name, 정원)
INDICES = [("1028", "kospi200", 200), ("2203", "kosdaq150", 150)]


def main():
    stock = load_pykrx()
    trd = stock.get_nearest_business_day_in_a_week()  # YYYYMMDD
    asof = pd.Timestamp(trd)

    # 종목명 조인용 — kr_marcap 최신일 (지수 PDF는 티커만 반환)
    mc = pd.read_parquet(year_path("kr_marcap", asof.year),
                         columns=["date", "ticker", "name"])
    names = mc[mc["date"] == mc["date"].max()].set_index("ticker")["name"]

    frames = []
    for code, label, expect in INDICES:
        tickers = stock.get_index_portfolio_deposit_file(code, trd)
        if len(tickers) != expect:
            print(f"[warn] {label}: {len(tickers)}종목 (정원 {expect})")
        df = pd.DataFrame({"ticker": list(tickers)})
        df["date"] = asof
        df["index_name"] = label
        df["name"] = df["ticker"].map(names)
        missing = int(df["name"].isna().sum())
        print(f"{label}: {len(df)}종목 @ {asof.date()}, 종목명 결측 {missing}")
        frames.append(df)
        time.sleep(0.5)

    out = pd.concat(frames, ignore_index=True)[["date", "index_name", "ticker", "name"]]
    res = merge_into_year_files("kr_index_constituents", out,
                                ["date", "index_name", "ticker"])
    print("merged:", res)


if __name__ == "__main__":
    main()
