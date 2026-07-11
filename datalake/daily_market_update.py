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
from dl_common import REPO, merge_into_year_files, year_path

PACE_SEC = 0.5
LOOKBACK_DAYS = 7
RANGE_DAYS = 30

# 일별 단면 데이터셋: (pykrx fetch(date, market?), 컬럼 rename은 backfill과 동일)
from backfill_krx import RENAME  # noqa: E402

# 휴장일/미확정 판정용 대표 컬럼 (전부 0이면 그 날짜 skip) — 종가 없는 데이터셋 포함
HOLIDAY_GUARD = {
    "kr_ohlcv": "종가", "kr_etf_ohlcv": "종가",
    "kr_marcap": "시가총액", "kr_fundamental": "BPS", "kr_foreign": "상장주식수",
}


def load_name_map(dataset):
    """ticker→종목명 맵. ①해당 데이터셋 최신 연도 parquet ②stock_master.json 순으로 구성.

    일일 단면에는 name이 없으므로 여기서 채운다 — 스키마를 백필본과 동일하게
    유지해야 연도 경계에서 parquet 스키마가 갈라지지 않고, upsert가 기존
    name을 NaN으로 덮지 않는다.
    """
    import glob as _glob
    import json
    import pandas as pd
    name_map = {}
    files = sorted(_glob.glob(os.path.join(os.path.dirname(year_path(dataset, 2000)), "[0-9]" * 4 + ".parquet")))
    if files:
        try:
            df = pd.read_parquet(files[-1], columns=["ticker", "name"])
            name_map = dict(df.dropna().drop_duplicates("ticker", keep="last").values)
        except Exception:
            pass
    sm = os.path.join(REPO, "stock_master.json")
    if os.path.exists(sm):
        try:
            data = json.load(open(sm, encoding="utf-8"))
            items = data.items() if isinstance(data, dict) else (
                (r.get("code") or r.get("ticker"), r.get("name")) for r in data)
            for code, nm in items:
                if code and nm and code not in name_map:
                    name_map[str(code)] = nm if isinstance(nm, str) else str(nm)
        except Exception:
            pass
    return name_map


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
    """최근 창에서 빠진 날짜의 시장 단면을 수집·upsert.

    - 시장 중 하나라도 호출 실패(예외)하면 그 날짜는 통째로 보류 → 다음
      lookback에서 재시도 (반쪽 적재 후 영구 누락 방지)
    - 컬럼은 백필본과 동일 순서(date, <값들>, ticker, name, market)로 정렬
    """
    import pandas as pd
    today = date.today()
    since = today - timedelta(days=LOOKBACK_DAYS)
    have = existing_dates(dataset, since)
    missing = [since + timedelta(days=i) for i in range((today - since).days + 1)
               if (since + timedelta(days=i)) not in have
               and (since + timedelta(days=i)).weekday() < 5]
    if not missing:
        print(f"[{dataset}] 누락 없음", flush=True)
        return
    name_map = load_name_map(dataset)
    guard_col = HOLIDAY_GUARD.get(dataset)
    added = 0
    for d in missing:
        ds = d.strftime("%Y%m%d")
        frames, failed = [], False
        for mkt in markets:
            time.sleep(PACE_SEC)
            try:
                df = fetch_by_market(ds, mkt)
            except Exception as e:
                print(f"  ! {dataset} {ds} {mkt}: {type(e).__name__} — 날짜 보류", flush=True)
                failed = True
                break
            if df is None or df.empty or (
                    guard_col and guard_col in df.columns and (df[guard_col] == 0).all()):
                continue  # 휴장일/미확정
            out = df.reset_index()
            out = out.rename(columns={out.columns[0]: "ticker"})  # 인덱스명 무관 방어
            out = out.rename(columns=RENAME[dataset])
            out["date"] = pd.Timestamp(d)
            out["name"] = out["ticker"].map(name_map).fillna("")
            # 백필 normalize와 동일한 컬럼 구성·순서 (ETF는 market 없음)
            keep = ["date"] + [c for c in RENAME[dataset].values() if c in out.columns] \
                + ["ticker", "name"]
            if mkt:
                out["market"] = mkt
                keep.append("market")
            frames.append(out[keep])
        if failed:
            continue
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


def _yf_recent(symbol, start):
    import pandas as pd
    import yfinance as yf
    # period 파라미터는 열거값만 허용("14d" 불가) — start= 로 최근 창 지정
    raw = yf.download(symbol, start=start, interval="1d",
                      auto_adjust=False, progress=False, threads=False)
    if raw is None or raw.empty:
        return None
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    return raw.reset_index().rename(columns={
        "Date": "date", "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Adj Close": "adj_close", "Volume": "volume"})


def overseas_update():
    from backfill_benchmarks import BENCHMARKS
    from backfill_overseas import load_overseas_universe
    start = (date.today() - timedelta(days=14)).isoformat()

    universe = load_overseas_universe()
    ok = 0
    for symbol, orig, name in universe:
        time.sleep(0.5)
        try:
            df = _yf_recent(symbol, start)
        except Exception:
            continue
        if df is None:
            continue
        df["symbol"], df["source_ticker"], df["name"] = symbol, orig, name
        merge_into_year_files("overseas_ohlcv", df, ["date", "symbol"])
        ok += 1
    print(f"[overseas_ohlcv] {ok}/{len(universe)}종목 최근 14일 갱신", flush=True)

    ok = 0
    for symbol, name, category in BENCHMARKS:
        time.sleep(0.5)
        try:
            df = _yf_recent(symbol, start)
        except Exception:
            continue
        if df is None:
            continue
        df["symbol"], df["name"], df["category"] = symbol, name, category
        merge_into_year_files("global_markets", df, ["date", "symbol"])
        ok += 1
    print(f"[global_markets] {ok}/{len(BENCHMARKS)}심볼 최근 14일 갱신", flush=True)


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

    # 카탈로그·뷰 갱신 — 실패를 성공으로 삼키지 않는다 (wrapper가 notify)
    rc = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                      "build_catalog.py")], check=False).returncode
    if rc != 0:
        print(f"! build_catalog 실패 rc={rc}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
