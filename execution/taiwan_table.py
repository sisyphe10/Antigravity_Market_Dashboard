# -*- coding: utf-8 -*-
"""Shared builder for the Taiwan monthly-revenue table.

Pure module (no create_dashboard import) so it can be embedded both as a
standalone page and as the Data-page 'Taiwan' button panel. Reads
taiwan_revenue.csv (fetch_taiwan_revenue.py output) + taiwan_universe.csv,
renders a flat table with excel-style header controls (click = asc/desc sort,
▾ = per-column value checkbox filter) plus a CSV Download button.

Exposes:
  load_rows()                    -> compact array payload
  TAIWAN_CSS                     -> <style> body (namespaced .tw-*)
  taiwan_panel_html(rows)        -> panel inner HTML (toolbar + table host)
  taiwan_script(rows)            -> <script> with payload embedded + twDownload
"""
import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "taiwan_revenue.csv")
UNIVERSE_CSV = os.path.join(ROOT, "taiwan_universe.csv")


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


# Namespaced (.tw-*) so it can coexist with the market page's own styles.
# .tw-container replaces the generic .table-container to avoid collisions.
TAIWAN_CSS = """
        .tw-wrapper { max-width: 1180px; margin: 0 auto; padding: 4px 24px 40px; position: relative; }
        .tw-toolbar { max-width: 1180px; margin: 0 auto; padding: 0 24px 10px; display: flex;
                      justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
        .tw-toolbar .tw-src { color: #666; font-size: 0.82rem; }
        .tw-dl-btn { background: #dc2626; color: #fff; border: none; border-radius: 8px;
                     padding: 6px 14px; font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit; }
        .tw-dl-btn:hover { background: #b91c1c; }
        .tw-container { overflow-x: auto; border: 1px solid #e5e7eb; border-radius: 12px; }
        .tw-table { width: 100%; border-collapse: collapse; }
        .tw-table th { position: sticky; top: 0; padding: 9px 10px; text-align: center;
                        font-size: 0.78rem; font-weight: 600; color: #374151; background: #f9fafb;
                        border-bottom: 1px solid #e5e7eb; white-space: nowrap; cursor: pointer; user-select: none; }
        .tw-table th:hover { color: #111; }
        .tw-table td { padding: 6px 10px; border-bottom: 1px solid #f3f4f6; color: #111;
                        white-space: nowrap; font-size: 0.8rem; text-align: center; }
        .tw-table tbody tr:last-child td { border-bottom: none; }
        .tw-table tbody tr:hover td { background: #f9fafb; }
        .tw-filter-btn { display: inline-block; margin-left: 4px; color: #9ca3af; cursor: pointer; }
        .tw-filter-btn:hover { color: #111; }
        .tw-filter-btn.tw-filter-on { color: #111; font-weight: 800; }
        .tw-filter-pop { position: absolute; z-index: 300; background: #fff; border: 1px solid #d1d5db;
                          border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,0.12); padding: 8px;
                          max-height: 280px; overflow-y: auto; min-width: 140px; }
        .tw-filter-item { display: block; padding: 3px 6px; font-size: 0.8rem; color: #111;
                           white-space: nowrap; cursor: pointer; }
        .tw-filter-item:hover { background: #f3f4f6; border-radius: 6px; }
        .tw-foot { max-width: 1180px; margin: 12px auto 0; padding: 0 24px; color: #999; font-size: 12px; text-align: center; }
        .tw-more-btn { display: block; width: 100%; padding: 10px; background: #f9fafb; border: none;
                       border-top: 1px solid #e5e7eb; color: #374151; font-size: 13px; font-weight: 600;
                       cursor: pointer; font-family: inherit; }
        .tw-more-btn:hover { background: #f3f4f6; color: #111; }
"""


def taiwan_panel_html(payload_rows):
    # 출처·종목수·최신월 안내 문구는 2026-07-12 사용자 요청으로 제거 (Download 버튼만 유지)
    return """
    <div class="tw-toolbar">
        <button class="tw-dl-btn" onclick="twDownload()">Download</button>
    </div>
    <div class="tw-wrapper">
        <div class="tw-container"><div id="twTableHost"></div></div>
    </div>
    <div class="tw-foot">발표일은 데이터 수집 시점 기준이며 과거분은 공란 · 본 자료는 참고용이며 투자 조언이 아닙니다</div>
    """


