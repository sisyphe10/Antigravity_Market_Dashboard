# -*- coding: utf-8 -*-
"""빅테크·네오클라우드 잉여현금흐름 (달력연도) — fcf_data.json → chart_viewer_fcf.html

FCF = 영업현금흐름 − 유형자산 취득(현금). 실적 CY2023~CY2025 는 SEC EDGAR XBRL 원문,
스페이스X 만 424B4 투자설명서(2026-06-12 상장, SPCX) 파싱. CY2026E~CY2028E 는 공개
capex 가이던스·컨센서스 기반 추정으로 셀 단위 신뢰도(A/B/C)를 데이터에 보존한다.

★수집기 없음 = 데일리 파이프라인(run_daily.py) 제외. 추정치 갱신은 수동 —
방법론·출처는 work/analysis/260727_빅테크_네오클라우드_FCF/SOURCES.md.
연간 6개 시점이라 기간 버튼·Log·정규화는 두지 않는다(FCF 음수라 Log 자체가 불가).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chart_common import core_js, nav_html  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(BASE, 'fcf_data.json'), encoding='utf-8'))

S = D['series']
by = {r['ticker']: r for r in S}
N = len(D['years'])
agg = lambda ks: [round(sum(by[k]['fcf'][i] for k in ks if by[k]['fcf'][i] is not None), 1)
                  for i in range(N)]
ALL = [r['ticker'] for r in S]
NEO = ['CRWV', 'NBIS', 'IREN', 'APLD', 'WULF', 'CIFR']
HYP = ['MSFT', 'GOOGL', 'AMZN', 'META']

EXTRA = [
    {'ticker': '_ALL', 'name': '합계 14종', 'group': '집계', 'color': '#111111', 'fcf': agg(ALL)},
    {'ticker': '_EXNA', 'name': '합계 (엔비디아·애플 제외)', 'group': '집계', 'color': '#DC2626',
     'fcf': agg([t for t in ALL if t not in ('NVDA', 'AAPL')])},
    {'ticker': '_HYP', 'name': '하이퍼스케일러 4종', 'group': '집계', 'color': '#1F4E9C', 'fcf': agg(HYP)},
    {'ticker': '_NEO', 'name': '네오클라우드 6종', 'group': '집계', 'color': '#EA580C', 'fcf': agg(NEO)},
]
payload = {'years': D['years'], 'nActual': D['nActual'],
           'groups': ['집계', 'M7', '네오클라우드', 'SpaceX'],
           'series': EXTRA + [{k: r[k] for k in ('ticker', 'name', 'group', 'color', 'fcf')}
                              for r in S]}

PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js"></script>
<script>
__AOE_CHART_CORE__
</script>
<style>
  * { box-sizing: border-box; }
  body { font-family: Pretendard, -apple-system, sans-serif; color: #111;
         background: #f7f8f9; margin: 0; padding: 22px 26px 40px; }
  h1 { font-size: 20px; font-weight: 700; margin: 0 0 12px; }
  .wrap { display: flex; gap: 16px; align-items: flex-start; }
  .side { width: 214px; flex: 0 0 214px; background: #fff; border-radius: 12px;
          box-shadow: 0 1px 3px rgba(0,0,0,.08); padding: 10px 8px; max-height: 600px; overflow-y: auto; }
  .side h3 { font-size: 11px; font-weight: 700; color: #888; letter-spacing: .4px; margin: 10px 6px 5px; }
  .side h3:first-child { margin-top: 2px; }
  .item { display: flex; align-items: center; padding: 5px 7px; border-radius: 5px;
          font-size: 12.5px; cursor: pointer; }
  .item:hover { background: #f4f4f4; }
  .item.on { background: #222; color: #fff; }
  .cbar { display: inline-block; width: 4px; height: 12px; border-radius: 2px; margin-right: 7px; flex: 0 0 4px; }
  .main { min-width: 0; }
  .controls { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
  .rng { font-family: inherit; font-size: 12.5px; padding: 5px 13px; border-radius: 8px;
         border: 1px solid #d0d0d0; background: #fff; color: #111; cursor: pointer; }
  .rng.active { background: #404040; color: #fff; border-color: #404040; }
  .dl { font-family: inherit; font-size: 12.5px; font-weight: 600; padding: 6px 14px;
        border-radius: 8px; border: none; background: #dc2626; color: #fff; cursor: pointer; }
  .chartbox { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.08); padding: 16px 18px; }
</style></head><body>
<h1>__TITLE__</h1>
__NAV__
<div class="wrap">
  <div class="side" id="side"></div>
  <div class="main">
    <div class="controls">
      <button class="rng active" id="btnZero">0선</button>
      <span style="margin-left:auto"></span>
      <button class="rng" id="cp" style="background:#0891b2;color:#fff;border:none;font-weight:600">Copy</button>
      <button class="dl" id="dl">Download</button>
    </div>
    <div class="chartbox"><div id="box" style="position:relative;height:450px"><canvas id="chart"></canvas></div><div id="chartLegend" style="margin-top:10px;text-align:center"></div></div>
  </div>
</div>
<script>
const D = __DATA__;
Chart.defaults.animation = false;
Chart.defaults.font.family = 'Pretendard, sans-serif';
const NA = D.nActual;
let sel = new Set(['_ALL', '_EXNA']), showZero = true;

const side = document.getElementById('side');
D.groups.forEach(g => {
  const rs = D.series.filter(s => s.group === g);
  if (!rs.length) return;
  const h = document.createElement('h3'); h.textContent = g; side.appendChild(h);
  rs.forEach(s => {
    const d = document.createElement('div');
    d.className = 'item' + (sel.has(s.ticker) ? ' on' : '');
    d.innerHTML = '<span class="cbar" style="background:' + s.color + '"></span>' + s.name;
    d.onclick = () => {
      sel.has(s.ticker) ? sel.delete(s.ticker) : sel.add(s.ticker);
      d.classList.toggle('on'); build();
    };
    side.appendChild(d);
  });
});

// ── 렌더 = 코어 표준 라인 cmbRenderCharts (P4b 2026-08-02) — DATA(cmb) 양식 단일 정본.
//    추정 구간 점선은 dataset.segment 로 코어에 그대로 전달(패스스루), 0선은 _cmbAux 보조 계열.
let chart = null;
function build() {
  const rows = D.series.filter(s => sel.has(s.ticker));
  const unitMap = {};
  const dsets = rows.map(s => {
    unitMap[s.name] = '$B';
    return {
      label: s.name, data: s.fcf, borderColor: s.color, backgroundColor: 'transparent',
      borderWidth: 3, borderJoinStyle: 'round', borderCapStyle: 'round',
      pointRadius: 0, tension: 0.4, cubicInterpolationMode: 'monotone', spanGaps: true,
      yAxisID: 'y',
      segment: { borderDash: c => c.p0DataIndex >= NA - 1 ? [6, 4] : undefined }
    };
  });
  if (showZero) dsets.push({ label: '0', data: D.years.map(() => 0), borderColor: '#b8bcc2',
    borderWidth: 1.5, borderDash: [6, 4], pointRadius: 0, spanGaps: true, tension: 0,
    _cmbAux: true, _skipEndLabel: true, order: 99, yAxisID: 'y' });
  chart = cmbRenderCharts({
    labels: D.years.map(String), datasets: dsets, dispDatasets: [], rocDatasets: [],
    mode: 'raw1', yEok: false, y1Eok: false,
    axAssign: dsets.filter(d => !d._cmbAux).map(d => ({ name: d.label, ax: 'y' })),
    unitMap,
    charts: { main: chart, disp: null, roc: null },
    ids: { canvas: 'chart', legend: 'chartLegend', dispPanel: null, rocPanel: null },
    xLabel: s => s || '',
    logOn: false
  }).main;
}

document.getElementById('btnZero').onclick = e => {
  showZero = !showZero; e.target.classList.toggle('active', showZero); build();
};
document.getElementById('dl').onclick = () => downloadChartImage('chart', 'bigtech_neocloud_FCF', 'chartLegend');
document.getElementById('cp').onclick = e => copyChartImage('chart', 'chartLegend', null, e.currentTarget);
build();
// 사이즈 = 세미나 단일 (800x450, 폴더 공통 규약)
(function () {
  const w = (800 + 34) + 'px';
  document.querySelector('.chartbox').style.width = w;
  document.querySelector('.controls').style.width = w;
  document.getElementById('box').style.height = '450px';
  if (chart) chart.resize();
})();
</script>
</body></html>
"""

out = (PAGE.replace('__AOE_CHART_CORE__', core_js())
           .replace('__TITLE__', '빅테크·네오클라우드 잉여현금흐름')
           .replace('__NAV__', nav_html('chart_viewer_fcf.html'))
           .replace('__DATA__', json.dumps(payload, ensure_ascii=False)))
for tok in ('__TITLE__', '__NAV__', '__DATA__', '__AOE_CHART_CORE__'):
    assert tok not in out, f'미치환 토큰 {tok}'

OUT = os.path.join(BASE, 'chart_viewer_fcf.html')
open(OUT, 'w', encoding='utf-8').write(out)
print(f'WROTE chart_viewer_fcf.html — {len(payload["series"])}계열 / '
      f'{D["years"][0]}~{D["years"][-1]} ({N}개 시점)')
