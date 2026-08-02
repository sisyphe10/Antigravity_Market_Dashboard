# -*- coding: utf-8 -*-
"""건설 3사 PBR·PER 일별 밴드 뷰어 (KRX get_market_fundamental, 2005~). construction_pbr_per.json 기반.
★KRX PBR/PER는 연간 확정 BPS/EPS 기준(계단식)이라 장기 밴드·사이클 고점용. datalake kr_fundamental 백필 후 그쪽으로 재소싱 예정."""
import os, json, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chart_common import apply_common
BASE = os.path.dirname(os.path.abspath(__file__))
TPL = r'C:\Users\user\.claude\skills\web-chart\assets\chart_template.html'
if not os.path.exists(TPL):
    TPL = os.path.join(BASE, 'chart_template.html')   # 맥미니 동봉본
raw = json.load(open(os.path.join(BASE, 'construction_pbr_per.json'), encoding='utf-8'))
colors = {"GS건설": "#1F4E9C", "아이에스동서": "#DC2626", "자이에스앤디": "#00854A"}
keys = {"GS건설": "gs", "아이에스동서": "isds", "자이에스앤디": "xnd"}
names = ["GS건설", "아이에스동서", "자이에스앤디"]

# 날짜 유니언
alld = set()
pbr = {n: {} for n in names}; per = {n: {} for n in names}
for n in names:
    for d, pb, pe in raw[n]['rows']:
        alld.add(d)
        pbr[n][d] = round(pb, 3) if (pb is not None and pb > 0) else None
        per[n][d] = round(pe, 2) if (pe is not None and pe > 0) else None
dates = sorted(alld)
series = {}
for n in names:
    series[f'pbr_{keys[n]}'] = [pbr[n].get(d) for d in dates]
    series[f'per_{keys[n]}'] = [per[n].get(d) for d in dates]
DATA = {'dates': dates, 'series': series}
CONFIG = {'groups': [
    {'name': 'PBR', 'items': [{'key': f'pbr_{keys[n]}', 'label': n, 'color': colors[n], 'axis': 'idx', 'fmt': 'pbr'} for n in names]},
    {'name': 'PER', 'items': [{'key': f'per_{keys[n]}', 'label': n, 'color': colors[n], 'axis': 'idx', 'fmt': 'per'} for n in names]},
], 'defaultOn': [f'pbr_{keys[n]}' for n in names]}

tpl = open(TPL, encoding='utf-8').read()
# pbr/per 포매터 추가
tpl = tpl.replace("  num:  v => v.toLocaleString(),",
                  "  num:  v => v.toLocaleString(),\n  pbr: v => v.toFixed(2) + '배',\n  per: v => v.toFixed(1) + '배',")
# 기본 기간 전체
tpl = tpl.replace("let rangeMonths = 'ytd';   // 기본 기간 = YTD (사용자 확정 2026-07-15)",
                  "let rangeMonths = 0;   // 기본 = 전체 (장기 밴드)")
tpl = tpl.replace('<button class="rng active" data-rng="ytd">YTD</button>\n        <button class="rng" data-rng="0">전체</button>',
                  '<button class="rng" data-rng="ytd">YTD</button>\n        <button class="rng active" data-rng="0">전체</button>')
tpl = tpl.replace("__TITLE__", "건설 3사 · 분기 PBR / TTM PER (DART 연결)")
tpl = tpl.replace("__DLNAME__", "construction_pbr_per")
tpl = tpl.replace("__NOTE__", "")
tpl = tpl.replace("__DATA__", json.dumps(DATA, ensure_ascii=False, separators=(',', ':')))
tpl = tpl.replace("__CONFIG__", json.dumps(CONFIG, ensure_ascii=False, separators=(',', ':')))
open(os.path.join(BASE, 'con_pbrper.html'), 'w', encoding='utf-8').write(apply_common(tpl, nav=False))
print("WROTE chart_viewer_construction_val.html; dates", len(dates), "series", list(series.keys()))
