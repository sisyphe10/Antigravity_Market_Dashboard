#!/usr/bin/env python3
"""AoE 차트 회귀 스냅샷 하네스 (P0, 2026-08-02).

fixture HTML을 로컬 HTTP로 서빙한 뒤 playwright(chromium)로 시나리오를 실행하고,
차트 상태(축·눈금·데이터 체크섬·범례·툴팁 제목·다운로드 파일명)를 JSON으로 덤프해
golden/ 과 비교한다. diff 0 = 통과. 의도된 규격 변경 시에만 --update 로 golden 갱신.

실행:  python chart_core/harness/run_snapshots.py [--update] [--only NAME]
전제:  pip install playwright && playwright install chromium
"""
import argparse
import http.server
import json
import os
import socketserver
import sys
import threading

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(BASE))
GOLDEN = os.path.join(BASE, 'golden')

# ── 공용 추출기: cmb(DATA) 차트 상태 ──────────────────────────────────────────
EXTRACT_CMB = r"""
() => {
  const el = document.getElementById('cmbDynamicChart');
  const ch = Chart.getChart(el);
  if (!ch) return { error: 'no-chart' };
  const rnd = v => (v == null || isNaN(v)) ? null : +Number(v).toPrecision(8);
  const axes = {};
  for (const [k, s] of Object.entries(ch.scales)) {
    axes[k] = { type: s.type, min: rnd(s.min), max: rnd(s.max),
                ticks: (s.ticks || []).map(t => String(t.label ?? t.value)) };
  }
  const datasets = ch.data.datasets.map(d => {
    const vals = d.data.filter(v => v != null && !isNaN(v));
    let sum = 0; vals.forEach(v => { sum += Number(v); });
    return { label: d.label, axis: d.yAxisID || 'y', n: vals.length,
             first: rnd(vals[0]), last: rnd(vals[vals.length - 1]), sum: rnd(sum) };
  });
  const legendEl = document.getElementById('cmbChartLegend');
  let fname = null;
  const orig = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function(){ fname = this.download; };
  try { downloadChartImage('cmbDynamicChart','AoE_Data','cmbChartLegend',['cmbDispChart','cmbRocChart']); }
  catch (e) { fname = 'DL_ERROR:' + e; }
  finally { HTMLAnchorElement.prototype.click = orig; }
  const disp = Chart.getChart(document.getElementById('cmbDispChart'));
  const roc = Chart.getChart(document.getElementById('cmbRocChart'));
  const panelInfo = c => c ? { n: c.data.datasets.length,
      labels: c.data.datasets.map(d => d.label),
      areaL: Math.round(c.chartArea.left), areaR: Math.round(c.chartArea.right) } : null;
  return {
    axes, datasets,
    legend: legendEl ? legendEl.textContent.trim().replace(/\s+/g, ' ') : null,
    tooltipTitle: ch.options.plugins.tooltip.callbacks.title([{ label: '2026-07-31' }]),
    paddingTop: ch.options.layout.padding.top,
    filename: fname,
    mainAreaL: Math.round(ch.chartArea.left), mainAreaR: Math.round(ch.chartArea.right),
    dispPanel: panelInfo(disp), rocPanel: panelInfo(roc)
  };
}
"""

# ── 공용 추출기: idx(INDICES) 차트 상태 — P3 코어 표준 라인 전환 검증 ─────────
EXTRACT_IDX = r"""
() => {
  const el = document.getElementById('idxDynamicChart');
  const ch = Chart.getChart(el);
  if (!ch) return { error: 'no-chart' };
  const rnd = v => (v == null || isNaN(v)) ? null : +Number(v).toPrecision(8);
  const axes = {};
  for (const [k, s] of Object.entries(ch.scales)) {
    axes[k] = { type: s.type, min: rnd(s.min), max: rnd(s.max),
                ticks: (s.ticks || []).map(t => String(t.label ?? t.value)) };
  }
  const datasets = ch.data.datasets.map(d => {
    const vals = d.data.filter(v => v != null && !isNaN(v));
    let sum = 0; vals.forEach(v => { sum += Number(v); });
    return { label: d.label, axis: d.yAxisID || 'y', n: vals.length,
             first: rnd(vals[0]), last: rnd(vals[vals.length - 1]), sum: rnd(sum) };
  });
  const legendEl = document.getElementById('idxChartLegend');
  const fam = ch._cmbFamily;
  return {
    axes, datasets,
    legend: legendEl ? legendEl.textContent.trim().replace(/\s+/g, ' ') : null,
    mode: ch._cmbMode, pinHost: !!ch._cmbPinHost,
    familyPeers: fam ? fam.peers.length : null,
    // 패밀리 격리: idx 패밀리가 DATA(cmb) 차트를 피어로 물고 있으면 안 된다
    isolated: fam ? fam.peers.every(c => c.canvas.id === 'idxDynamicChart') : null
  };
}
"""

