# -*- coding: utf-8 -*-
"""taiwan.html generator — Taiwan monthly revenue line-by-line table.

Reads taiwan_revenue.csv (fetch_taiwan_revenue.py output) and renders a single
flat table, newest announcements first, with excel-style header controls
(click = asc/desc sort toggle, ▾ = per-column value checkbox filter — the
rev-filter pattern from the WRAP fee tab). Standalone generator like
create_market_alert.py; shared top nav / sidebar come from create_dashboard.
"""
import csv
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from create_dashboard import (top_nav_html, sidebar_html, body_class,
                              TOP_NAV_CSS, PRETENDARD_LINK, PRETENDARD_STACK)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "taiwan_revenue.csv")
UNIVERSE_CSV = os.path.join(ROOT, "taiwan_universe.csv")
OUT_PATH = os.path.join(ROOT, "taiwan.html")


def load_rows():
    # 한국PEER is static metadata joined at render time (edits to taiwan_universe.csv
    # take effect on the next page build without touching taiwan_revenue.csv)
    with open(UNIVERSE_CSV, encoding="utf-8-sig", newline="") as f:
        peers = {u["코드"]: u.get("한국PEER", "") for u in csv.DictReader(f)}
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    # newest first: 날짜 desc, 발표일 desc(공란 마지막), 코드 asc
    rows.sort(key=lambda r: (r["날짜"], r["발표일"], ), reverse=True)
    # compact array payload: [날짜, 발표일, 코드, 기업명, 시장, 섹터, 분류, 한국PEER, 매출TWD, MoM, YoY, 누계YoY]
    return [[r["날짜"], r["발표일"], r["코드"], r["기업명"], r["시장"], r["섹터"],
             r["분류"], peers.get(r["코드"], ""), int(r["매출_TWD"]),
             r["MoM(%)"], r["YoY(%)"], r["누계YoY(%)"]]
            for r in rows]


