"""게이트를 transcripts 199건 전수에 돌려 오탐(정상 차단)·미탐(불량 통과)을 실측."""
import json
import sqlite3
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import transcript_gate as G

FIX = "execution/earnings_bot/fixtures/transcript_gate_fixture.json"
expected = {i["transcript_id"]: i for i in json.load(open(FIX, encoding="utf-8"))["items"]}

c = sqlite3.connect("execution/earnings_bot/earnings.db")
c.row_factory = sqlite3.Row
rows = c.execute("""
    SELECT t.id, f.ticker, substr(f.filed_at,1,10) fd, t.source, t.source_url,
           coalesce(t.prepared_remarks,'') pr, coalesce(t.qa,'') qa
    FROM transcripts t JOIN filings f ON f.id=t.filing_id
""").fetchall()

fp, fn, agree_pass, agree_rej = [], [], 0, 0
for r in rows:
    exp = expected.get(r["id"])
    if not exp:
        continue
    # 기대값 보정: fixture 의 section_missing 단독 건은 '정상'으로 재분류(사용자 승인 기준)
    reasons_exp = [x for x in exp["reasons"] if x != "section_missing"]
    want_reject = bool(reasons_exp)

    g = G.check_collect(r["source_url"], r["pr"], r["qa"], r["fd"])
    got_reject = not g.ok

    if want_reject and got_reject:
        agree_rej += 1
    elif not want_reject and not got_reject:
        agree_pass += 1
    elif not want_reject and got_reject:
        fp.append((r, g.reasons, exp))
    else:
        fn.append((r, exp))

print("게이트 실측 (transcripts %d건)" % len(rows))
print("  일치: 차단 %d / 통과 %d" % (agree_rej, agree_pass))
print("  ★오탐(정상인데 차단) %d건" % len(fp))
for r, reasons, exp in fp:
    print("     %-6s %s %-14s %s자  ← %s"
          % (r["ticker"], r["fd"], r["source"], format(len(r["pr"]) + len(r["qa"]), ","),
             " | ".join(reasons)))
print("  미탐(불량인데 통과) %d건" % len(fn))
for r, exp in fn:
    print("     %-6s %s  기대사유=%s  url=%s"
          % (r["ticker"], r["fd"], exp["reasons"], (r["source_url"] or "")[:70]))
