# -*- coding: utf-8 -*-
"""KRX 과거 일봉 데이터 전량 백필 (pykrx 로그인판, 재개 가능).

전 상장종목(KOSPI+KOSDAQ) 상장일부터 오늘까지, 일봉·종가 기준.
패스별 진행: ohlcv → marcap → fundamental → foreign → etf → index → investor

안전 규칙 (★KRX 계정 잠금 방지):
- 호출 간 0.5s 페이싱, 연속 실패 5회 → 즉시 중단(재실행 시 이어서)
- 종목별 결과를 _staging/<key>.parquet 에 저장 → 패스 완료 시 연도 parquet 병합
- staging 파일 존재 = 완료로 보고 skip (체크포인트)
- 10년 윈도우를 최신→과거 순으로 조회, 데이터가 있다가 완전히 빈 윈도우를 만나면
  그 이전(상장 전)은 조회 생략

사용:
  nohup python3 datalake/backfill_krx.py > ~/datalake/backfill.log 2>&1 &
  python3 datalake/backfill_krx.py --pass ohlcv               # 특정 패스만
  python3 datalake/backfill_krx.py --pass ohlcv --tickers 005930,000660   # 재백필(수정주가 소급)
"""
import argparse
import glob
import os
import sys
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dl_common import dataset_dir, merge_into_year_files

PACE_SEC = 0.5
MAX_CONSEC_FAIL = 5
START_YEAR = 1990
WINDOW_YEARS = 10

PASSES = ["ohlcv", "marcap", "fundamental", "foreign", "etf", "index", "investor"]

# 데이터셋별 (pykrx 컬럼 → 영문 컬럼) — 없는 컬럼은 무시
RENAME = {
    "kr_ohlcv": {"시가": "open", "고가": "high", "저가": "low", "종가": "close",
                 "거래량": "volume", "거래대금": "value", "등락률": "change_pct"},
    "kr_marcap": {"시가총액": "marcap", "거래량": "volume", "거래대금": "value",
                  "상장주식수": "shares"},
    "kr_fundamental": {"BPS": "bps", "PER": "per", "PBR": "pbr", "EPS": "eps",
                       "DIV": "div", "DPS": "dps"},
    "kr_foreign": {"상장주식수": "shares", "보유수량": "held", "지분율": "ratio",
                   "한도수량": "limit_qty", "한도소진률": "exhaustion"},
    "kr_etf_ohlcv": {"NAV": "nav", "시가": "open", "고가": "high", "저가": "low",
                     "종가": "close", "거래량": "volume", "거래대금": "value",
                     "기초지수": "index_value"},
    "kr_index_ohlcv": {"시가": "open", "고가": "high", "저가": "low", "종가": "close",
                       "거래량": "volume", "거래대금": "value", "상장시가총액": "marcap"},
    "kr_investor_value": {"기관합계": "institution", "기타법인": "other_corp",
                          "개인": "individual", "외국인합계": "foreigner", "전체": "total"},
}


def normalize(df, dataset, **extra_cols):
    """pykrx DataFrame(index=날짜) → date 컬럼 + 영문 컬럼 + 식별자 컬럼."""
    import pandas as pd
    if df is None or df.empty:
        return None
    out = df.reset_index()
    out = out.rename(columns={out.columns[0]: "date"})
    out = out.rename(columns=RENAME[dataset])
    keep = ["date"] + [c for c in RENAME[dataset].values() if c in out.columns]
    out = out[keep]
    for k, v in extra_cols.items():
        out[k] = v
    out["date"] = pd.to_datetime(out["date"])
    return out


def windows(today):
    """[(from, to)] 최신→과거 순 10년 윈도우."""
    result = []
    end_year = today.year
    while end_year >= START_YEAR:
        start_year = max(end_year - WINDOW_YEARS + 1, START_YEAR)
        frm = f"{start_year}0101"
        to = today.strftime("%Y%m%d") if end_year == today.year else f"{end_year}1231"
        result.append((frm, to))
        end_year = start_year - 1
    return result


