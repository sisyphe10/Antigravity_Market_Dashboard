# -*- coding: utf-8 -*-
"""지수 거래대금·거래량 → dataset.csv 업서트 (DATA 통합차트 INDEX 그룹).

원천은 전부 datalake — 백필과 일일 갱신이 같은 소스라야 계단·불연속이 안 생긴다.

- KOSPI/KOSDAQ 거래대금(원) ← kr_index_ohlcv.value
  ★KRX OpenAPI `idx/*_dd_trd` 의 ACC_TRDVAL 은 '지수 구성종목' 기준이라 시장 전체보다
    작다(코스닥 평균 -0.81%, 최대 -10.4% 실측). 통상 보도되는 시장 거래대금과 다르므로
    채택하지 않는다. kr_index_ohlcv.value 는 kr_ohlcv 종목합과 오차 0.0% 로 일치.
- S&P500/나스닥 거래량(주) ← global_markets ^GSPC/^IXIC volume (구성종목 거래주식수 합)
  ★미국은 '지수 단위 거래대금(달러)' 공개 원천이 없다. 달러 기준 활동량은 아래 ETF로 본다.
- SPY/QQQ 거래대금(달러) ← global_markets close×volume (종가 기준 근사, VWAP 아님)

업서트는 텍스트 수준 — PRODUCTS 에 든 제품명 행만 제거 후 재적재(타 행 바이트 불변).
실행 순서: gha-crawl 에서 create_dashboard.py 앞 (비치명).
"""
import glob
import os

import pandas as pd

LAKE = os.path.expanduser("~/datalake/market")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(REPO, "dataset.csv")
BASE = "2022-01-01"

# 제품명 → (데이터 타입) : 업서트 대상 집합이자 재적재 순서
PRODUCTS = [
    ("KOSPI 거래대금", "INDEX_KR"),
    ("KOSDAQ 거래대금", "INDEX_KR"),
    ("S&P 500 거래량", "INDEX_US"),
    ("NASDAQ 거래량", "INDEX_US"),
    ("SPY 거래대금", "INDEX_US"),
    ("QQQ 거래대금", "INDEX_US"),
]


def load(ds):
    files = sorted(glob.glob(os.path.join(LAKE, ds, "*.parquet")))
    if not files:
        raise SystemExit(ds + ": parquet 없음")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def emit(df, col, name, dtype):
    """date/col 두 컬럼 프레임 → CSV 행 목록 (양수 관측만, 정수 반올림)."""
    d = df[["date", col]].dropna()
    d = d[(d["date"] >= BASE) & (d[col] > 0)].sort_values("date")
    assert not d["date"].duplicated().any(), name + ": 중복 일자"
    rows = ["{},{},{:.0f},{}".format(dt, name, v, dtype)
            for dt, v in zip(d["date"].dt.strftime("%Y-%m-%d"), d[col])]
    print("{}: {}행, 최종 {} = {:,.0f}".format(
        name, len(rows), d["date"].max().date(), d[col].iloc[-1]))
    return rows


def main():
    lines = []

    kri = load("kr_index_ohlcv")
    for kname, product in (("코스피", "KOSPI 거래대금"), ("코스닥", "KOSDAQ 거래대금")):
        sub = kri[kri["name"] == kname].copy()
        lines += emit(sub, "value", product, "INDEX_KR")

    gm = load("global_markets")
    for sym, product in (("^GSPC", "S&P 500 거래량"), ("^IXIC", "NASDAQ 거래량")):
        sub = gm[gm["symbol"] == sym].copy()
        lines += emit(sub, "volume", product, "INDEX_US")
    for sym, product in (("SPY", "SPY 거래대금"), ("QQQ", "QQQ 거래대금")):
        sub = gm[gm["symbol"] == sym].copy()
        if sub.empty:
            print("! {}: global_markets 에 없음 — 스킵".format(sym))
            continue
        sub["turnover"] = sub["close"] * sub["volume"]
        lines += emit(sub, "turnover", product, "INDEX_US")

    names = {p for p, _ in PRODUCTS}
    with open(CSV, "rb") as f:
        bom = f.read(3) == b"\xef\xbb\xbf"
    enc = "utf-8-sig" if bom else "utf-8"
    with open(CSV, encoding=enc) as f:
        keep = [l for l in f.read().splitlines()
                if len(l.split(",")) < 2 or l.split(",")[1] not in names]
    with open(CSV, "w", encoding=enc, newline="\n") as f:
        f.write("\n".join(keep + lines) + "\n")
    print("dataset.csv: 기존 {}행 + 신규 {}행".format(len(keep), len(lines)))


if __name__ == "__main__":
    main()
