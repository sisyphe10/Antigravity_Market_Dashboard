# -*- coding: utf-8 -*-
"""글로벌 벤치마크(지수·환율·원자재·금리) 전 기간 백필 (yfinance).

데이터셋: global_markets — 해외 개별주(overseas_ohlcv)와 분리해 지수/거시 자산만.
일일 증분은 daily_market_update.py가 같은 심볼 목록으로 수행.

사용: python3 datalake/backfill_benchmarks.py [--symbols ^SOX,KRW=X]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backfill_overseas import fetch_symbol
from dl_common import dataset_dir, merge_into_year_files

DATASET = "global_markets"
PACE_SEC = 1.0

# (yahoo 심볼, 표시명, 분류)
BENCHMARKS = [
    # 지수
    ("^GSPC", "S&P500", "index"),
    ("^IXIC", "나스닥종합", "index"),
    ("^DJI", "다우존스", "index"),
    ("^SOX", "필라델피아 반도체지수", "index"),
    ("^VIX", "VIX", "index"),
    ("^RUT", "러셀2000", "index"),
    ("^N225", "닛케이225", "index"),
    ("^TWII", "대만가권", "index"),
    ("^HSI", "항셍", "index"),
    ("000001.SS", "상해종합", "index"),
    ("^STOXX50E", "유로스톡스50", "index"),
    ("^NDX", "나스닥100", "index"),
    # 환율
    ("KRW=X", "달러원", "fx"),
    ("JPY=X", "달러엔", "fx"),
    ("EURUSD=X", "유로달러", "fx"),
    ("CNY=X", "달러위안", "fx"),
    ("DX-Y.NYB", "달러인덱스 DXY", "fx"),
    # 원자재
    ("CL=F", "WTI", "commodity"),
    ("BZ=F", "브렌트유", "commodity"),
    ("GC=F", "금", "commodity"),
    ("SI=F", "은", "commodity"),
    ("HG=F", "구리", "commodity"),
    ("NG=F", "천연가스", "commodity"),
    # 금리 (야후 일별 — FRED 이력과 상호 보완)
    ("^TNX", "미 국채 10Y 수익률", "rate"),
    ("^IRX", "미 T-Bill 13주 수익률", "rate"),
    ("^TYX", "미 국채 30Y 수익률", "rate"),
    # 크립토
    ("BTC-USD", "비트코인", "crypto"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", help="쉼표구분 yahoo 심볼 — 재수집")
    args = ap.parse_args()

    targets = BENCHMARKS
    done_file = os.path.join(dataset_dir(DATASET), ".backfilled_symbols")
    done = set()
    if os.path.exists(done_file):
        done = set(open(done_file, encoding="utf-8").read().split())
    if args.symbols:
        want = set(args.symbols.split(","))
        targets = [b for b in BENCHMARKS if b[0] in want]
        done -= want

    ok = fail = 0
    for symbol, name, category in targets:
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
            df["symbol"], df["name"], df["category"] = symbol, name, category
            merge_into_year_files(DATASET, df, ["date", "symbol"])
            ok += 1
            print(f"  ✓ {symbol} {name}: {len(df):,}행", flush=True)
        done.add(symbol)
        tmp = done_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(done)))
        os.replace(tmp, done_file)

    print(f"완료: 성공 {ok}, 실패 {fail} / 대상 {len(targets)}", flush=True)
    return 1 if (targets and fail == len(targets)) else 0


if __name__ == "__main__":
    sys.exit(main())
