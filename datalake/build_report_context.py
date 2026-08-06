# -*- coding: utf-8 -*-
"""보고서 작성용 컨텍스트 빌더 — freshness preflight + 구조화 JSON 한 방 출력.

보고서 커맨드(운용보고서/주간보고/긴급코멘트)가 SSH 1회로 호출한다.
"레이크가 완전한가"를 원천 DB와 실시간 대조로 판정하고, 불완전하면
exit 2 로 끝나 커맨드가 폴백(Notion/로컬)으로 넘어가게 한다.

사용:
  python3 datalake/build_report_context.py --kind monthly --period 2026-07
  python3 datalake/build_report_context.py --kind weekly  --date 2026-08-06
  python3 datalake/build_report_context.py --kind comment --date 2026-08-06

출력: stdout에 JSON 1개. 섹션별 status/count 포함.
exit 0 = complete, 2 = incomplete(폴백 필요), 1 = 사용 오류.

as-of 원칙: --kind monthly 로 과거 월을 재생성할 때 period 말일 이후 자료는
테마 집계·직전 보고서 선정에서 제외한다 (look-ahead 차단).
"""
import argparse
import calendar
import glob
import json
import os
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dl_common import DATALAKE_ROOT, NOTES_DIR, REPO  # noqa: E402

DB_PATH = os.path.join(REPO, "execution", "research_bot", "research_notes.db")
REPORTS_DIR = os.path.join(DATALAKE_ROOT, "reports")
TAG_INDEX = os.path.join(DATALAKE_ROOT, "tag_index.sqlite")

FM_LIST_KEYS = ("themes", "tickers", "sectors", "orgs")


def read_frontmatter(path):
    """exporter 가 쓰는 결정적 프론트매터를 파싱한다.

    리스트 값은 JSON 배열로 직렬화돼 있으므로(export_research_notes._yaml_list)
    json.loads 로 안전하게 읽는다. 형식이 다르면 그 키만 None.
    """
    fm = {}
    try:
        with open(path, encoding="utf-8") as f:
            first = f.readline()
            if first.strip() != "---":
                return fm
            for line in f:
                if line.strip() == "---":
                    break
                m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line.rstrip("\n"))
                if not m:
                    continue
                key, val = m.group(1), m.group(2).strip()
                if val.startswith("["):
                    try:
                        fm[key] = json.loads(val)
                    except ValueError:
                        fm[key] = None
                else:
                    fm[key] = val.strip('"')
    except OSError:
        pass
    return fm


def db_day_counts(conn, d0, d1):
    """원천 DB의 일별 메시지 수 (d0~d1 포함)."""
    rows = conn.execute(
        "SELECT substr(timestamp,1,10) d, count(*) c FROM messages"
        " WHERE substr(timestamp,1,10) BETWEEN ? AND ? GROUP BY d ORDER BY d",
        (d0, d1)).fetchall()
    return {r[0]: r[1] for r in rows}


def notes_freshness(conn, d0, d1):
    """레이크 research_notes md vs 원천 DB 실시간 대조."""
    db_counts = db_day_counts(conn, d0, d1)
    days, missing, mismatch = [], [], []
    for day, db_c in sorted(db_counts.items()):
        path = os.path.join(NOTES_DIR, day[:4], day + ".md")
        if not os.path.exists(path):
            missing.append(day)
            days.append({"date": day, "db_count": db_c, "md_count": None, "match": False})
            continue
        fm = read_frontmatter(path)
        md_c = int(fm.get("count") or 0)
        ok = (md_c == db_c)
        if not ok:
            mismatch.append(day)
        days.append({"date": day, "db_count": db_c, "md_count": md_c, "match": ok})
    status = "ok" if not missing and not mismatch else "incomplete"
    return {"status": status, "days": days, "missing_days": missing,
            "mismatch_days": mismatch,
            "hint": "" if status == "ok" else
            "venv/bin/python3 datalake/export_research_notes.py --from %s --to %s 로 재수출" % (d0, d1)}


