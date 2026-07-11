# -*- coding: utf-8 -*-
"""국내 전 상장종목 수정주가 이력 백필 (yfinance 배치) → kr_ohlcv_adj.

배경: KRX 수정주가 화면은 요청당 ~666행 캡 + 장기 이력 미제공 (실측 2026-07-11)
→ 장기 수익률 계산용 수정주가는 야후(.KS/.KQ)의 adj_close 사용.
kr_ohlcv(무수정, KRX 정본)와 상호 보완 — 카탈로그에 용도 구분 명시.

배치 다운로드(50종목/콜)라 전 종목도 수십 콜. 멱등(upsert).

사용: python3 datalake/backfill_kr_adjusted.py [--chunk 50]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dl_common import dataset_dir, load_pykrx, merge_into_year_files

DATASET = "kr_ohlcv_adj"
PACE_SEC = 1.5  # 배치 콜 간


def yahoo_symbol(ticker, market):
    return f"{ticker}.{'KS' if market == 'KOSPI' else 'KQ'}"


def fetch_batch(symbols):
    """yf 배치 다운로드 → {symbol: DataFrame(date, close, adj_close, volume)}"""
    import pandas as pd
    import yfinance as yf
    raw = yf.download(" ".join(symbols), period="max", interval="1d",
                      auto_adjust=False, progress=False, threads=True,
                      group_by="ticker")
    out = {}
    if raw is None or raw.empty:
        return out
    for sym in symbols:
        try:
            sub = raw[sym] if isinstance(raw.columns, pd.MultiIndex) else raw
        except KeyError:
            continue
        sub = sub.dropna(how="all")
        if sub.empty:
            continue
        df = sub.reset_index().rename(columns={
            "Date": "date", "Close": "close", "Adj Close": "adj_close",
            "Volume": "volume"})
        keep = [c for c in ("date", "close", "adj_close", "volume") if c in df.columns]
        out[sym] = df[keep].dropna(subset=["close"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=50)
    args = ap.parse_args()

    from datetime import date
    stock = load_pykrx()
    tdy = date.today().strftime("%Y%m%d")
    # 종목명은 stock_master.json에서 — 종목당 KRX name 호출 2,765회 회피
    # (backfill_krx.py와 병행 실행해도 KRX 부하 없음: KRX 호출은 리스트 2회뿐)
    import json
    from dl_common import REPO
    names = {}
    sm = os.path.join(REPO, "stock_master.json")
    if os.path.exists(sm):
        try:
            for r in json.load(open(sm, encoding="utf-8")):
                if r.get("code"):
                    names[str(r["code"])] = r.get("name", "")
        except Exception:
            pass
    universe = []  # (yahoo_sym, ticker, name, market)
    for mkt in ("KOSPI", "KOSDAQ"):
        time.sleep(0.6)
        for t in stock.get_market_ticker_list(tdy, market=mkt):
            universe.append((yahoo_symbol(t, mkt), t, names.get(t, ""), mkt))
    print(f"유니버스: {len(universe)}종목", flush=True)

    done_file = os.path.join(dataset_dir(DATASET), ".backfilled_symbols")
    done = set()
    if os.path.exists(done_file):
        done = set(open(done_file, encoding="utf-8").read().split())
    todo = [u for u in universe if u[0] not in done]
    print(f"대상: {len(todo)} (기완료 {len(done)})", flush=True)

    ok = miss = 0
    for i in range(0, len(todo), args.chunk):
        batch = todo[i:i + args.chunk]
        time.sleep(PACE_SEC)
        try:
            frames = fetch_batch([b[0] for b in batch])
        except Exception as e:
            print(f"  ! 배치 {i}: {type(e).__name__}: {e} — 보류(재실행 시 재시도)", flush=True)
            continue
        import pandas as pd
        merged = []
        for sym, ticker, name, mkt in batch:
            df = frames.get(sym)
            if df is None or df.empty:
                miss += 1
            else:
                df = df.copy()
                df["ticker"], df["name"], df["market"] = ticker, name, mkt
                merged.append(df)
                ok += 1
            done.add(sym)
        if merged:
            merge_into_year_files(DATASET, pd.concat(merged, ignore_index=True),
                                  ["date", "ticker"])
        tmp = done_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(done)))
        os.replace(tmp, done_file)
        print(f"진행 {min(i + args.chunk, len(todo))}/{len(todo)} (성공 {ok}, 야후 미상장 {miss})", flush=True)

    print(f"완료: 성공 {ok}, 야후 데이터 없음 {miss}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
