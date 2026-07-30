# -*- coding: utf-8 -*-
"""레포 dataset.csv → datalake macro_series **누적** 적재 (2026-07-30 신설).

★왜 필요한가
  종전 macro_series 는 dataset.csv 를 `shutil.copy2` 로 통째 복사한 사본을 읽는
  DuckDB VIEW 였다. 즉 **미러**라서 dataset.csv 와 이력이 100% 동일했고, 데이터레이크의
  본래 목적("덮어쓰기형 산출물 과거 유실 방지")을 이 900여 시리즈에 대해선 전혀
  달성하지 못했다. dataset.csv 에서 행이 사라지면 다음 동기화에서 레이크에서도 사라졌다.
  실제로 야후 연속선물(NG=F·SI=F 등)은 롤오버로 과거 값이 소급 재작성된다.

★무엇이 바뀌는가
  연도 파티션 parquet 에 (date, series) 키로 **upsert 누적**한다.
  - dataset.csv 에서 행이 빠져도 레이크는 계속 보유한다 (핵심).
  - 값이 정정되면 새 값으로 대체(keep=last) — 정정은 반영, 삭제는 무시.
  - 멱등: 몇 번 돌려도 같은 결과. 전체 파일을 매번 읽어 upsert 하므로 누락 창이 없다.

사용: venv/bin/python3 datalake/accumulate_macro_series.py [--csv PATH] [--dry-run]
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dl_common import REPO, merge_into_year_files, dataset_dir  # noqa: E402

DATASET = "macro_series"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=os.path.join(REPO, "dataset.csv"))
    ap.add_argument("--dry-run", action="store_true", help="적재하지 않고 집계만 출력")
    args = ap.parse_args()

    import pandas as pd

    if not os.path.exists(args.csv):
        print(f"! dataset.csv 없음: {args.csv}")
        return 1

    # dataset.csv 일부 행이 RFC4180 비준수 — 관용 파싱 (build_catalog 의 strict_mode=false 와 동일 취지)
    df = pd.read_csv(args.csv, encoding="utf-8-sig", dtype=str,
                     engine="python", on_bad_lines="skip")
    need = ["날짜", "제품명", "가격"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        print(f"! 컬럼 누락 {missing} — 실제 컬럼 {list(df.columns)}")
        return 1

    out = pd.DataFrame({
        "date": pd.to_datetime(df["날짜"], errors="coerce"),
        "series": df["제품명"].astype(str).str.strip(),
        "value": pd.to_numeric(df["가격"].astype(str).str.replace(",", "", regex=False),
                               errors="coerce"),
        "dtype": df.get("데이터 타입", pd.Series([None] * len(df))).astype("object"),
    })
    bad = out["date"].isna() | (out["series"] == "") | out["value"].isna()
    if bad.any():
        print(f"  파싱 불가 {int(bad.sum())}행 제외 (날짜/제품명/가격 결측)")
    out = out[~bad].copy()
    # 같은 (date, series) 가 CSV 안에 중복이면 뒤쪽(최신 기록)을 남긴다
    before_dedup = len(out)
    out = out.drop_duplicates(subset=["date", "series"], keep="last")
    if len(out) != before_dedup:
        print(f"  CSV 내 중복 {before_dedup - len(out)}행 정리")

    print(f"CSV: {len(out):,}행 / 시리즈 {out['series'].nunique()}종 / "
          f"{out['date'].min().date()} ~ {out['date'].max().date()}")

    # 적재 전 레이크 현황
    d = dataset_dir(DATASET)
    existing = sorted(f for f in os.listdir(d) if f.endswith(".parquet")) if os.path.isdir(d) else []
    if existing:
        old = pd.concat([pd.read_parquet(os.path.join(d, f)) for f in existing], ignore_index=True)
        print(f"레이크(기존): {len(old):,}행 / 시리즈 {old['series'].nunique()}종")
        # ★레이크에만 있고 CSV 에는 없는 행 = 이 구조가 지켜낸 이력
        key_csv = set(zip(out["date"].dt.strftime("%Y-%m-%d"), out["series"]))
        key_old = set(zip(pd.to_datetime(old["date"]).dt.strftime("%Y-%m-%d"), old["series"]))
        kept = key_old - key_csv
        if kept:
            print(f"  ★CSV 에서 사라졌지만 레이크가 보유 중인 행: {len(kept):,}개")
    else:
        print("레이크(기존): 없음 — 최초 적재")

    if args.dry_run:
        print("(dry-run — 적재 생략)")
        return 0

    res = merge_into_year_files(DATASET, out, ["date", "series"])
    added = sum(fin - bef for bef, fin in res.values())
    total = sum(fin for _, fin in res.values())
    print(f"적재 완료: 연도 {len(res)}개 / 총 {total:,}행 (순증 {added:+,})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