def build_html(payload_rows):
    now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    n_stocks = len({r[2] for r in payload_rows})
    latest = max(r[0] for r in payload_rows) if payload_rows else "-"

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Taiwan 월매출</title>
    {PRETENDARD_LINK}
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: {PRETENDARD_STACK}; background: #fff; color: #111; }}
        header {{ text-align: center; padding: 28px 16px 10px; }}
        header h1 {{ font-size: 1.5rem; color: #111; }}
        .last-updated {{ color: #999; font-size: 0.85rem; margin-top: 6px; }}
        .tw-wrapper {{ max-width: 1180px; margin: 0 auto; padding: 12px 24px 40px; position: relative; }}
        .table-container {{ overflow-x: auto; border: 1px solid #e5e7eb; border-radius: 12px; }}
        .tw-table {{ width: 100%; border-collapse: collapse; }}
        .tw-table th {{ position: sticky; top: 0; padding: 9px 10px; text-align: center;
                        font-size: 0.78rem; font-weight: 600; color: #374151; background: #f9fafb;
                        border-bottom: 1px solid #e5e7eb; white-space: nowrap; cursor: pointer; user-select: none; }}
        .tw-table th:hover {{ color: #111; }}
        .tw-table td {{ padding: 6px 10px; border-bottom: 1px solid #f3f4f6; color: #111;
                        white-space: nowrap; font-size: 0.8rem; text-align: center; }}
        .tw-table tbody tr:last-child td {{ border-bottom: none; }}
        .tw-table tbody tr:hover td {{ background: #f9fafb; }}
        .tw-filter-btn {{ display: inline-block; margin-left: 4px; color: #9ca3af; cursor: pointer; }}
        .tw-filter-btn:hover {{ color: #111; }}
        .tw-filter-btn.tw-filter-on {{ color: #111; font-weight: 800; }}
        .tw-filter-pop {{ position: absolute; z-index: 300; background: #fff; border: 1px solid #d1d5db;
                          border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,0.12); padding: 8px;
                          max-height: 280px; overflow-y: auto; min-width: 140px; }}
        .tw-filter-item {{ display: block; padding: 3px 6px; font-size: 0.8rem; color: #111;
                           white-space: nowrap; cursor: pointer; }}
        .tw-filter-item:hover {{ background: #f3f4f6; border-radius: 6px; }}
        footer {{ text-align: center; padding: 16px; color: #999; font-size: 13px; }}
        footer a {{ color: #999; }}
        {TOP_NAV_CSS}
    </style>
</head>
<body{body_class('taiwan')}>
    {top_nav_html('taiwan')}
    {sidebar_html('taiwan')}
    <header>
        <h1>Taiwan 월매출</h1>
        <div class="last-updated">Updated: {now} &nbsp;|&nbsp; {n_stocks}종목 · 최신 {latest}</div>
    </header>

    <div class="tw-wrapper">
        <div class="table-container"><div id="twTableHost"></div></div>
    </div>

    <footer>
        출처: FinMind · TWSE/TPEx 월별 매출 공시 (증권거래법 §36, 익월 10일 한) &nbsp;|&nbsp;
        발표일은 데이터 수집 시점 기준이며 과거분은 공란 &nbsp;|&nbsp; 본 자료는 참고용이며 투자 조언이 아닙니다
    </footer>

    <script>
    var TW_DATA = __PAYLOAD__;
    // row: [0날짜, 1발표일, 2코드, 3기업명, 4시장, 5섹터, 6분류, 7한국PEER, 8매출TWD, 9MoM, 10YoY, 11누계YoY]
    function twFmtEok(twd) {{ return (twd / 1e8).toLocaleString('ko-KR', {{minimumFractionDigits: 1, maximumFractionDigits: 1}}); }}
    function twFmtPct(s) {{ return s === '' ? '-' : s + '%'; }}
    function twNum(s) {{ return s === '' ? -1e18 : parseFloat(s); }}
    var TW_COLS = [
        {{ name: '날짜',       disp: function(r) {{ return r[0]; }},            val: function(r) {{ return r[0]; }} }},
        {{ name: '발표일',     nofilter: true, disp: function(r) {{ return r[1]; }},   val: function(r) {{ return r[1]; }} }},
        {{ name: '코드',       disp: function(r) {{ return r[2]; }},            val: function(r) {{ return r[2]; }} }},
        {{ name: '기업명',     disp: function(r) {{ return r[3]; }},            val: function(r) {{ return r[3]; }} }},
        {{ name: '시장',       disp: function(r) {{ return r[4]; }},            val: function(r) {{ return r[4]; }} }},
        {{ name: '섹터',       disp: function(r) {{ return r[5]; }},            val: function(r) {{ return r[5]; }} }},
        {{ name: '분류',       disp: function(r) {{ return r[6]; }},            val: function(r) {{ return r[6]; }} }},
        {{ name: '한국 PEER',  disp: function(r) {{ return r[7] || '-'; }},     val: function(r) {{ return r[7]; }} }},
        {{ name: '매출(억TWD)', nofilter: true, disp: function(r) {{ return twFmtEok(r[8]); }}, val: function(r) {{ return r[8]; }} }},
        {{ name: 'MoM',        nofilter: true, disp: function(r) {{ return twFmtPct(r[9]); }},  val: function(r) {{ return twNum(r[9]); }} }},
        {{ name: 'YoY',        nofilter: true, disp: function(r) {{ return twFmtPct(r[10]); }}, val: function(r) {{ return twNum(r[10]); }} }},
        {{ name: '누계YoY',    nofilter: true, disp: function(r) {{ return twFmtPct(r[11]); }}, val: function(r) {{ return twNum(r[11]); }} }}
    ];
    var twSortCol = -1, twSortDir = 1;
    var twFilters = {{}};  // colIdx -> 선택된 표시값 배열 (키 없음 = 전체 허용)
    function twPasses(r, skipIdx) {{
        for (var i = 0; i < TW_COLS.length; i++) {{
            if (i === skipIdx) continue;
            var f = twFilters[i];
            if (f && f.indexOf(String(TW_COLS[i].disp(r))) === -1) return false;
        }}
        return true;
    }}
    function twSortClick(th) {{
        var i = Number(th.dataset.col);
        if (twSortCol === i) {{ twSortDir = -twSortDir; }} else {{ twSortCol = i; twSortDir = 1; }}
        twRender();
    }}
    function twCloseFilter() {{ var p = document.getElementById('twFilterPop'); if (p) p.parentNode.removeChild(p); }}
    function twOpenFilter(btn, ev) {{
        ev.stopPropagation();
        var i = Number(btn.dataset.col);
        var existing = document.getElementById('twFilterPop');
        var reopen = !(existing && Number(existing.dataset.col) === i);
        twCloseFilter();
        if (!reopen) return;  // 같은 칼럼 ▾ 재클릭 = 닫기
        var c = TW_COLS[i];
        // 고유값 목록: 다른 칼럼 필터가 적용된 집합 기준 (엑셀 자동필터 방식)
        var vals = [];
        TW_DATA.forEach(function(r) {{
            if (!twPasses(r, i)) return;
            var v = String(c.disp(r));
            if (vals.indexOf(v) === -1) vals.push(v);
        }});
        vals.sort();
        var cur = twFilters[i];
        var inner = '<label class="tw-filter-item"><input type="checkbox" id="twFAll" data-col="' + i + '"' + (!cur ? ' checked' : '') + ' onchange="twFilterAll(this)"> (전체 선택)</label>';
        vals.forEach(function(v) {{
            var on = (!cur || cur.indexOf(v) !== -1) ? ' checked' : '';
            inner += '<label class="tw-filter-item"><input type="checkbox" data-col="' + i + '" data-val="' + v.replace(/"/g, '&quot;') + '"' + on + ' onchange="twFilterVal(this)"> ' + (v === '' ? '(공란)' : v) + '</label>';
        }});
        var pop = document.createElement('div');
        pop.id = 'twFilterPop'; pop.className = 'tw-filter-pop'; pop.dataset.col = i;
        pop.onclick = function(e) {{ e.stopPropagation(); }};
        pop.innerHTML = inner;
        var host = document.querySelector('.tw-wrapper');
        host.appendChild(pop);
        var br = btn.getBoundingClientRect(), hr = host.getBoundingClientRect();
        pop.style.left = Math.max(0, br.left - hr.left - 8) + 'px';
        pop.style.top = (br.bottom - hr.top + 6) + 'px';
    }}
    function twFilterAll(box) {{
        var i = Number(box.dataset.col);
        var items = document.getElementById('twFilterPop').querySelectorAll('input[data-val]');
        for (var j = 0; j < items.length; j++) items[j].checked = box.checked;
        if (box.checked) {{ delete twFilters[i]; }} else {{ twFilters[i] = []; }}
        twRender();
    }}
    function twFilterVal(box) {{
        var i = Number(box.dataset.col);
        var items = document.getElementById('twFilterPop').querySelectorAll('input[data-val]');
        var sel = [];
        for (var j = 0; j < items.length; j++) {{ if (items[j].checked) sel.push(items[j].dataset.val); }}
        if (sel.length === items.length) {{ delete twFilters[i]; }} else {{ twFilters[i] = sel; }}
        var all = document.getElementById('twFAll');
        if (all) all.checked = sel.length === items.length;
        twRender();
    }}
    document.addEventListener('click', twCloseFilter);
    function twRender() {{
        var recs = TW_DATA.filter(function(r) {{ return twPasses(r, -1); }});
        if (twSortCol >= 0) {{
            var c = TW_COLS[twSortCol], dir = twSortDir;
            recs = recs.slice().sort(function(a, b) {{
                var va = c.val(a), vb = c.val(b);
                if (va < vb) return -dir; if (va > vb) return dir; return 0;
            }});
        }}
        var body = recs.map(function(r) {{
            return '<tr>' + TW_COLS.map(function(c) {{
                return '<td' + (c.cls ? ' class="' + c.cls + '"' : '') + '>' + c.disp(r) + '</td>';
            }}).join('') + '</tr>';
        }}).join('');
        var head = '<tr>' + TW_COLS.map(function(c, i) {{
            var arrow = twSortCol === i ? (twSortDir === 1 ? ' ▲' : ' ▼') : '';
            var fbtn = c.nofilter ? '' : '<span class="tw-filter-btn' + (twFilters[i] ? ' tw-filter-on' : '') + '" data-col="' + i + '" onclick="twOpenFilter(this, event)">▾</span>';
            return '<th data-col="' + i + '" onclick="twSortClick(this)">' + c.name + arrow + fbtn + '</th>';
        }}).join('') + '</tr>';
        document.getElementById('twTableHost').innerHTML =
            '<table class="tw-table"><thead>' + head + '</thead><tbody>' + body + '</tbody></table>';
    }}
    twRender();
    </script>
</body>
</html>"""


def main():
    rows = load_rows()
    html = build_html(rows).replace("__PAYLOAD__", json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"taiwan.html written: {len(rows)} rows, {os.path.getsize(OUT_PATH)//1024}KB")


if __name__ == "__main__":
    main()