def _extract_std(canvas_id, legend_id):
    """표준 라인 추출기 — idx 추출기의 캔버스·범례 id 치환판 (P3 전환 페이지 공용)."""
    return EXTRACT_IDX.replace('idxDynamicChart', canvas_id).replace('idxChartLegend', legend_id)


# ── 공용 추출기: web-chart 템플릿(뷰어) ──────────────────────────────────────
EXTRACT_VIEWER = r"""
() => {
  const ch = Chart.getChart(document.querySelector('canvas'));
  if (!ch) return { error: 'no-chart' };
  const rnd = v => (v == null || isNaN(v)) ? null : +Number(v).toPrecision(8);
  const axes = {};
  for (const [k, s] of Object.entries(ch.scales)) {
    axes[k] = { type: s.type, min: rnd(s.min), max: rnd(s.max),
                ticks: (s.ticks || []).map(t => String(t.label ?? t.value)) };
  }
  const datasets = ch.data.datasets.map(d => {
    const vals = d.data.filter(v => v != null && !isNaN(v));
    let sum = 0; vals.forEach(v => { sum += Number(v); });
    return { label: d.label, axis: d.yAxisID || 'y', n: vals.length,
             first: rnd(vals[0]), last: rnd(vals[vals.length - 1]), sum: rnd(sum) };
  });
  return { axes, datasets, legend: ch.legend.legendItems.map(li => li.text) };
}
"""

CLICK_ROW = """async (pattern) => {
  const rows = Array.from(document.querySelectorAll('#cmbSideTable tbody tr'));
  const r = rows.find(x => new RegExp(pattern).test(x.textContent));
  if (!r) return 'ROW_NOT_FOUND:' + pattern;
  r.click(); return 'ok';
}"""

SCENARIOS = [
    # (이름, fixture, [준비 스텝들], 추출기)  스텝: ('row', 패턴) | ('js', 코드) | ('wait', ms)
    ('data_deposit_eok_log',  'market', [('row', '고객예탁금')], EXTRACT_CMB),
    ('data_basis_neg_linear', 'market', [('row', '삼성전자 현선물 괴리율')], EXTRACT_CMB),
    ('data_dual_axis',        'market', [('row', '고객예탁금'), ('row', 'KOSPI$')], EXTRACT_CMB),
    ('data_normalized',       'market', [('row', '고객예탁금'), ('row', 'KOSPI$'),
        ('js', "document.getElementById('cmbNormBtn').click()")], EXTRACT_CMB),
    ('data_disp_panel',       'market', [('row', '고객예탁금'),
        ('js', "Array.from(document.querySelectorAll('.cmb-ma-btn')).find(b=>b.textContent.trim()==='20'&&b.id!=='cmbRocFreqM').click()")], EXTRACT_CMB),
    ('data_roc2_leading_index', 'market', [('row', '선행지수'), ('wait', 600),
        ('js', "document.getElementById('cmbRocBtn').click()")], EXTRACT_CMB),
    # P2a 인터랙션: 클릭 핀 (설정→같은 좌표 재클릭 해제까지 상태 확인)
    # ★P3: 핀·호버 상태는 전역이 아니라 chart._cmbFamily (다중 패밀리 격리) — 추출식만 변경, 의미 동일
    ('data_pin_click',        'market', [('row', '고객예탁금'), ('wait', 400),
        ('mouse', {'sel': '#cmbDynamicChart', 'rx': 0.5, 'ry': 0.5, 'action': 'click'}), ('wait', 300),
        ('js', "window.__pin1 = Chart.getChart(document.getElementById('cmbDynamicChart'))._cmbFamily.pin.date"),
        ('mouse', {'sel': '#cmbDynamicChart', 'rx': 0.5, 'ry': 0.5, 'action': 'click'}), ('wait', 300),
        ('js', "window.__pin2 = Chart.getChart(document.getElementById('cmbDynamicChart'))._cmbFamily.pin.date"),
        ('mouse', {'sel': '#cmbDynamicChart', 'rx': 0.7, 'ry': 0.5, 'action': 'click'}), ('wait', 300)],
        r"""() => { const f = Chart.getChart(document.getElementById('cmbDynamicChart'))._cmbFamily;
                    return { pin1: window.__pin1, pin2AfterSameClick: window.__pin2, pin3: f.pin.date,
                             hoverIdxType: typeof f.hover.idx }; }"""),
    # P2a 인터랙션: 크로스헤어 호버 + 마우스아웃 해제
    ('data_crosshair_hover',  'market', [('row', '고객예탁금'), ('wait', 400),
        ('mouse', {'sel': '#cmbDynamicChart', 'rx': 0.4, 'ry': 0.5, 'action': 'move'}), ('wait', 300),
        ('js', "var __f = Chart.getChart(document.getElementById('cmbDynamicChart'))._cmbFamily; window.__hov = { idx: __f.hover.idx, active: __f.hover.activeId }"),
        ('mouse', {'sel': 'body', 'rx': 0.01, 'ry': 0.99, 'action': 'move'}), ('wait', 300)],
        r"""() => ({ hover: window.__hov,
                     afterOut: Chart.getChart(document.getElementById('cmbDynamicChart'))._cmbFamily.hover.idx })"""),
    # P3: INDICES 표준 라인 전환 — 기본(7지수)·USD 모드 + 패밀리 격리.
    # ★Indices 서브탭을 먼저 열어야 캔버스가 실측 크기로 레이아웃된다 (숨김 탭에서 만든
    #   차트는 0×0 캔버스 눈금 — 사용자 화면과 다른 상태를 golden 으로 남기지 않기 위함)
    ('idx_default',           'market', [('js', 'mktSwitchTab(1)'), ('wait', 700)], EXTRACT_IDX),
    ('idx_usd',               'market', [('js', 'mktSwitchTab(1)'), ('wait', 700),
        ('js', "document.querySelector('.idx-mode-btn[data-mode=\"usd\"]').click()"), ('wait', 400)], EXTRACT_IDX),
    # P3: hotels ADR 표준 라인 전환 (독립 페이지 — 로드 즉시 렌더)
    ('hotel_adr',             'hotels', [('wait', 600)], _extract_std('hotelAdrChart', 'hotelAdrLegend')),
    ('viewer2_mktcap',        'viewer2', [
        ('js', "document.querySelector('[data-key=\"삼성전자|mktcap\"]').click()")], EXTRACT_VIEWER),
    ('viewer2_normalized',    'viewer2', [
        ('js', "document.querySelector('[data-key=\"삼성전자|mktcap\"]').click()"), ('wait', 400),
        ('js', "Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='정규화').click()")], EXTRACT_VIEWER),
]

