# -*- coding: utf-8 -*-
"""CSV 2종 → 자립형 chart_viewer.html 생성 (WRAP 대시보드 CHART 탭 양식)

양식 출처: execution/create_dashboard.py wrap/Data CHART 탭
 - 사이드바: 색 바(4px) + 계열명 행, 클릭 토글(.active=검정 배경 흰 글씨)
 - Download 버튼: #dc2626 빨강, 클릭 순간 devicePixelRatio 4배 재렌더 후 PNG 저장
 - 크로스헤어(십자 보조선) + 데이터 카드(흰 배경 index 툴팁) + 끝값 라벨
 - 전 계열 실선, 눈금 검정, Pretendard
"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.abspath(__file__))

import pandas as pd

ps = pd.read_csv(os.path.join(BASE, 'price_short.csv'), parse_dates=['date'])
fu = pd.read_csv(os.path.join(BASE, 'futures.csv'), parse_dates=['date'])

dates = sorted(ps['date'].dt.strftime('%Y-%m-%d').unique())
idx = {d: i for i, d in enumerate(dates)}

def series(df, nm, col, scale=1.0):
    out = [None] * len(dates)
    sub = df[df['name'] == nm].dropna(subset=[col])
    for d, v in zip(sub['date'].dt.strftime('%Y-%m-%d'), sub[col]):
        if d in idx:
            out[idx[d]] = round(float(v) / scale, 4)
    return out

DATA = {'dates': dates, 'series': {}}
for nm in ['삼성전자', 'SK하이닉스']:
    DATA['series'][nm] = {
        'price':  series(ps, nm, 'close'),            # 원
        'basis':  series(fu, nm, 'basis_pct'),        # %
        'oi':     series(fu, nm, 'total_oi', 1e4),    # 만 계약
        'short':  series(ps, nm, 'short_amt', 1e8),   # 억원
    }

html = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>삼성전자·SK하이닉스 현선물/공매도 CHART</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  * { box-sizing: border-box; }
  body { font-family: 'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif;
         margin: 0; background: #fff; color: #111; }
  .wrap { max-width: 1500px; margin: 0 auto; padding: 24px 28px; }
  h1 { font-size: 20px; font-weight: 700; margin: 0 0 4px; }
  .sub { font-size: 12.5px; color: #666; margin-bottom: 16px; }
  .layout { display: flex; gap: 22px; align-items: flex-start; }
  .sidebar { width: 250px; flex: none; border: 1px solid #e5e5e5; border-radius: 10px; padding: 12px 12px; }
  .grp h3 { font-size: 13px; margin: 6px 4px 4px; font-weight: 700; }
  table.series { width: 100%; border-collapse: collapse; }
  table.series td { padding: 6px 8px; font-size: 13px; cursor: pointer; user-select: none; }
  table.series td.bar { width: 6px; padding: 0; }
  table.series td.bar div { width: 4px; height: 18px; border-radius: 2px; }
  tr.chart-item:hover td { background: #f4f4f4; }
  tr.chart-item.active td { background: #222; color: #fff; }
  .main { flex: 1; min-width: 0; }
  .controls { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; align-items: center; }
  button.rng { font-family: inherit; font-size: 12.5px; padding: 5px 14px; border-radius: 999px;
               border: 1px solid #d0d0d0; background: #fff; color: #111; cursor: pointer; }
  button.rng:hover { background: #f4f4f4; }
  button.rng.active { background: #404040; color: #fff; border-color: #404040; }
  button.util { font-family: inherit; font-size: 12.5px; padding: 5px 14px; border-radius: 999px;
                border: 1px solid #d0d0d0; background: #fff; color: #111; cursor: pointer; }
  button.dl { margin-left: auto; font-family: inherit; font-size: 13px; font-weight: 600; padding: 6px 14px;
              background: #dc2626; color: #fff; border: none; border-radius: 8px; cursor: pointer; }
  .chartbox { border: 1px solid #e5e5e5; border-radius: 10px; padding: 14px 16px 8px; }
  #chart { width: 100%; height: 560px; }
  .note { font-size: 11.5px; color: #888; margin-top: 8px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>삼성전자 · SK하이닉스 — 현선물 격차 / 미결제약정 / 공매도 잔고 / 주가</h1>
  <div class="sub">2025-01-02 ~ 2026-07-14 (공매도 잔고는 T+2 공시로 2026-07-10까지) · 괴리율 = 최근월물 종가 vs 현물 · 미결제약정 = 전 월물 합</div>
  <div class="layout">
    <div class="sidebar" id="sidebar"></div>
    <div class="main">
      <div class="controls">
        <button class="rng" data-rng="3">3M</button>
        <button class="rng" data-rng="6">6M</button>
        <button class="rng" data-rng="12">1Y</button>
        <button class="rng active" data-rng="0">전체</button>
        <button class="util" id="btn-clear">전체 해제</button>
        <button class="dl" id="btn-dl">Download</button>
      </div>
      <div class="chartbox"><canvas id="chart"></canvas></div>
      <div class="note">레벨 지표(주가·미결제약정·공매도잔고)는 표시 기간 시작=100 지수화(좌축), 현선물 괴리율은 % 원값(우축). 툴팁·끝값은 원값 표기.</div>
    </div>
  </div>
</div>
<script>
const RAW = __DATA__;

const METRICS = {
  price: { label: '주가',        unit: '원',     axis: 'idx', fmt: v => Math.round(v).toLocaleString() + '원' },
  basis: { label: '현선물 괴리율', unit: '%',     axis: 'pct', fmt: v => (v>=0?'+':'') + v.toFixed(1) + '%' },
  oi:    { label: '미결제약정',    unit: '만 계약', axis: 'idx', fmt: v => Math.round(v).toLocaleString() + '만 계약' },
  short: { label: '공매도 잔고',   unit: '억원',   axis: 'idx', fmt: v => Math.round(v).toLocaleString() + '억원' },
};
// 전 계열 실선 — 종목·지표 구분은 색으로 (대시보드 팔레트)
const COLORS = {
  '삼성전자|price': '#404040', '삼성전자|basis': '#DC2626', '삼성전자|oi': '#1B5E20', '삼성전자|short': '#1F4E9C',
  'SK하이닉스|price': '#EA580C', 'SK하이닉스|basis': '#9333EA', 'SK하이닉스|oi': '#0072CE', 'SK하이닉스|short': '#00854A',
};
const DEFAULT_ON = new Set(['삼성전자|price', 'SK하이닉스|price']);

// ── 사이드바 (wrap CHART 탭 양식: 색 바 + 행 클릭 토글) ──
const sb = document.getElementById('sidebar');
for (const stk of Object.keys(RAW.series)) {
  const g = document.createElement('div'); g.className = 'grp';
  g.innerHTML = '<h3>' + stk + '</h3>';
  const tb = document.createElement('table'); tb.className = 'series';
  for (const mk of Object.keys(METRICS)) {
    const key = stk + '|' + mk;
    const tr = document.createElement('tr');
    tr.className = 'chart-item' + (DEFAULT_ON.has(key) ? ' active' : '');
    tr.dataset.key = key;
    tr.innerHTML = '<td class="bar"><div style="background:' + COLORS[key] + '"></div></td><td>' + METRICS[mk].label + '</td>';
    tr.addEventListener('click', () => { tr.classList.toggle('active'); build(); });
    tb.appendChild(tr);
  }
  g.appendChild(tb);
  sb.appendChild(g);
}

// ── 크로스헤어(십자 보조선) ──
const crosshairPlugin = {
  id: 'crosshair',
  afterEvent(chart, args) {
    const e = args.event;
    chart.$cross = (args.inChartArea && (e.type === 'mousemove' || e.type === 'mouseenter'))
      ? { x: e.x, y: e.y } : null;
    args.changed = true;
  },
  afterDraw(chart) {
    const p = chart.$cross;
    if (!p) return;
    const { ctx, chartArea: a } = chart;
    ctx.save();
    ctx.strokeStyle = 'rgba(17,17,17,0.45)';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(p.x, a.top); ctx.lineTo(p.x, a.bottom);
    ctx.moveTo(a.left, p.y); ctx.lineTo(a.right, p.y);
    ctx.stroke();
    ctx.restore();
  }
};

// ── 끝값 라벨 (원값) ──
const endLabelPlugin = {
  id: 'endLabel',
  afterDatasetsDraw(chart) {
    const { ctx } = chart;
    ctx.save();
    ctx.font = 'bold 11px Pretendard, sans-serif';
    ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    const used = [];
    chart.data.datasets.forEach((ds, di) => {
      const meta = chart.getDatasetMeta(di);
      if (!meta.visible) return;
      let li = -1;
      for (let i = ds.data.length - 1; i >= 0; i--) if (ds.data[i] != null) { li = i; break; }
      if (li < 0) return;
      const el = meta.data[li];
      if (!el) return;
      let y = el.y;
      while (used.some(u => Math.abs(u - y) < 13)) y -= 13;
      used.push(y);
      ctx.fillStyle = ds.borderColor;
      ctx.fillText(ds.rawFmt(ds.rawData[li]), el.x + 6, y);
    });
    ctx.restore();
  }
};

let rangeMonths = 0;
let chart = null;

function visibleWindow() {
  const n = RAW.dates.length;
  if (!rangeMonths) return [0, n - 1];
  const end = new Date(RAW.dates[n - 1]);
  const from = new Date(end); from.setMonth(from.getMonth() - rangeMonths);
  const fs = from.toISOString().slice(0, 10);
  let s = 0;
  for (let i = 0; i < n; i++) if (RAW.dates[i] >= fs) { s = i; break; }
  return [s, n - 1];
}

function build() {
  const [s, e] = visibleWindow();
  const labels = RAW.dates.slice(s, e + 1);
  const datasets = [];
  document.querySelectorAll('#sidebar tr.chart-item.active').forEach(tr => {
    const [stk, mk] = tr.dataset.key.split('|');
    const m = METRICS[mk];
    const raw = RAW.series[stk][mk].slice(s, e + 1);
    let data = raw;
    if (m.axis === 'idx') {
      const base = raw.find(v => v != null);
      data = raw.map(v => v == null ? null : v / base * 100);
    }
    datasets.push({
      label: stk + ' ' + m.label, data, rawData: raw, rawFmt: m.fmt,
      borderColor: COLORS[tr.dataset.key], backgroundColor: COLORS[tr.dataset.key],
      borderWidth: 2, pointRadius: 0, pointHitRadius: 6, spanGaps: true, tension: 0,
      yAxisID: m.axis === 'idx' ? 'y' : 'y1',
    });
  });
  // 활성 계열이 전부 현선물 괴리율(basis, y1)일 때만 각 종목 괴리율 평균 수평 점선 추가
  const activeItems = [...document.querySelectorAll('#sidebar tr.chart-item.active')];
  const allBasis = activeItems.length > 0 && activeItems.every(tr => tr.dataset.key.split('|')[1] === 'basis');
  if (allBasis) {
    datasets.slice().forEach(ds => {
      const vals = ds.rawData.filter(v => v != null);
      if (!vals.length) return;
      const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
      datasets.push({
        label: ds.label + ' 평균', data: labels.map(() => avg),
        rawData: labels.map(() => avg),
        rawFmt: v => '평균 ' + (v >= 0 ? '+' : '') + v.toFixed(2) + '%',
        borderColor: ds.borderColor, backgroundColor: ds.backgroundColor,
        borderWidth: 1.5, borderDash: [6, 4], pointRadius: 0, pointHitRadius: 0,
        spanGaps: true, tension: 0, yAxisID: 'y1', isAvg: true,
      });
    });
  }
  const anyIdx = datasets.some(d => d.yAxisID === 'y');
  const anyPct = datasets.some(d => d.yAxisID === 'y1');
  if (chart) chart.destroy();
  chart = new Chart(document.getElementById('chart'), {
    type: 'line',
    data: { labels, datasets },
    plugins: [endLabelPlugin, crosshairPlugin],
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      layout: { padding: { right: 90 } },
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { grid: { color: 'rgba(176,176,176,0.35)', borderDash: [4, 4] },
             ticks: { color: '#111', maxTicksLimit: 10, maxRotation: 0,
                      callback(v) { const d = this.getLabelForValue(v);
                        return (rangeMonths && rangeMonths <= 6) ? d.slice(5).replace('-', '/') : d.slice(2, 7).replace('-', '/'); } } },
        y:  { display: anyIdx, position: 'left',
              title: { display: anyIdx, text: '지수화 (기간 시작 = 100)', color: '#111', font: { size: 11 } },
              grid: { color: 'rgba(176,176,176,0.35)', borderDash: [4, 4] }, ticks: { color: '#111' } },
        y1: { display: anyPct, position: 'right',
              title: { display: anyPct, text: '괴리율 (%)', color: '#111', font: { size: 11 } },
              grid: { drawOnChartArea: !anyIdx, color: 'rgba(176,176,176,0.35)', borderDash: [4, 4] },
              ticks: { color: '#111', callback: v => v.toFixed(1) + '%' } },
      },
      plugins: {
        legend: { position: 'bottom', labels: { color: '#111', usePointStyle: false, boxWidth: 22, boxHeight: 2,
                   filter: (item, data) => !data.datasets[item.datasetIndex].isAvg } },
        tooltip: {   // 데이터 카드 (흰 배경·검정 글씨)
          backgroundColor: 'rgba(255,255,255,0.96)',
          titleColor: '#111', bodyColor: '#111',
          borderColor: '#c8c8c8', borderWidth: 1,
          cornerRadius: 8, padding: 10,
          titleFont: { weight: 'bold', size: 12.5 }, bodyFont: { size: 12 },
          boxWidth: 14, boxHeight: 2, boxPadding: 4,
          caretSize: 0, displayColors: true,
          filter: item => !item.dataset.isAvg,
          callbacks: {
            label(c) {
              const ds = c.dataset, rv = ds.rawData[c.dataIndex];
              return ' ' + ds.label + ': ' + (rv == null ? '-' : ds.rawFmt(rv));
            }
          }
        }
      }
    }
  });
}

document.querySelectorAll('button[data-rng]').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('button[data-rng]').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  rangeMonths = +b.dataset.rng;
  build();
}));
document.getElementById('btn-clear').addEventListener('click', () => {
  document.querySelectorAll('#sidebar tr.chart-item.active').forEach(tr => tr.classList.remove('active'));
  build();
});

// ── Download: 클릭 순간에만 DPR 4배 재렌더 → 고해상도 PNG (대시보드 downloadChartImage 방식) ──
document.getElementById('btn-dl').addEventListener('click', () => {
  if (!chart) return;
  const DL_DPR = 4;
  const prev = chart.options.devicePixelRatio || (window.devicePixelRatio || 1);
  chart.$cross = null;
  chart.options.devicePixelRatio = DL_DPR;
  chart.resize(); chart.draw();
  try {
    const src = document.getElementById('chart');
    const c = document.createElement('canvas');
    c.width = src.width; c.height = src.height;
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height);
    ctx.drawImage(src, 0, 0);
    // sync toDataURL — 대시보드 downloadChartImage와 동일 (user activation 유지)
    const a = document.createElement('a');
    a.href = c.toDataURL('image/png');
    a.download = 'samsung_hynix_chart_' + new Date().toLocaleDateString('sv').replaceAll('-', '') + '.png';
    a.click();
  } finally {
    chart.options.devicePixelRatio = prev;
    chart.resize(); chart.draw();
  }
});

build();
</script>
</body>
</html>
"""

html = html.replace('__DATA__', json.dumps(DATA, ensure_ascii=False, separators=(',', ':')))
out = os.path.join(BASE, 'chart_viewer.html')
with open(out, 'w', encoding='utf-8') as f:
    f.write(html)
print('저장:', out, f'{os.path.getsize(out)/1024:.0f}KB')