def tag_index_freshness(d1):
    """tag_index 가 대상 기간 md 보다 오래되면 stale."""
    if not os.path.exists(TAG_INDEX):
        return {"status": "missing", "index_mtime": None}
    idx_m = os.path.getmtime(TAG_INDEX)
    newest = 0.0
    for path in glob.glob(os.path.join(NOTES_DIR, d1[:4], "*.md")):
        if os.path.basename(path)[:10] <= d1:
            newest = max(newest, os.path.getmtime(path))
    stale = newest > idx_m
    return {"status": "stale" if stale else "ok",
            "index_mtime": datetime.fromtimestamp(idx_m).isoformat(timespec="seconds"),
            "newest_md_mtime": datetime.fromtimestamp(newest).isoformat(timespec="seconds") if newest else None,
            "hint": "" if not stale else "datalake/tagging/tag_docs.py + build_tag_index.py 실행 필요"}


def theme_day_freq(d0, d1):
    """기간 내 테마별 등장 일수 (메시지 수 아님 — 채널 반복량 왜곡 완화).

    빈도는 '많이 언급된 화두'의 탐색 지도일 뿐 시장 중요도 근거가 아니다.
    """
    freq = {}
    n_days = 0
    d = datetime.strptime(d0, "%Y-%m-%d").date()
    end = datetime.strptime(d1, "%Y-%m-%d").date()
    while d <= end:
        path = os.path.join(NOTES_DIR, "%04d" % d.year, d.isoformat() + ".md")
        if os.path.exists(path):
            n_days += 1
            for t in (read_frontmatter(path).get("themes") or []):
                freq[t] = freq.get(t, 0) + 1
        d += timedelta(days=1)
    top = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    return {"status": "ok" if n_days else "empty", "days_covered": n_days,
            "top": top[:30]}


def collect_reports(subdir, on_or_before, limit, full_text=True):
    """reports/<subdir>/ 에서 날짜 ≤ on_or_before 인 최신 limit 건.

    파일명 선두 YYYY-MM(-DD) 기준. 비교는 두 문자열의 짧은 쪽 정밀도로
    맞춘다 (월간 파일명 YYYY-MM vs 경계 YYYY-MM-DD 혼재 대응). as-of 필터.
    """
    items = []
    for path in sorted(glob.glob(os.path.join(REPORTS_DIR, subdir, "*", "*.md")), reverse=True):
        name = os.path.basename(path)
        m = re.match(r"(\d{4}-\d{2}(?:-\d{2})?)", name)
        if not m:
            continue
        w = min(len(m.group(1)), len(on_or_before))
        if m.group(1)[:w] > on_or_before[:w]:
            continue
        item = {"path": os.path.relpath(path, DATALAKE_ROOT), "date": m.group(1),
                "chars": os.path.getsize(path)}
        fm = read_frontmatter(path)
        if fm.get("status"):
            item["status"] = fm["status"]
        if full_text:
            try:
                item["text"] = open(path, encoding="utf-8").read()
            except OSError:
                item["text"] = None
        items.append(item)
        if len(items) >= limit:
            break
    return {"status": "ok" if items else "empty", "count": len(items), "items": items}