class Runner:
    """페이싱 + 연속 실패 감시. 실패 5연속이면 RuntimeError로 전체 중단."""

    def __init__(self):
        self.consec_fail = 0
        self.calls = 0

    def call(self, fn, *args, **kwargs):
        time.sleep(PACE_SEC)
        self.calls += 1
        try:
            out = fn(*args, **kwargs)
            self.consec_fail = 0
            return out
        except Exception as e:
            self.consec_fail += 1
            print(f"  ! 호출 실패({self.consec_fail}/{MAX_CONSEC_FAIL}): {type(e).__name__}: {e}", flush=True)
            if self.consec_fail >= MAX_CONSEC_FAIL:
                raise RuntimeError("연속 실패 한도 도달 — KRX 인증/차단 가능성, 전체 중단") from e
            time.sleep(2)
            return None


def fetch_windowed(runner, fetch_fn, today):
    """윈도우를 최신→과거로 조회, 데이터 이후 빈 윈도우 나오면 중단. 병합 DataFrame 반환."""
    import pandas as pd
    frames, seen_data = [], False
    for frm, to in windows(today):
        df = runner.call(fetch_fn, frm, to)
        if df is not None and not df.empty:
            frames.append(df)
            seen_data = True
        elif seen_data:
            break
    if not frames:
        return None
    return pd.concat(frames)


def staging_path(dataset, key):
    d = os.path.join(dataset_dir(dataset), "_staging")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{key}.parquet")


def finalize(dataset, key_cols):
    """staging 전체 → 연도 parquet 병합 후 staging 삭제."""
    import pandas as pd
    files = glob.glob(os.path.join(dataset_dir(dataset), "_staging", "*.parquet"))
    if not files:
        return
    print(f"[{dataset}] finalize: staging {len(files)}개 병합 중...", flush=True)
    frames = [pd.read_parquet(f) for f in files]
    df = pd.concat(frames, ignore_index=True)
    merge_into_year_files(dataset, df, key_cols)
    for f in files:
        os.remove(f)
    try:
        os.rmdir(os.path.dirname(files[0]))
    except OSError:
        pass
    print(f"[{dataset}] finalize 완료: {len(df):,}행", flush=True)


