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
from chart_common import nav_html  # noqa: E402

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
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
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
      <button class="dl" id="dl">Download</button>
    </div>
    <div class="chartbox"><div id="box" style="position:relative;height:450px"><canvas id="chart"></canvas></div></div>
  </div>
</div>
<script>
const D = __DATA__;
Chart.defaults.animation = false;
Chart.defaults.font.family = 'Pretendard, sans-serif';
const DPR = (window.devicePixelRatio || 1) * 2, NA = D.nActual;
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

const digitsFor = m => m < 10 ? 2 : (m < 100 ? 1 : 0);
const fmt = (v, d) => v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

function ticksFor(min, max) {
  const sp = (max - min) || 1, lo = min - sp * 0.05, hi = max + sp * 0.05;
  const raw = hi - lo, s0 = raw / 7, mag = Math.pow(10, Math.floor(Math.log10(s0)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= s0) || 10 * mag;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
  const gap = raw / 9;
  const all = [lo, ...out.filter(v => Math.abs(v - lo) > gap && Math.abs(v - hi) > gap), hi];
  while (all.length > 8) all.splice(Math.floor(all.length / 2), 1);
  return { lo, hi, ticks: all };
}

let cursor = null, pin = null;
const crosshair = { id: 'ch',
  afterEvent(c, a) {
    const e = a.event;
    if (e.type === 'mousemove') { cursor = { x: e.x, y: e.y }; a.changed = true; }
    else if (e.type === 'mouseout') { cursor = null; a.changed = true; }
    else if (e.type === 'click') {
      const el = c.getElementsAtEventForMode(e, 'index', { intersect: false }, false);
      const i = el.length ? el[0].index : null;
      pin = (pin === i) ? null : i; a.changed = true;
    }
  },
  afterDraw(c) {
    const { ctx, chartArea: ca } = c;
    if (cursor && cursor.x >= ca.left && cursor.x <= ca.right) {
      ctx.save(); ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
      ctx.strokeStyle = 'rgba(17,17,17,0.45)';
      ctx.beginPath(); ctx.moveTo(cursor.x, ca.top); ctx.lineTo(cursor.x, ca.bottom);
      ctx.moveTo(ca.left, cursor.y); ctx.lineTo(ca.right, cursor.y); ctx.stroke(); ctx.restore();
    }
    if (pin === null) return;
    const x = c.scales.x.getPixelForValue(pin), d = c._digits;
    ctx.save(); ctx.setLineDash([4, 4]); ctx.lineWidth = 1; ctx.strokeStyle = 'rgba(17,17,17,0.55)';
    ctx.beginPath(); ctx.moveTo(x, ca.top); ctx.lineTo(x, ca.bottom); ctx.stroke(); ctx.setLineDash([]);
    const lines = [D.years[pin]], cols = [null];
    c.data.datasets.forEach(s => {
      if (s._aux || s.data[pin] === null || s.data[pin] === undefined) return;
      lines.push(s.label + '   ' + fmt(s.data[pin], d)); cols.push(s.borderColor);
    });
    ctx.font = '13px Pretendard, sans-serif';
    const w = Math.max(...lines.map(t => ctx.measureText(t).width)) + 34, h = lines.length * 19 + 12;
    let px = x + 12; const py = ca.top + 10;
    if (px + w > ca.right) px = x - w - 12;
    ctx.fillStyle = 'rgba(255,255,255,0.96)'; ctx.strokeStyle = '#c8c8c8'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.roundRect(px, py, w, h, 8); ctx.fill(); ctx.stroke();
    ctx.textBaseline = 'middle';
    lines.forEach((t, i) => {
      const ty = py + 16 + i * 19;
      if (cols[i]) { ctx.fillStyle = cols[i]; ctx.beginPath(); ctx.arc(px + 14, ty, 4, 0, 7); ctx.fill(); }
      ctx.fillStyle = '#111';
      ctx.font = (i === 0 ? '700 13px' : '13px') + ' Pretendard, sans-serif';
      ctx.fillText(t, px + (cols[i] ? 24 : 12), ty);
    });
    ctx.restore();
  }
};

const endLabels = { id: 'el',
  afterDraw(c) {
    const { ctx, chartArea: ca } = c, d = c._digits;
    ctx.save();
    ctx.font = '13px Pretendard, sans-serif'; ctx.fillStyle = '#111';
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    ctx.fillText('($B)', ca.left - 6, ca.top - 12);
    const items = [];
    c.data.datasets.forEach(s => {
      if (s._aux) return;
      let li = -1; s.data.forEach((v, i) => { if (v !== null && v !== undefined) li = i; });
      if (li < 0) return;
      const py = c.scales.y.getPixelForValue(s.data[li]);
      items.push({ px: c.scales.x.getPixelForValue(li), py, y: py,
                   t: fmt(s.data[li], d), col: s.borderColor });
    });
    items.sort((a, b) => a.y - b.y);
    for (let i = 1; i < items.length; i++)
      if (items[i].y - items[i - 1].y < 15) items[i].y = items[i - 1].y + 15;
    for (let i = items.length - 1; i > 0; i--)
      if (items[i].y > ca.bottom) items[i - 1].y = Math.min(items[i - 1].y, items[i].y - 15);
    ctx.textBaseline = 'middle';
    const lx = ca.right + 8;
    items.forEach(it => {
      ctx.beginPath(); ctx.arc(it.px, it.py, 3, 0, 7); ctx.fillStyle = it.col; ctx.fill();
      if (Math.abs(it.y - it.py) > 2 || lx - it.px > 12) {
        ctx.strokeStyle = it.col + '99'; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(it.px + 4, it.py); ctx.lineTo(lx - 3, it.y); ctx.stroke();
      }
      ctx.fillStyle = it.col; ctx.font = '700 13px Pretendard, sans-serif';
      ctx.fillText(it.t, lx, it.y);
    });
    ctx.restore();
  }
};

let chart = null;
function build() {
  const rows = D.series.filter(s => sel.has(s.ticker));
  const dsets = rows.map(s => ({
    label: s.name, data: s.fcf, borderColor: s.color, backgroundColor: s.color,
    borderWidth: 2, pointRadius: 0, pointHitRadius: 6, spanGaps: true, tension: 0,
    segment: { borderDash: c => c.p0DataIndex >= NA - 1 ? [6, 4] : undefined }
  }));
  if (showZero) dsets.push({ label: '0', data: D.years.map(() => 0), borderColor: '#b8bcc2',
    borderWidth: 1.5, borderDash: [6, 4], pointRadius: 0, _aux: true, order: 99 });
  const vals = rows.flatMap(s => s.fcf).filter(v => v !== null && v !== undefined);
  if (showZero) vals.push(0);
  const { lo, hi, ticks } = vals.length ? ticksFor(Math.min(...vals), Math.max(...vals))
                                        : { lo: -1, hi: 1, ticks: [-1, 0, 1] };
  const digits = digitsFor(Math.max(Math.abs(lo), Math.abs(hi)));
  if (chart) chart.destroy();
  const cx = document.getElementById('chart').getContext('2d');
  cx.font = '700 13px Pretendard, sans-serif';
  const padR = Math.max(...(vals.length ? vals : [0]).map(v => cx.measureText(fmt(v, digits)).width)) + 23;
  chart = new Chart(cx, {
    type: 'line', data: { datasets: dsets, labels: D.years },
    options: {
      responsive: true, maintainAspectRatio: false, devicePixelRatio: DPR,
      layout: { padding: { right: padR, top: 24 } },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { mode: 'index', intersect: false, backgroundColor: 'rgba(255,255,255,0.96)',
          titleColor: '#111', bodyColor: '#111', borderColor: '#c8c8c8', borderWidth: 1,
          cornerRadius: 8, caretSize: 0, titleFont: { size: 13 }, bodyFont: { size: 13 },
          filter: i => !i.dataset._aux,
          callbacks: { label: i => ' ' + i.dataset.label + '   ' + fmt(i.parsed.y, digits) } }
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#000', font: { size: 12 } } },
        y: { min: lo, max: hi, afterBuildTicks: a => { a.ticks = ticks.map(v => ({ value: v })); },
             grid: { color: '#eceef0' },
             ticks: { color: '#000', font: { size: 12 }, callback: v => fmt(v, digits) } }
      }
    }, plugins: [crosshair, endLabels]
  });
  chart._digits = digits;
}