# Plain string (single braces) — payload injected via __PAYLOAD__ replace.
_TAIWAN_SCRIPT = """<script>
    var TW_DATA = __PAYLOAD__;
    // row: [0날짜, 1발표일, 2코드, 3기업명, 4시장, 5섹터, 6분류, 7한국PEER, 8매출TWD, 9MoM, 10YoY, 11누계YoY]
    function twFmtEok(twd) { return (twd / 1e8).toLocaleString('ko-KR', {minimumFractionDigits: 1, maximumFractionDigits: 1}); }
    function twFmtPct(s) { return s === '' ? '-' : s + '%'; }
    function twNum(s) { return s === '' ? -1e18 : parseFloat(s); }
    var TW_COLS = [
        { name: '날짜',       key: '날짜',      disp: function(r) { return r[0]; },            val: function(r) { return r[0]; } },
        { name: '발표일',     key: '발표일',    nofilter: true, disp: function(r) { return r[1]; },   val: function(r) { return r[1]; } },
        { name: '코드',       key: '코드',      disp: function(r) { return r[2]; },            val: function(r) { return r[2]; } },
        { name: '기업명',     key: '기업명',    disp: function(r) { return r[3]; },            val: function(r) { return r[3]; } },
        { name: '시장',       key: '시장',      disp: function(r) { return r[4]; },            val: function(r) { return r[4]; } },
        { name: '섹터',       key: '섹터',      disp: function(r) { return r[5]; },            val: function(r) { return r[5]; } },
        { name: '분류',       key: '분류',      disp: function(r) { return r[6]; },            val: function(r) { return r[6]; } },
        { name: '한국 PEER',  key: '한국PEER',  disp: function(r) { return r[7] || '-'; },     val: function(r) { return r[7]; } },
        { name: '매출(억TWD)', key: '매출_TWD', nofilter: true, disp: function(r) { return twFmtEok(r[8]); }, val: function(r) { return r[8]; } },
        { name: 'MoM',        key: 'MoM(%)',    nofilter: true, disp: function(r) { return twFmtPct(r[9]); },  val: function(r) { return twNum(r[9]); } },
        { name: 'YoY',        key: 'YoY(%)',    nofilter: true, disp: function(r) { return twFmtPct(r[10]); }, val: function(r) { return twNum(r[10]); } },
        { name: '누계YoY',    key: '누계YoY(%)', nofilter: true, disp: function(r) { return twFmtPct(r[11]); }, val: function(r) { return twNum(r[11]); } }
    ];
    var twSortCol = -1, twSortDir = 1;
    var TW_DEFAULT_ROWS = 30;   // 기본 표시 행수 (전체 보기 버튼으로 확장)
    var twShowAll = false;
    var twFilters = {};  // colIdx -> 선택된 표시값 배열 (키 없음 = 전체 허용)
    function twPasses(r, skipIdx) {
        for (var i = 0; i < TW_COLS.length; i++) {
            if (i === skipIdx) continue;
            var f = twFilters[i];
            if (f && f.indexOf(String(TW_COLS[i].disp(r))) === -1) return false;
        }
        return true;
    }
    function twSortClick(th) {
        var i = Number(th.dataset.col);
        if (twSortCol === i) { twSortDir = -twSortDir; } else { twSortCol = i; twSortDir = 1; }
        twRender();
    }
    function twCloseFilter() { var p = document.getElementById('twFilterPop'); if (p) p.parentNode.removeChild(p); }
    function twOpenFilter(btn, ev) {
        ev.stopPropagation();
        var i = Number(btn.dataset.col);
        var existing = document.getElementById('twFilterPop');
        var reopen = !(existing && Number(existing.dataset.col) === i);
        twCloseFilter();
        if (!reopen) return;  // 같은 칼럼 ▾ 재클릭 = 닫기
        var c = TW_COLS[i];
        // 고유값 목록: 다른 칼럼 필터가 적용된 집합 기준 (엑셀 자동필터 방식)
        var vals = [];
        TW_DATA.forEach(function(r) {
            if (!twPasses(r, i)) return;
            var v = String(c.disp(r));
            if (vals.indexOf(v) === -1) vals.push(v);
        });
        vals.sort();
        var cur = twFilters[i];
        var inner = '<label class="tw-filter-item"><input type="checkbox" id="twFAll" data-col="' + i + '"' + (!cur ? ' checked' : '') + ' onchange="twFilterAll(this)"> (전체 선택)</label>';
        vals.forEach(function(v) {
            var on = (!cur || cur.indexOf(v) !== -1) ? ' checked' : '';
            inner += '<label class="tw-filter-item"><input type="checkbox" data-col="' + i + '" data-val="' + v.replace(/"/g, '&quot;') + '"' + on + ' onchange="twFilterVal(this)"> ' + (v === '' ? '(공란)' : v) + '</label>';
        });
        var pop = document.createElement('div');
        pop.id = 'twFilterPop'; pop.className = 'tw-filter-pop'; pop.dataset.col = i;
        pop.onclick = function(e) { e.stopPropagation(); };
        pop.innerHTML = inner;
        var host = document.querySelector('.tw-wrapper');
        host.appendChild(pop);
        var br = btn.getBoundingClientRect(), hr = host.getBoundingClientRect();
        pop.style.left = Math.max(0, br.left - hr.left - 8) + 'px';
        pop.style.top = (br.bottom - hr.top + 6) + 'px';
    }
    function twFilterAll(box) {
        var i = Number(box.dataset.col);
        var items = document.getElementById('twFilterPop').querySelectorAll('input[data-val]');
        for (var j = 0; j < items.length; j++) items[j].checked = box.checked;
        if (box.checked) { delete twFilters[i]; } else { twFilters[i] = []; }
        twRender();
    }
    function twFilterVal(box) {
        var i = Number(box.dataset.col);
        var items = document.getElementById('twFilterPop').querySelectorAll('input[data-val]');
        var sel = [];
        for (var j = 0; j < items.length; j++) { if (items[j].checked) sel.push(items[j].dataset.val); }
        if (sel.length === items.length) { delete twFilters[i]; } else { twFilters[i] = sel; }
        var all = document.getElementById('twFAll');
        if (all) all.checked = sel.length === items.length;
        twRender();
    }
    document.addEventListener('click', twCloseFilter);
    function twCurrentRecords() {
        var recs = TW_DATA.filter(function(r) { return twPasses(r, -1); });
        if (twSortCol >= 0) {
            var c = TW_COLS[twSortCol], dir = twSortDir;
            recs = recs.slice().sort(function(a, b) {
                var va = c.val(a), vb = c.val(b);
                if (va < vb) return -dir; if (va > vb) return dir; return 0;
            });
        }
        return recs;
    }
    function twToggleAll() { twShowAll = !twShowAll; twRender(); }
    function twRender() {
        var recs = twCurrentRecords();
        var total = recs.length;
        var shown = (!twShowAll && total > TW_DEFAULT_ROWS) ? recs.slice(0, TW_DEFAULT_ROWS) : recs;
        var body = shown.map(function(r) {
            return '<tr>' + TW_COLS.map(function(c) {
                return '<td' + (c.cls ? ' class="' + c.cls + '"' : '') + '>' + c.disp(r) + '</td>';
            }).join('') + '</tr>';
        }).join('');
        var head = '<tr>' + TW_COLS.map(function(c, i) {
            var arrow = twSortCol === i ? (twSortDir === 1 ? ' ▲' : ' ▼') : '';
            var fbtn = c.nofilter ? '' : '<span class="tw-filter-btn' + (twFilters[i] ? ' tw-filter-on' : '') + '" data-col="' + i + '" onclick="twOpenFilter(this, event)">▾</span>';
            return '<th data-col="' + i + '" onclick="twSortClick(this)">' + c.name + arrow + fbtn + '</th>';
        }).join('') + '</tr>';
        var more = '';
        if (total > TW_DEFAULT_ROWS) {
            more = twShowAll
                ? '<button class="tw-more-btn" onclick="twToggleAll()">최근 ' + TW_DEFAULT_ROWS + '개만 보기</button>'
                : '<button class="tw-more-btn" onclick="twToggleAll()">전체 보기 (' + total.toLocaleString('ko-KR') + '행)</button>';
        }
        document.getElementById('twTableHost').innerHTML =
            '<table class="tw-table"><thead>' + head + '</thead><tbody>' + body + '</tbody></table>' + more;
    }
    // 현재 필터·정렬 상태의 데이터를 CSV로 내려받기 (Excel 한글 호환 위해 UTF-8 BOM)
    function twDownload() {
        var recs = twCurrentRecords();
        var header = TW_COLS.map(function(c) { return c.key; });
        function esc(v) { var s = String(v); return /[",\\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }
        var lines = [header.map(esc).join(',')];
        recs.forEach(function(r) {
            lines.push([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7] || '', r[8], r[9], r[10], r[11]].map(esc).join(','));
        });
        var blob = new Blob(['\\ufeff' + lines.join('\\n')], { type: 'text/csv;charset=utf-8;' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url; a.download = 'taiwan_revenue.csv';
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
    twRender();
    </script>"""


def taiwan_script(payload_rows):
    return _TAIWAN_SCRIPT.replace(
        "__PAYLOAD__", json.dumps(payload_rows, ensure_ascii=False, separators=(",", ":")))