FIXTURES = {
    'market':  '/chart_core/fixtures/market_baseline.html',
    'hotels':  '/chart_core/fixtures/hotels_baseline.html',
    'viewer2': '/chart_core/fixtures/chart_viewer2_baseline.html',
}


def serve(root, port):
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=root, **kw)
    srv = socketserver.ThreadingTCPServer(('127.0.0.1', port), handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def run(update=False, only=None):
    from playwright.sync_api import sync_playwright
    os.makedirs(GOLDEN, exist_ok=True)
    srv = serve(REPO, 0)
    port = srv.server_address[1]
    results, failures = {}, []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for name, fx, steps, extractor in SCENARIOS:
            if only and only not in name:
                continue
            page = browser.new_page(viewport={'width': 1900, 'height': 1000})
            page.goto(f'http://127.0.0.1:{port}{FIXTURES[fx]}', wait_until='load')
            page.wait_for_timeout(1200)
            for kind, arg in steps:
                if kind == 'row':
                    r = page.evaluate(CLICK_ROW, arg)
                    if r != 'ok':
                        print(f'  ! {name}: {r}')
                elif kind == 'js':
                    page.evaluate(f'() => {{ {arg} }}' if not arg.strip().startswith('(') else arg)
                elif kind == 'mouse':
                    box = page.locator(arg['sel']).bounding_box()
                    px = box['x'] + box['width'] * arg['rx']
                    py = box['y'] + box['height'] * arg['ry']
                    page.mouse.move(px, py)
                    if arg['action'] == 'click':
                        page.mouse.click(px, py)
                elif kind == 'wait':
                    page.wait_for_timeout(arg)
                page.wait_for_timeout(500)
            page.wait_for_timeout(700)
            snap = page.evaluate(extractor)
            page.close()
            results[name] = snap
            gpath = os.path.join(GOLDEN, name + '.json')
            dump = json.dumps(snap, ensure_ascii=False, indent=1, sort_keys=True)
            if update or not os.path.exists(gpath):
                with open(gpath, 'w', encoding='utf-8') as f:
                    f.write(dump)
                print(f'  golden written: {name}')
            else:
                with open(gpath, encoding='utf-8') as f:
                    want = f.read()
                if want != dump:
                    failures.append(name)
                    with open(os.path.join(GOLDEN, name + '.actual.json'), 'w', encoding='utf-8') as f:
                        f.write(dump)
                    print(f'  FAIL: {name} (actual 저장됨)')
                else:
                    print(f'  pass: {name}')
        browser.close()
    srv.shutdown()
    if failures:
        print(f'\n{len(failures)} 시나리오 불일치: {failures}')
        return 1
    print(f'\n전체 통과 ({len(results)} 시나리오)')
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--update', action='store_true')
    ap.add_argument('--only')
    a = ap.parse_args()
    sys.exit(run(update=a.update, only=a.only))