document.getElementById('btnZero').onclick = e => {
  showZero = !showZero; e.target.classList.toggle('active', showZero); build();
};
document.getElementById('dl').onclick = () => {
  const c = chart, prev = c.options.devicePixelRatio;
  try {
    c.options.devicePixelRatio = 4; c.resize(); c.draw();
    const off = document.createElement('canvas');
    off.width = c.canvas.width; off.height = c.canvas.height;
    const o = off.getContext('2d');
    o.fillStyle = '#fff'; o.fillRect(0, 0, off.width, off.height);
    o.drawImage(c.canvas, 0, 0);
    const a = document.createElement('a');
    a.download = 'bigtech_neocloud_FCF_' + new Date().toLocaleDateString('sv').replace(/-/g, '') + '.png';
    a.href = off.toDataURL('image/png'); a.click();
  } finally { c.options.devicePixelRatio = prev; c.resize(); c.draw(); }
};
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

out = (PAGE.replace('__TITLE__', '빅테크·네오클라우드 잉여현금흐름')
           .replace('__NAV__', nav_html('chart_viewer_fcf.html'))
           .replace('__DATA__', json.dumps(payload, ensure_ascii=False)))
for tok in ('__TITLE__', '__NAV__', '__DATA__'):
    assert tok not in out, f'미치환 토큰 {tok}'

OUT = os.path.join(BASE, 'chart_viewer_fcf.html')
open(OUT, 'w', encoding='utf-8').write(out)
print(f'WROTE chart_viewer_fcf.html — {len(payload["series"])}계열 / '
      f'{D["years"][0]}~{D["years"][-1]} ({N}개 시점)')
