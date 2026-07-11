# -*- coding: utf-8 -*-
"""일일 증분 수집 — 매일 20:30 KST launchd (datalake-market-update).

당일(및 lookback 창) 데이터를 각 데이터셋 연도 parquet에 upsert.
휴장일은 KRX가 빈 응답을 주므로 조용히 skip. lookback으로 누락일 자가치유.

- 국내 단면(종목·ETF): 최근 LOOKBACK_DAYS 중 아직 없는 날짜만 일별 단면 호출
- 지수·투자자: 최근 30일 범위 재조회 upsert (잠정치 self-heal)
- 해외: 심볼별 최근 14일 (yfinance 일괄 다운로드)
- 마지막에 build_catalog.py 실행 (뷰·카탈로그 갱신)

사용: python3 datalake/daily_market_update.py [--days N]
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dl_common import dataset_dir, merge_into_year_files, year_path

PACE_SEC = 0.5
LOOKBACK_DAYS = 7
RANGE_DAYS = 30

# 일별 단면 데이터셋: (pykrx fetch(date, market?), 컬럼 rename은 backfill과 동일)
from backfill_krx import RENAME  # noqa: E402


def existing_dates(dataset, since):
    """연도 parquet에서 since 이후 존재하는 날짜 집합."""
    import pandas as pd
    dates = set()
    for year in {since.year, date.today().year}:
        p = year_path(dataset, year)
        if os.path.exists(p):
            s = pd.read_parquet(p, columns=["date"])["date"]
            dates |= {d.date() for d in s if d.date() >= since}
    return dates


def cross_section(stock, dataset, fetch_by_market, key_cols, markets):
    """최근 창에서 빠진 날짜의 시장 단면을 수집·upsert."""
    import pandas as pd
    today = date.today()
    since = today - timedelta(days=LOOKBACK_DAYS)
    have = existing_dates(dataset, since)
    missing = [since + timedelta(days=i) for i in range((today - since).days + 1)
               if (since + timedelta(days=i)) not in have
               and (since + timedelta(days=i)).weekday() < 5]
    added = 0
    for d in missing:
        ds = d.strftime("%Y%m%d")
        frames = []
        for mkt in markets:
            time.sleep(PACE_SEC)
            try:
                df = fetch_by_market(ds, mkt)
            except Exception as e:
                print(f"  ! {dataset} {ds} {mkt}: {type(e).__name__}", flush=True)
                continue
            if df is None or df.empty or (("종가" in df.columns) and (df["종가"] == 0).all()):
                continue  # 휴장일/미확정
            out = df.reset_index().rename(columns={df.index.name or "티커": "ticker"})
            out = out.rename(columns=RENAME[dataset])
            out["date"] = pd.Timestamp(d)
            if mkt:
                out["market"] = mkt
            keep = ["date", "ticker"] + [c for c in RENAME[dataset].values() if c in out.columns]
            if mkt:
                keep.append("market")
            frames.append(out[keep])
        if frames:
            merge_into_year_files(dataset, pd.concat(frames, ignore_index=True), key_cols)
            added += 1
    print(f"[{dataset}] 신규 {added}일 (누락 후보 {len(missing)}일)", flush=True)


def range_update(stock):
    """지수·투자자·해외 — 최근 RANGE_DAYS 범위 재조회 upsert."""
    import pandas as pd
    from backfill_krx import normalize
    today = date.today()
    frm = (today - timedelta(days=RANGE_DAYS)).strftime("%Y%m%d")
    to = today.strftime("%Y%m%d")

    # 지수: 기존 parquet에 있는 index_code 목록 대상으로 갱신
    codes = []
    for year in (today.year, today.year - 1):
        p = year_path("kr_index_ohlcv", year)
        if os.path.exists(p):
            df = pd.read_parquet(p, columns=["index_code", "name", "market"])
            codes = df.drop_duplicates("index_code").values.tolist()
            break
    for code, name, mkt in codes:
        time.sleep(PACE_SEC)
        try:
            df = stock.get_index_ohlcv(frm, to, code)
        except Exception as e:
            print(f"  ! index {code}: {type(e).__name__}", flush=True)
            continue
        norm = normalize(df, "kr_index_ohlcv", index_code=code, name=name, market=mkt)
        if norm is not None:
            merge_into_year_files("kr_index_ohlcv", norm, ["date", "index_code"])
    print(f"[kr_index_ohlcv] {len(codes)}개 지수 최근 {RANGE_DAYS}일 갱신", flush=True)

    for mkt in ("KOSPI", "KOSDAQ"):
        time.sleep(PACE_SEC)
        try:
            df = stock.get_market_trading_value_by_date(frm, to, mkt)
        except Exception as e:
            print(f"  ! investor {mkt}: {type(e).__name__}", flush=True)
            continue
        norm = normalize(df, "kr_investor_value", market=mkt)
        if norm is not None:
            merge_into_year_files("kr_investor_value", norm, ["date", "market"])
    print("[kr_investor_value] 갱신 완료", flush=True)


def overseas_update():
    import pandas as pd
    from backfill_overseas import fetch_symbol, load_overseas_universe
    universe = load_overseas_universe()
    ok = 0
    for symbol, orig, name in universe:
        time.sleep(0.5)
        try:
            import yfinance as yf
            raw = yf.download(symbol, period="14d", interval="1d",
                              auto_adjust=False, progress=False, threads=False)
        except Exception:
            continue
        if raw is None or raw.empty:
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        df = raw.reset_index().rename(columns={
            "Date": "date", "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Adj Close": "adj_close", "Volume": "volume"})
        df["symbol"], df["source_ticker"], df["name"] = symbol, orig, name
        merge_into_year_files("overseas_ohlcv", df, ["date", "symbol"])
        ok += 1
    print(f"[overseas_ohlcv] {ok}/{len(universe)}종목 최근 14일 갱신", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, help="국내 단면 lookback 일수 override")
    args = ap.parse_args()
    global LOOKBACK_DAYS
    if args.days:
        LOOKBACK_DAYS = args.days

    from dl_common import load_pykrx
    stock = load_pykrx()
    print("pykrx 로드 완료", flush=True)

    cross_section(stock, "kr_ohlcv",
                  lambda d, m: stock.get_market_ohlcv(d, market=m),
                  ["date", "ticker"], ("KOSPI", "KOSDAQ"))
    cross_section(stock, "kr_marcap",
                  lambda d, m: stock.get_market_cap(d, market=m),
                  ["date", "ticker"], ("KOSPI", "KOSDAQ"))
    cross_section(stock, "kr_fundamental",
                  lambda d, m: stock.get_market_fundamental(d, market=m),
                  ["date", "ticker"], ("KOSPI", "KOSDAQ"))
    cross_section(stock, "kr_foreign",
                  lambda d, m: stock.get_exhaustion_rates_of_foreign_investment(d, market=m),
                  ["date", "ticker"], ("KOSPI", "KOSDAQ"))
    cross_section(stock, "kr_etf_ohlcv",
                  lambda d, m: stock.get_etf_ohlcv_by_ticker(d),
                  ["date", "ticker"], (None,))
    range_update(stock)
    overseas_update()

    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 "build_catalog.py")], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
