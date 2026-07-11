# -*- coding: utf-8 -*-
"""ECOS 한국 매크로 33종 전체 이력 백필 → kr_macro parquet.

기존 수집기 execution/fetch_ecos_data.py의 SERIES/DERIVED 레지스트리와
api_fetch/stamp_for를 그대로 import해 재사용 — 시리즈 정의 이중화 없음.
dataset.csv(2021~, 지속 갱신)와 같은 시리즈명을 쓰므로 문답에서 상호 보완.

키: env ECOS_API_KEY 또는 REPO/secrets/api_keys.env 의 ECOS_API_KEY=
시작: 일별 1995~, 월별 1990~, 분기 1990Q1~ (API가 가용 범위만 반환)

사용: python3 datalake/backfill_ecos.py
"""
import os
import sys
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dl_common import REPO, merge_into_year_files

sys.path.insert(0, os.path.join(REPO, "execution"))
import fetch_ecos_data as ecos  # noqa: E402  (import 시 부수효과 없음 — 정의만)

DATASET = "kr_macro"
PACE_SEC = 0.4
FULL_START = {"D": "19950101", "M": "199001", "Q": "1990Q1"}


def load_key():
    from dl_common import load_api_key
    return load_api_key("ECOS_API_KEY")


def yoy(rows):
    """[(TIME, v)] 월별 원지수 → 전년동월비 %. 베이스 없는 초기 12개월은 제외."""
    by_time = dict(rows)
    out = []
    for t, v in rows:
        y, m = int(t[:4]), int(t[4:6])
        base = by_time.get(f"{y - 1}{m:02d}")
        if base:
            out.append((t, (v / base - 1) * 100))
    return out


def main():
    import pandas as pd
    key = load_key()
    if not key:
        print("ERROR: ECOS_API_KEY 없음 (env 또는 secrets/api_keys.env)")
        return 1

    today = date.today()
    frames, ok, failed = [], 0, []
    for s in ecos.SERIES:
        time.sleep(PACE_SEC)
        try:
            rows = ecos.api_fetch(key, s["stat"], s["cycle"], FULL_START[s["cycle"]],
                                  ecos.ecos_end(s["cycle"], today), s["items"])
        except Exception as e:
            print(f"  ✗ {s['name']}: {type(e).__name__}", flush=True)
            failed.append(s["name"])
            continue
        if s.get("transform") == "yoy":
            rows = yoy(rows)
        scale = s.get("scale", 1)
        nd = s.get("nd", 2)
        recs = [(ecos.stamp_for(t, s["cycle"], s.get("date_rule", "")), s["name"],
                 round(v * scale, nd)) for t, v in rows]
        if recs:
            frames.append(pd.DataFrame(recs, columns=["date", "series", "value"]))
            ok += 1
            print(f"  ✓ {s['name']}: {len(recs):,}행 ({recs[0][0]}~)", flush=True)
        else:
            print(f"  - {s['name']}: 데이터 없음", flush=True)

    if not frames:
        return 1
    df = pd.concat(frames, ignore_index=True)
    df["source"] = "ECOS"

    # 파생 시리즈 (inner join a-b)
    for d in ecos.DERIVED:
        a = df[df.series == d["a"]][["date", "value"]].rename(columns={"value": "va"})
        b = df[df.series == d["b"]][["date", "value"]].rename(columns={"value": "vb"})
        j = a.merge(b, on="date")
        if not j.empty:
            dd = pd.DataFrame({"date": j["date"], "series": d["name"],
                               "value": (j["va"] - j["vb"]).round(d.get("nd", 2)),
                               "source": "ECOS"})
            df = pd.concat([df, dd], ignore_index=True)
            print(f"  ✓ (파생) {d['name']}: {len(dd):,}행", flush=True)

    merge_into_year_files(DATASET, df, ["date", "series"])
    print(f"완료: 시리즈 {ok}/{len(ecos.SERIES)} + 파생 {len(ecos.DERIVED)}, 총 {len(df):,}행"
          + (f", 실패 {failed}" if failed else ""), flush=True)
    return 1 if ok == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