def run_per_item(dataset, items, fetch_one, runner, today, key_cols, extra_fn, force=False):
    """items(식별자 목록)를 하나씩 staging으로 백필. 완료 후 finalize.

    체크포인트 2단: 패스 전체 완료 = <dataset>/.backfill_done 마커,
    항목 완료 = _staging/<key>.parquet (데이터 없음은 .parquet.empty 마커).
    """
    done_marker = os.path.join(dataset_dir(dataset), ".backfill_done")
    if os.path.exists(done_marker) and not force:
        print(f"[{dataset}] 이미 백필 완료(.backfill_done) — skip. 재실행하려면 마커 삭제", flush=True)
        return
    done = skipped = 0
    for idx, key in enumerate(items, 1):
        sp = staging_path(dataset, key)
        if os.path.exists(sp) or os.path.exists(sp + ".empty"):
            skipped += 1
            continue
        df = fetch_windowed(runner, lambda f, t, k=key: fetch_one(f, t, k), today)
        norm = normalize(df, dataset, **extra_fn(key)) if df is not None else None
        if norm is not None and not norm.empty:
            norm.to_parquet(sp, index=False)
        else:
            # 데이터 없음도 완료로 기록 (빈 마커)
            open(sp + ".empty", "w").close()
        done += 1
        if idx % 50 == 0:
            print(f"[{dataset}] {idx}/{len(items)} (신규 {done}, skip {skipped}, 호출 {runner.calls})", flush=True)
    print(f"[{dataset}] 수집 완료: 신규 {done}, skip {skipped}", flush=True)
    finalize(dataset, key_cols)
    # .empty 마커 정리 후 패스 완료 마커 기록
    for f in glob.glob(os.path.join(dataset_dir(dataset), "_staging", "*.empty")):
        os.remove(f)
    try:
        os.rmdir(os.path.join(dataset_dir(dataset), "_staging"))
    except OSError:
        pass
    open(done_marker, "w").close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pass", dest="only_pass", choices=PASSES, help="특정 패스만 실행")
    ap.add_argument("--tickers", help="쉼표구분 종목코드 — 해당 종목 재백필(기존 staging 무시)")
    args = ap.parse_args()

    from dl_common import load_pykrx
    stock = load_pykrx()
    print("pykrx 로드 완료 (data.krx 로그인)", flush=True)

    today = date.today()
    tdy = today.strftime("%Y%m%d")
    runner = Runner()
    passes = [args.only_pass] if args.only_pass else PASSES

    # 종목 유니버스 (KOSPI+KOSDAQ 현재 상장 전 종목)
    tickers, market_of, name_of = [], {}, {}
    if any(p in passes for p in ("ohlcv", "marcap", "fundamental", "foreign")):
        for mkt in ("KOSPI", "KOSDAQ"):
            for t in runner.call(stock.get_market_ticker_list, tdy, market=mkt) or []:
                tickers.append(t)
                market_of[t] = mkt
        print(f"종목 유니버스: {len(tickers)}개", flush=True)
        if args.tickers:
            want = set(args.tickers.split(","))
            tickers = [t for t in tickers if t in want]
            for ds in ("kr_ohlcv", "kr_marcap", "kr_fundamental", "kr_foreign"):
                for t in tickers:
                    for suf in ("", ".empty"):
                        p = staging_path(ds, t) + suf
                        if os.path.exists(p):
                            os.remove(p)
            print(f"재백필 대상: {len(tickers)}개", flush=True)

    def name_lookup(t):
        if t not in name_of:
            try:
                name_of[t] = stock.get_market_ticker_name(t)
            except Exception:
                name_of[t] = ""
        return name_of[t]

    def stock_extra(t):
        return {"ticker": t, "name": name_lookup(t), "market": market_of.get(t, "")}

    force = bool(args.tickers)
    if "ohlcv" in passes:
        run_per_item("kr_ohlcv", tickers,
                     lambda f, t, k: stock.get_market_ohlcv(f, t, k, adjusted=True),
                     runner, today, ["date", "ticker"], stock_extra, force=force)
    if "marcap" in passes:
        run_per_item("kr_marcap", tickers,
                     lambda f, t, k: stock.get_market_cap(f, t, k),
                     runner, today, ["date", "ticker"], stock_extra, force=force)
    if "fundamental" in passes:
        run_per_item("kr_fundamental", tickers,
                     lambda f, t, k: stock.get_market_fundamental(f, t, k),
                     runner, today, ["date", "ticker"], stock_extra, force=force)
    if "foreign" in passes:
        run_per_item("kr_foreign", tickers,
                     lambda f, t, k: stock.get_exhaustion_rates_of_foreign_investment(f, t, k),
                     runner, today, ["date", "ticker"], stock_extra, force=force)

    if "etf" in passes:
        etfs = runner.call(stock.get_etf_ticker_list, tdy) or []
        etf_names = {}

        def etf_extra(t):
            if t not in etf_names:
                try:
                    etf_names[t] = stock.get_etf_ticker_name(t)
                except Exception:
                    etf_names[t] = ""
            return {"ticker": t, "name": etf_names[t]}

        print(f"ETF 유니버스: {len(etfs)}개", flush=True)
        run_per_item("kr_etf_ohlcv", etfs,
                     lambda f, t, k: stock.get_etf_ohlcv_by_date(f, t, k),
                     runner, today, ["date", "ticker"], etf_extra)

    if "index" in passes:
        codes, code_mkt = [], {}
        for mkt in ("KOSPI", "KOSDAQ", "KRX", "테마"):
            for c in runner.call(stock.get_index_ticker_list, tdy, market=mkt) or []:
                codes.append(c)
                code_mkt[c] = mkt
        idx_names = {}

        def idx_extra(c):
            if c not in idx_names:
                try:
                    idx_names[c] = stock.get_index_ticker_name(c)
                except Exception:
                    idx_names[c] = ""
            return {"index_code": c, "name": idx_names[c], "market": code_mkt.get(c, "")}

        print(f"지수 유니버스: {len(codes)}개", flush=True)
        run_per_item("kr_index_ohlcv", codes,
                     lambda f, t, k: stock.get_index_ohlcv(f, t, k),
                     runner, today, ["date", "index_code"], idx_extra)

    if "investor" in passes:
        run_per_item("kr_investor_value", ["KOSPI", "KOSDAQ"],
                     lambda f, t, k: stock.get_market_trading_value_by_date(f, t, k),
                     runner, today, ["date", "market"], lambda k: {"market": k})

    print(f"백필 종료 — 총 호출 {runner.calls}회", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