def live_day_messages(conn, day):
    """당일분을 원천 DB에서 직접(read-only) — 23:20 export 지연과 무관하게 최신."""
    rows = conn.execute(
        "SELECT id, timestamp, message_type, forward_source, text_content, url"
        " FROM messages WHERE timestamp LIKE ? ORDER BY timestamp, id",
        (day + "%",)).fetchall()
    items = [{"id": r[0], "time": r[1][11:16], "type": r[2], "source": r[3],
              "text": (r[4] or "").strip(), "url": r[5]} for r in rows]
    return {"status": "ok" if items else "empty", "count": len(items),
            "as_of": datetime.now().strftime("%Y-%m-%d %H:%M KST"), "items": items}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, choices=["monthly", "weekly", "comment"])
    ap.add_argument("--period", help="monthly: YYYY-MM")
    ap.add_argument("--date", help="weekly/comment: 기준일 YYYY-MM-DD (기본 오늘)")
    ap.add_argument("--allow-incomplete", action="store_true",
                    help="incomplete 여도 exit 0 (폴백 판단을 호출측이 직접)")
    args = ap.parse_args()

    out = {"kind": args.kind,
           "generated_at": datetime.now().isoformat(timespec="seconds"),
           "sections": {}, "warnings": []}
    sec = out["sections"]

    if not os.path.exists(DB_PATH):
        print(json.dumps({"error": "research_notes.db 없음"}, ensure_ascii=False))
        return 1
    conn = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True)

    today = date.today().isoformat()

    if args.kind == "monthly":
        if not args.period or not re.match(r"^\d{4}-\d{2}$", args.period):
            print(json.dumps({"error": "--period YYYY-MM 필요"}, ensure_ascii=False))
            return 1
        y, m = int(args.period[:4]), int(args.period[5:7])
        d0 = "%04d-%02d-01" % (y, m)
        d1 = "%04d-%02d-%02d" % (y, m, calendar.monthrange(y, m)[1])
        if d0 > today:
            print(json.dumps({"error": "미래 월 %s" % args.period}, ensure_ascii=False))
            return 1
        if d1 >= today:
            out["warnings"].append("보고월이 아직 끝나지 않음 — 당월 진행분 기준")
            d1 = today
        out["period"] = {"from": d0, "to": d1}
        sec["research_notes"] = notes_freshness(conn, d0, d1)
        sec["tag_index"] = tag_index_freshness(d1)
        sec["themes"] = theme_day_freq(d0, d1)
        # 전월 테마 (delta 비교용)
        pm_y, pm_m = (y, m - 1) if m > 1 else (y - 1, 12)
        pd0 = "%04d-%02d-01" % (pm_y, pm_m)
        pd1 = "%04d-%02d-%02d" % (pm_y, pm_m, calendar.monthrange(pm_y, pm_m)[1])
        sec["themes_prev_month"] = theme_day_freq(pd0, pd1)
        sec["prior_monthly"] = collect_reports("monthly", "%04d-%02d" % (pm_y, pm_m), 5)
        sec["recent_comments"] = collect_reports("comments", d1, 3)
        if sec["prior_monthly"]["count"] > 1:
            out["warnings"].append("prior_monthly 는 같은 달 상품별 문서가 겹칠 수 있음 — 공통 본문 중복 주의")

    elif args.kind == "weekly":
        base = args.date or today
        out["period"] = {"base_date": base}
        d0 = (datetime.strptime(base, "%Y-%m-%d").date() - timedelta(days=7)).isoformat()
        sec["research_notes"] = notes_freshness(conn, d0, min(base, today))
        sec["tag_index"] = tag_index_freshness(base)
        day_before = (datetime.strptime(base, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()
        sec["prior_weekly"] = collect_reports("weekly", day_before, 2)
        sec["recent_comments"] = collect_reports("comments", base, 3)
        sec["themes_window"] = theme_day_freq(d0, min(base, today))
        if not any(i.get("status") == "final" for i in sec["prior_weekly"]["items"]):
            out["warnings"].append("레이크 prior_weekly 에 status:final 문서 없음 — 로컬 '주간 보고' 폴더 최종본을 우선하라")

    else:  # comment
        base = args.date or today
        out["period"] = {"event_date": base}
        sec["today_notes"] = live_day_messages(conn, base)
        prev = (datetime.strptime(base, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()
        sec["yesterday_notes_freshness"] = notes_freshness(conn, prev, prev)
        sec["prior_comments"] = collect_reports("comments", prev, 2)
        sec["themes_window"] = theme_day_freq(
            (datetime.strptime(base, "%Y-%m-%d").date() - timedelta(days=7)).isoformat(), base)

    conn.close()

    incomplete = any(s.get("status") in ("incomplete", "missing")
                     for s in sec.values() if isinstance(s, dict))
    out["complete"] = not incomplete
    if incomplete:
        out["warnings"].append("불완전 섹션 있음 — 커맨드의 폴백 경로를 사용하고 degraded source 를 보고할 것")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if (out["complete"] or args.allow_incomplete) else 2


if __name__ == "__main__":
    sys.exit(main())
