"""
merge_wrap_nav.py — 3-way sheet-level merge for Wrap_NAV.xlsx.

git cannot merge the binary, and whole-file ours/theirs always drops one
side's appended rows when both sides changed (local user AUM/NEW edits vs
GHA finalize_orders). This merger resolves at the domain level instead:

  sheet        | policy
  -------------|----------------------------------------------------------
  AUM          | 3-way upsert by key (날짜, 증권사, 상품명). Same-key
               | both-changed -> --prefer side wins (default ours).
  NEW          | 3-way by GROUP (날짜, 증권사, 상품명). finalize REPLACES a
               | whole group (portfolio snapshot), so row-level union is
               | wrong: a group changed on both sides -> CONFLICT (exit 2).
               | Merged groups are validated (비중 합계 <= 100).
  기준가/수익률 | derived; theirs wins when both changed (recalc_wrap_nav
               | re-derives on the next push anyway), changed side otherwise.
  other sheets | changed side; both changed -> CONFLICT (exit 2).

Output = copy of THEIRS file (keeps its derived sheets/format) with the
merged AUM/NEW (and any ours-only sheets) rewritten pandas-style, matching
add_aum.py's if_sheet_exists='replace' convention.

CLI:  python merge_wrap_nav.py BASE OURS THEIRS -o OUT [--prefer ours|theirs]
Exit: 0 merged, 2 domain conflict (manual resolution needed), 1 error.
"""

import argparse
import shutil
import sys

import pandas as pd

AUM_SHEET = "AUM"
NEW_SHEET = "NEW"
DERIVED_SHEETS = {"기준가", "수익률"}
AUM_KEY = ["날짜", "증권사", "상품명"]
NEW_GROUP_KEY = ["날짜", "증권사", "상품명"]
WEIGHT_COL = "비중"
WEIGHT_TOLERANCE = 0.01


class MergeConflict(Exception):
    pass


# ── normalization ──────────────────────────────────────


def _norm_cell(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, float):
        return f"{round(v, 6):g}"
    if isinstance(v, int):
        return str(v)
    return str(v).strip()


def _norm_date(v):
    ts = pd.to_datetime(v, errors="coerce")
    return _norm_cell(v) if pd.isna(ts) else ts.strftime("%Y-%m-%d")


def _norm_row(row, columns):
    return tuple(_norm_cell(row[c]) for c in columns)


def _norm_table(df):
    """Header included: a column rename/reorder must count as a change."""
    if df is None:
        return None
    header = tuple(str(c) for c in df.columns)
    return [header] + [tuple(_norm_cell(v) for v in row) for row in df.itertuples(index=False)]


def _key_of(row, key_cols):
    # '날짜' may arrive as Timestamp or as string ('2026-06-01 00:00:00') —
    # both must map to the same key or groups silently split.
    return tuple(
        _norm_date(row[c]) if c == "날짜" else _norm_cell(row[c]) for c in key_cols
    )


def _check_columns(sheet, ours, theirs):
    if list(map(str, ours.columns)) != list(map(str, theirs.columns)):
        raise MergeConflict(
            f"{sheet} 컬럼 불일치: {list(ours.columns)} vs {list(theirs.columns)}"
        )


# ── AUM: keyed upsert ──────────────────────────────────


def merge_aum(base, ours, theirs, prefer, log):
    _check_columns(AUM_SHEET, ours, theirs)
    cols = list(theirs.columns)
    val_cols = [c for c in cols if c not in AUM_KEY]

    def to_map(df):
        m = {}
        for _, row in df.iterrows():
            m[_key_of(row, AUM_KEY)] = row  # last occurrence wins (add_aum dedups too)
        return m

    b, o, t = to_map(base), to_map(ours), to_map(theirs)

    def val(m, k):
        return _norm_row(m[k], val_cols) if k in m else None

    out_rows, handled = [], set()
    stats = {"ours_add": 0, "ours_upd": 0, "ours_del": 0, "pref": 0}

    # output uses the dedup maps (last occurrence wins), matching add_aum's upsert
    for _, trow in theirs.iterrows():
        k = _key_of(trow, AUM_KEY)
        if k in handled:
            continue
        handled.add(k)
        ours_changed = val(o, k) != val(b, k)
        theirs_changed = val(t, k) != val(b, k)
        if not ours_changed:
            out_rows.append(t[k])
        elif k not in o:  # ours deleted
            if theirs_changed and prefer == "theirs":
                out_rows.append(t[k])
            else:
                stats["ours_del"] += 1
        else:
            if theirs_changed and val(o, k) != val(t, k):
                stats["pref"] += 1
                out_rows.append(t[k] if prefer == "theirs" else o[k])
            else:
                stats["ours_upd"] += 1
                out_rows.append(o[k])

    for _, orow in ours.iterrows():  # keys absent from theirs
        k = _key_of(orow, AUM_KEY)
        if k in handled:
            continue
        handled.add(k)
        if val(o, k) == val(b, k):  # theirs deleted, ours untouched -> stay deleted
            continue
        if k in b and prefer == "theirs":  # ours changed but theirs deleted
            stats["pref"] += 1
            continue
        stats["ours_add"] += 1
        out_rows.append(o[k])

    log(f"AUM merge: +{stats['ours_add']} upd {stats['ours_upd']} del {stats['ours_del']}"
        f" prefer-resolved {stats['pref']}")
    return pd.DataFrame(out_rows, columns=cols).reset_index(drop=True)


# ── NEW: group-level snapshot merge ────────────────────


def _group_table(df):
    """ordered dict: group key -> (original rows DataFrame, normalized row list)"""
    groups = {}
    for _, row in df.iterrows():
        groups.setdefault(_key_of(row, NEW_GROUP_KEY), []).append(row)
    return groups


