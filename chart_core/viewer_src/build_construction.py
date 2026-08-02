# -*- coding: utf-8 -*-
"""건설 6사 밸류에이션 통합 차트 (단일) — 시총÷수주잔고 · PBR · TTM PER를 사이드바 그룹으로 토글.
데이터: construction_daily.json(collect_construction_val.py 생성) — 세 지표 모두 **일별**.
  분모(자본·TTM순익·수주잔고)는 분기 계단, 분자(시총)는 일별 → 주가 변동이 매일 반영된다
  (2026-07-26 분기 스냅샷에서 전환. 분기말 값은 종전과 동일, 재현오차 0).
chart_viewer_construction.html 직접 생성(nav=True)."""
import os, json, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chart_common import apply_common
BASE = os.path.dirname(os.path.abspath(__file__))
TPL = r'C:\Users\user\.claude\skills\web-chart\assets\chart_template.html'
if not os.path.exists(TPL): TPL = os.path.join(BASE, 'chart_template.html')

daily = json.load(open(os.path.join(BASE, 'construction_daily.json'), encoding='utf-8'))
names, colors, keys = daily['names'], daily['colors'], daily['keys']
D = daily['data']


# 일별 축 = 전 종목 거래일 유니언
dates = sorted({d for n in names for d in D[n]['dates']})
series, has = {}, {}
for n in names:
    k = keys[n]
    pos = {d: i for i, d in enumerate(D[n]['dates'])}
    for fld in ('soojoo', 'pbr', 'per'):
        arr = D[n][fld]
        col = [arr[pos[d]] if d in pos else None for d in dates]
        series[f'{fld}_{k}'] = col
        has[f'{fld}_{k}'] = any(v is not None for v in col)
DATA = {'dates': dates, 'series': series}
def grp(title, fld, fmt):
    """값이 하나도 없는 계열(신규 3사 수주잔고)은 사이드바에서 제외."""
    return {'name': title, 'items': [
        {'key': f'{fld}_{keys[n]}', 'label': n, 'color': colors[n], 'axis': 'idx', 'fmt': fmt}
        for n in names if has[f'{fld}_{keys[n]}']]}


CONFIG = {'groups': [grp('시총÷수주잔고', 'soojoo', 'mult'), grp('PBR', 'pbr', 'pbr'),
                     grp('TTM PER', 'per', 'per')],
          'defaultOn': [f'pbr_{keys[n]}' for n in daily.get('default_on', names)
                        if has.get(f'pbr_{keys[n]}')]}

tpl = open(TPL, encoding='utf-8').read()
# 포매터 (mult/pbr/per)
tpl = tpl.replace("  num:  v => v.toLocaleString(),",
                  "  num:  v => v.toLocaleString(),\n  mult: v => v.toFixed(3) + '배',\n  pbr: v => v.toFixed(2) + '배',\n  per: v => v.toFixed(1) + '배',")
# 기본 기간 전체
tpl = tpl.replace("let rangeMonths = 'ytd';   // 기본 기간 = YTD (사용자 확정 2026-07-15)",
                  "let rangeMonths = 0;   // 기본 = 전체 (분기 밴드)")
tpl = tpl.replace('<button class="rng active" data-rng="ytd">YTD</button>\n        <button class="rng" data-rng="0">전체</button>',
                  '<button class="rng" data-rng="ytd">YTD</button>\n        <button class="rng active" data-rng="0">전체</button>')
# 평균 보조선 (활성 지표 계열, 표시창 기준) — 상단 '평균' 버튼으로 토글 (2026-07-26)
avg_block = '''  if (mode === 'raw' && avgOn) {
    activeItems.forEach(it => {
      if (it.axis !== 'idx') return;
      const vals = RAW.series[it.key].slice(s, e + 1).filter(v => v != null);
      if (!vals.length) return;
      const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
      const arr = labels.map(() => avg);
      datasets.push({ label: it.fullLabel + ' 평균', data: arr, rawData: arr,
        rawFmt: v => '평균 ' + v.toFixed(3), isAux: true,
        borderColor: it.color, backgroundColor: it.color, borderWidth: 1.5,
        borderDash: [6, 4], pointRadius: 0, pointHitRadius: 0, spanGaps: true, tension: 0,
        yAxisID: 'y' });
    });
  }
  const shortWin = labels.length <= 135;   // ~6개월 이하 창 → X라벨 MM/DD'''
tpl = tpl.replace("  const shortWin = labels.length <= 135;   // ~6개월 이하 창 → X라벨 MM/DD", avg_block)
tpl = tpl.replace('<button class="rng" id="btn-norm">정규화</button>',
                  '<button class="rng" id="btn-norm">정규화</button>\n'
                  '        <button class="rng active" id="btn-avg">평균</button>')
tpl = tpl.replace("let normMode = false;",
                  "let avgOn = true;         // '평균' 버튼 — 활성 계열의 표시창 평균 점선 (기본 ON)\n"
                  "let normMode = false;")
tpl = tpl.replace("""document.getElementById('btn-norm').addEventListener('click', () => {""",
                  """document.getElementById('btn-avg').addEventListener('click', () => {
  avgOn = !avgOn;
  document.getElementById('btn-avg').classList.toggle('active', avgOn);
  build();
});
document.getElementById('btn-norm').addEventListener('click', () => {""")

tpl = tpl.replace("__TITLE__", "건설 13사 밸류에이션 (PBR · TTM PER · 시총÷수주잔고)")
tpl = tpl.replace("__DLNAME__", "construction_valuation")
tpl = tpl.replace("__NOTE__", "")
tpl = tpl.replace("__DATA__", json.dumps(DATA, ensure_ascii=False, separators=(',', ':')))
tpl = tpl.replace("__CONFIG__", json.dumps(CONFIG, ensure_ascii=False, separators=(',', ':')))
open(os.path.join(BASE, 'chart_viewer_construction.html'), 'w', encoding='utf-8').write(apply_common(tpl, 'chart_viewer_construction.html', nav=True))
print("WROTE chart_viewer_construction.html (일별: 시총÷수주잔고·PBR·TTM PER)", "일수", len(dates), dates[0], "~", dates[-1])
