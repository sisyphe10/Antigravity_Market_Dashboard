# -*- coding: utf-8 -*-
"""FRED 미국 매크로 36종 전체 이력 백필 → us_macro parquet.

기존 수집기 execution/fetch_fred_data.py의 SERIES 레지스트리와 api_fetch를
import해 재사용. 스탬프 규칙은 수집기와 동일: D=관측일, W=관측일+shift_days,
M=관측월 말일, Q=관측일(분기 첫날)이 속한 달의 말일.

키: env FRED_API_KEY 또는 REPO/secrets/api_keys.env 의 FRED_API_KEY=
시작: 1990-01-01 (yoy 베이스 확보 위해 1989-01-01부터 fetch)

사용: python3 datalake/backfill_fred.py
"""
import calendar
import os
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dl_common import REPO, merge_into_year_files

sys.path.insert(0, os.path.join(REPO, "execution"))
import fetch_fred_data as fred  # noqa: E402

DATASET = "us_macro"
PACE_SEC = 0.5
FULL_START = "1989-01-01"  # yoy 12개월 베이스 포함
KEEP_FROM = date(1990, 1, 1)


def load_key():
    from dl_common import load_api_key
    return load_api_key("FRED_API_KEY")


def month_end(d):
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def stamp(d, s):
    cycle = s["cycle"]
    if cycle == "D":
        return d
    if cycle == "W":
        return d + timedelta(days=s.get("shift_days", 0))
    return month_end(d)  # M·Q(분기 첫날 관측) → 그 달 말일


def transform(rows, s):
    """[(date, v)] → transform 적용. yoy=전년동월비, mom_diff=전월차."""
    tf = s.get("transform")
    if not tf:
        return rows
    by_ym = {(d.year, d.month): v for d, v in rows}
    out = []
    for d, v in rows:
        if tf == "yoy":
            base = by_ym.get((d.year - 1, d.month))
            if base:
                out.append((d, (v / base - 1) * 100))
        elif tf == "mom_diff":
            y, m = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
            prev = by_ym.get((y, m))
            if prev is not None:
                out.append((d, v - prev))
    return out


def main():
    import pandas as pd
    key = load_key()
    if not key:
        print("ERROR: FRED_API_KEY 없음 (env 또는 secrets/api_keys.env)")
        return 1

    frames, ok, failed = [], 0, []
    for s in fred.SERIES:
        time.sleep(PACE_SEC)
        try:
            rows = fred.api_fetch(key, s["fred_id"], FULL_START)
        except Exception as e:
            print(f"  ✗ {s['name']}: {type(e).__name__}", flush=True)
            failed.append(s["name"])
            continue
        rows = transform(rows, s)
        scale = s.get("scale", 1)
        nd = s.get("nd", 2)
        recs = [(stamp(d, s), s["name"], round(v * scale, nd))
                for d, v in rows if stamp(d, s) >= KEEP_FROM]
        if recs:
            frames.append(pd.DataFrame(recs, columns=["date", "series", "value"]))
            ok += 1
            print(f"  ✓ {s['name']}: {len(recs):,}행 ({recs[0][0]}~)", flush=True)
        else:
            print(f"  - {s['name']}: 데이터 없음", flush=True)

    if not frames:
        return 1
    df = pd.concat(frames, ignore_index=True)
    df["source"] = "FRED"
    merge_into_year_files(DATASET, df, ["date", "series"])
    print(f"완료: 시리즈 {ok}/{len(fred.SERIES)}, 총 {len(df):,}행"
          + (f", 실패 {failed}" if failed else ""), flush=True)
    return 1 if ok == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
