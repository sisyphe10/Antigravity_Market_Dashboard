"""투자주체별 누적 순매수 → dataset.csv 업서트 (데이터 타입 INVESTOR_FLOW).

kr_investor_value(코스피/코스닥 현물) + kr_deriv_investor(K200·KQ150 선물, metric=value/side=net)
일별 순매수(원)를 2022-01-01 이후 첫 거래일부터 0 기점 누적(조원, 소수 4자리)해
DATA 통합차트 시리즈로 싣는다. 매일 전 구간 결정론 재계산(멱등) — 과거 정정 자동 반영.

- 시리즈명: "{시장} {주체} 누적" (create_dashboard.py INVFLOW_* 와 합의된 키)
- 업서트는 텍스트 수준: 기존 INVESTOR_FLOW 행만 제거 후 재적재 (타 행 바이트 불변)
- 실행 순서: gha-daily-crawl 에서 create_dashboard.py 앞 (비치명)
"""
import glob
import os

import pandas as pd

LAKE = os.path.expanduser("~/datalake/market")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(REPO, "dataset.csv")
BASE = "2022-01-01"
DTYPE = "INVESTOR_FLOW"

INVESTORS = [
    ("individual", "개인"), ("foreigner_total", "외국인"),  # 외국인=합계(등록+기타, 사용자 확정 명명)
    ("fin_invest", "금융투자"), ("inst_ex_fin", "기관(금투제외)"),
    ("pension", "연기금"), ("trust", "투신"), ("private_fund", "사모"), ("insurance", "보험"),
    ("bank", "은행"), ("other_fin", "기타금융"), ("other_corp", "기타법인"),
]
DERIV_PRODS = {"KOSPI200 선물": "K200선물", "KOSDAQ150 선물": "KQ150선물"}


def load(ds):
    files = sorted(glob.glob(os.path.join(LAKE, ds, "*.parquet")))
    if not files:
        raise SystemExit(ds + ": parquet 없음")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def cum_lines(df, label, cols):
    """일별 원 단위 → BASE 이후 누적 조원 CSV 행 목록."""
    df = df[df["date"] >= BASE].sort_values("date")
    assert not df["date"].duplicated().any(), label + ": 중복 일자"
    out = []
    for col, inv in cols:
        cum = df[col].cumsum() / 1e12
        name = "{} {} 누적".format(label, inv)
        for d, v in zip(df["date"].dt.strftime("%Y-%m-%d"), cum):
            out.append("{},{},{:.4f},{}".format(d, name, v, DTYPE))
    return out, df["date"].max()


def main():
    lines = []
    spot = load("kr_investor_value")
    spot["inst_ex_fin"] = spot["institution"] - spot["fin_invest"]
    for mkt in ("KOSPI", "KOSDAQ"):
        rows, last = cum_lines(spot[spot["market"] == mkt].copy(), mkt, INVESTORS)
        lines += rows
        print("{}: {}행, 최종 {}".format(mkt, len(rows), last.date()))
    deriv = load("kr_deriv_investor")
    deriv = deriv[(deriv["metric"] == "value") & (deriv["side"] == "net")]
    dcols = [x for x in INVESTORS if x[0] != "private_fund"]
    for pname, label in DERIV_PRODS.items():
        sub = deriv[deriv["prod_name"] == pname].copy()
        assert sub["prod"].nunique() == 1, pname + ": prod 코드 복수"
        sub["inst_ex_fin"] = sub[["insurance", "trust", "bank", "other_fin", "pension"]].sum(axis=1)
        rows, last = cum_lines(sub, label, dcols)
        lines += rows
        print("{}: {}행, 최종 {}".format(label, len(rows), last.date()))

    with open(CSV, "rb") as f:
        bom = f.read(3) == b"\xef\xbb\xbf"
    enc = "utf-8-sig" if bom else "utf-8"
    with open(CSV, encoding=enc) as f:
        keep = [l for l in f.read().splitlines() if not l.endswith("," + DTYPE)]
    with open(CSV, "w", encoding=enc, newline="\n") as f:
        f.write("\n".join(keep + lines) + "\n")
    print("dataset.csv: 기존 {}행 + {} {}행".format(len(keep), DTYPE, len(lines)))
    for probe in ("KOSPI 개인 누적", "KOSPI 외국인 누적", "K200선물 외국인 누적"):
        vals = [l.split(",")[2] for l in lines if "," + probe + "," in l]
        print("{}: 최종 {}조원 ({}포인트)".format(probe, vals[-1], len(vals)))
    # 외부 대조(세미나 자료 창): 2025-01-02~2026-06-01 코스피 주체별 순매수 합
    w = spot[(spot["market"] == "KOSPI") & (spot["date"] >= "2025-01-02") & (spot["date"] <= "2026-06-01")]
    print("검증창 2025-01-02~2026-06-01 KOSPI(조원): 금융투자 {:.1f} / 외국인합계 {:.1f} / 개인 {:.1f} / 기관계-금투 {:.1f}".format(
        w["fin_invest"].sum() / 1e12, w["foreigner_total"].sum() / 1e12,
        w["individual"].sum() / 1e12, (w["institution"].sum() - w["fin_invest"].sum()) / 1e12))


if __name__ == "__main__":
    main()