def _group_norm(rows, columns):
    body = sorted(_norm_row(r, columns) for r in rows)
    return body


def merge_new(base, ours, theirs, log):
    _check_columns(NEW_SHEET, ours, theirs)
    cols = list(theirs.columns)
    b, o, t = _group_table(base), _group_table(ours), _group_table(theirs)

    def norm(m, k):
        return _group_norm(m[k], cols) if k in m else None

    out_rows, handled = [], set()
    stats = {"ours_groups": 0}

    for k in t:
        handled.add(k)
        ours_changed = norm(o, k) != norm(b, k)
        theirs_changed = norm(t, k) != norm(b, k)
        if ours_changed and theirs_changed and norm(o, k) != norm(t, k):
            raise MergeConflict(
                f"NEW 그룹 {k} 이(가) 로컬·원격 양쪽에서 다르게 수정됨 — 수동 해결 필요"
            )
        if ours_changed:
            stats["ours_groups"] += 1
            out_rows.extend(o.get(k, []))
        else:
            out_rows.extend(t[k])

    for k in o:
        if k in handled:
            continue
        ours_changed = norm(o, k) != norm(b, k)
        theirs_changed = (k in b) != (k in t) or norm(t, k) != norm(b, k)
        if not ours_changed:  # theirs deleted the group, ours untouched
            continue
        if theirs_changed:
            raise MergeConflict(
                f"NEW 그룹 {k} 을(를) 한쪽이 삭제하고 한쪽이 수정함 — 수동 해결 필요"
            )
        stats["ours_groups"] += 1
        out_rows.extend(o[k])

    merged = pd.DataFrame(out_rows, columns=cols).reset_index(drop=True)

    weights = pd.to_numeric(merged[WEIGHT_COL], errors="coerce")
    if weights.isna().any():
        raise MergeConflict("NEW 비중에 숫자가 아닌 값 존재 — 수동 확인 필요")
    sums = merged.assign(_w=weights).groupby(NEW_GROUP_KEY, sort=False)["_w"].sum()
    bad = sums[sums > 100 + WEIGHT_TOLERANCE]
    if len(bad):
        raise MergeConflict(f"NEW 비중 합계 100 초과 그룹: {bad.to_dict()}")

    log(f"NEW merge: ours 그룹 {stats['ours_groups']}개 반영, 총 {len(merged)}행")
    return merged


# ── orchestration ──────────────────────────────────────


def merge_files(base_path, ours_path, theirs_path, out_path, prefer="ours", log=print):
    """Returns 0 (merged, out written) or raises MergeConflict."""
    base = pd.read_excel(base_path, sheet_name=None)
    ours = pd.read_excel(ours_path, sheet_name=None)
    theirs = pd.read_excel(theirs_path, sheet_name=None)

    names_o, names_t = set(ours), set(theirs)
    removed = (set(base) - names_o) ^ (set(base) - names_t)
    if (set(base) - names_o) and (set(base) - names_t) and removed:
        raise MergeConflict(f"시트 삭제가 양쪽에서 엇갈림: {removed}")

    empty = pd.DataFrame()
    to_write = {}  # sheet -> DataFrame to replace onto theirs copy

    for name in sorted(names_o | names_t):
        b_df, o_df, t_df = base.get(name, empty), ours.get(name), theirs.get(name)
        if name == AUM_SHEET:
            merged = merge_aum(b_df, o_df, t_df, prefer, log)
            if _norm_table(merged) != _norm_table(t_df):
                to_write[name] = merged
            continue
        if name == NEW_SHEET:
            merged = merge_new(b_df, o_df, t_df, log)
            if _norm_table(merged) != _norm_table(t_df):
                to_write[name] = merged
            continue

        ours_changed = _norm_table(o_df) != _norm_table(b_df if name in base else None)
        theirs_changed = _norm_table(t_df) != _norm_table(b_df if name in base else None)
        if not ours_changed:
            continue  # theirs copy already holds the right content
        if t_df is None:  # ours-only new sheet
            to_write[name] = o_df
        elif not theirs_changed:
            to_write[name] = o_df
            log(f"시트 '{name}': ours만 변경 → ours 채택")
        elif name in DERIVED_SHEETS or _norm_table(o_df) == _norm_table(t_df):
            log(f"시트 '{name}': 양쪽 변경 → theirs 채택 (파생, recalc self-heal)")
        else:
            raise MergeConflict(f"시트 '{name}' 양쪽 수정 (파생 시트 아님) — 수동 해결 필요")

    shutil.copyfile(theirs_path, out_path)
    if to_write:
        with pd.ExcelWriter(out_path, engine="openpyxl", mode="a",
                            if_sheet_exists="replace") as w:
            for name, df in to_write.items():
                df.to_excel(w, sheet_name=name, index=False)
    log(f"병합 완료 → {out_path} (교체 시트: {list(to_write) or '없음'})")
    return 0


def files_equal(a_path, b_path):
    """Normalized content equality across all sheets (byte equality is useless
    for xlsx — recompression changes bytes on every write)."""
    a = pd.read_excel(a_path, sheet_name=None)
    b = pd.read_excel(b_path, sheet_name=None)
    if set(a) != set(b):
        return False
    return all(_norm_table(a[name]) == _norm_table(b[name]) for name in a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("ours")
    ap.add_argument("theirs")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--prefer", choices=["ours", "theirs"], default="ours")
    args = ap.parse_args()
    try:
        merge_files(args.base, args.ours, args.theirs, args.out, prefer=args.prefer)
        return 0
    except MergeConflict as e:
        print(f"CONFLICT: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
