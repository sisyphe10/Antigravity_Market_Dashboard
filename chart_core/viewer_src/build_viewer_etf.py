# -*- coding: utf-8 -*-
"""단일종목 레버리지 ETF AUM/NAV 뷰어 — web-chart 표준 템플릿 기반 (etf_aum_raw.json → chart_viewer_etf.html)"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chart_common import apply_common
BASE = os.path.dirname(os.path.abspath(__file__))
TPL = r'C:\Users\user\.claude\skills\web-chart\assets\chart_template.html'
if not os.path.exists(TPL):
    TPL = os.path.join(BASE, 'chart_template.html')   # 맥미니 동봉본

raw = json.load(open(os.path.join(BASE, 'etf_aum_raw.json'), encoding='utf-8'))
px = json.load(open(os.path.join(BASE, 'underlying_px.json'), encoding='utf-8'))

def num(s):
    if s is None or s in ('', '-'):
        return None
    return float(str(s).replace(',', ''))

# 정규화: {name: {date: {aum(억원), nav(원)}}}
etf = {}
for name, d in raw.items():
    rows = {}
    for r in d['rows']:
        dt = r['TRD_DD'].replace('/', '-')
        aum = num(r['INVSTASST_NETASST_TOTAMT'])
        rows[dt] = {'aum': round(aum / 1e8, 1) if aum else None,
                    'nav': num(r['LST_NAV'])}
    etf[name] = rows

dates = sorted({dt for rows in etf.values() for dt in rows})
idx = {d: i for i, d in enumerate(dates)}
print(f'dates: {dates[0]} ~ {dates[-1]} ({len(dates)}d)')

MGR_COLOR = {'KODEX': '#DC2626', 'TIGER': '#EA580C', 'RISE': '#1F4E9C', 'ACE': '#1B5E20',
             'SOL': '#9333EA', 'KIWOOM': '#0072CE', 'PLUS': '#00854A', '1Q': '#404040'}

def meta(name):
    mgr = name.split()[0]
    under = '삼성전자' if '삼성전자' in name else 'SK하이닉스'
    fut = '선물' in name
    inv = '인버스' in name
    label = mgr + ('(선)' if fut else '')
    return mgr, under, inv, label

DATA = {'dates': dates, 'series': {}}

def put(key, getter):
    DATA['series'][key] = [getter(d) for d in dates]

# 개별 ETF AUM/NAV
groups_items = {'sec_lev': [], 'sk_lev': [], 'inv': []}
for name, rows in etf.items():
    mgr, under, inv, label = meta(name)
    gk = 'inv' if inv else ('sec_lev' if under == '삼성전자' else 'sk_lev')
    groups_items[gk].append((name, mgr, under, label))
    put(f'{name}|aum', lambda d, rows=rows: rows.get(d, {}).get('aum'))
    put(f'{name}|nav', lambda d, rows=rows: rows.get(d, {}).get('nav'))

# 합산 AUM (레버리지=인버스 제외)
def agg(names):
    out = []
    for d in dates:
        vals = [etf[n].get(d, {}).get('aum') for n in names]
        vals = [v for v in vals if v is not None]
        out.append(round(sum(vals), 1) if vals else None)
    return out

lev_sec = [n for n in etf if '삼성전자' in n and '인버스' not in n]
lev_sk = [n for n in etf if '하이닉스' in n and '인버스' not in n]
inv_all = [n for n in etf if '인버스' in n]
DATA['series']['agg|sec'] = agg(lev_sec)
DATA['series']['agg|sk'] = agg(lev_sk)
DATA['series']['agg|all'] = agg(lev_sec + lev_sk)
DATA['series']['agg|inv'] = agg(inv_all)

# 기초자산 주가 (naver: {yyyymmdd: close})
for code, key in [('005930', 'px|sec'), ('000660', 'px|sk')]:
    m = {f'{k[:4]}-{k[4:6]}-{k[6:]}': v for k, v in px[code].items()}
    put(key, lambda d, m=m: m.get(d))

def it(key, label, color, metric, fmt, noRebase=False):
    o = {'key': key, 'label': label, 'color': color, 'axis': 'idx', 'fmt': fmt, 'metric': metric}
    if noRebase:
        o['noRebase'] = True
    return o

def etf_items(gk, mk, fmt):
    out = []
    for name, mgr, under, label in sorted(groups_items[gk], key=lambda x: x[3]):
        lb = label if gk != 'inv' else f'{"삼전" if under == "삼성전자" else "SK"} {label}'
        out.append(it(f'{name}|{mk}', lb, MGR_COLOR[mgr], 'aum' if mk == 'aum' else 'price',
                      fmt, noRebase=(mk == 'aum')))
    return out

CONFIG = {
    'groups': [
        {'name': '합산 AUM', 'items': [
            it('agg|sec', '삼성전자 레버리지 합산', '#1F4E9C', 'aum', 'eok', True),
            it('agg|sk', 'SK하이닉스 레버리지 합산', '#00854A', 'aum', 'eok', True),
            it('agg|all', '레버리지 전체 (14종)', '#DC2626', 'aum', 'eok', True),
            it('agg|inv', '인버스2X 합산 (2종)', '#9333EA', 'aum', 'eok', True),
        ]},
        {'name': '기초자산 주가', 'items': [
            it('px|sec', '삼성전자', '#404040', 'price', 'won'),
            it('px|sk', 'SK하이닉스', '#EA580C', 'price', 'won'),
        ]},
        {'name': '삼성전자 AUM', 'items': etf_items('sec_lev', 'aum', 'eok')},
        {'name': 'SK하이닉스 AUM', 'items': etf_items('sk_lev', 'aum', 'eok')},
        {'name': '인버스2X AUM', 'items': etf_items('inv', 'aum', 'eok')},
        {'name': '삼성전자 NAV', 'items': etf_items('sec_lev', 'nav', 'won')},
        {'name': 'SK하이닉스 NAV', 'items': etf_items('sk_lev', 'nav', 'won')},
        {'name': '인버스2X NAV', 'items': etf_items('inv', 'nav', 'won')},
    ],
    'defaultOn': ['agg|sec', 'agg|sk'],
}

with open(TPL, encoding='utf-8') as f:
    html = f.read()

# (구 metric/noRebase 자동모드 패치는 2026-07-15 템플릿 개정으로 폐기 — 원값 기본+정규화 버튼이 템플릿 내장)

html = (html
        .replace('__TITLE__', '삼성전자 · SK하이닉스 단일종목 레버리지 ETF — AUM / NAV 추이')
        .replace('__NOTE__', '')
        .replace('__DLNAME__', 'single_stock_lev_etf')
        .replace('__CONFIG__', json.dumps(CONFIG, ensure_ascii=False, separators=(',', ':')))
        .replace('__DATA__', json.dumps(DATA, ensure_ascii=False, separators=(',', ':'))))

# ── 연도별 실적 섹션 (매출=꺾은선, 영업이익·순이익=바) — DART earnings_fin.json(억원) ──
fin = json.load(open(os.path.join(BASE, 'earnings_fin.json'), encoding='utf-8'))
years = sorted({int(y) for c in fin.values() for y in c})
def arr(name, k):  # 억원 → 조원(소수1)
    return [round(fin[name].get(str(y), {}).get(k, None) / 1e4, 1)
            if fin[name].get(str(y), {}).get(k) is not None else None for y in years]

EARN = {
    'years': years,
    'sets': [  # order: type, label, key, color / 매출=line, 영업·순익=bar
        ('line', '삼성전자 매출',   arr('삼성전자', 'revenue'),  '#1F4E9C'),
        ('line', 'SK하이닉스 매출', arr('SK하이닉스', 'revenue'), '#C2410C'),
        ('bar',  '삼성전자 영업이익',   arr('삼성전자', 'op'),  '#60A5FA'),
        ('bar',  '삼성전자 순이익',     arr('삼성전자', 'ni'),  '#BFDBFE'),
        ('bar',  'SK하이닉스 영업이익', arr('SK하이닉스', 'op'), '#FB923C'),
        ('bar',  'SK하이닉스 순이익',   arr('SK하이닉스', 'ni'), '#FED7AA'),
    ],
}
EARN_SECTION = (
    '<div class="wrap" style="padding-top:0">'
    '<h1 style="margin-top:4px">삼성전자 · SK하이닉스 연도별 실적 — 매출 · 영업이익 · 순이익</h1>'
    '<div class="chartbox" style="max-width:1080px"><canvas id="earnChart" style="height:520px"></canvas></div>'
    '</div>'
)
EARN_JS = '<script>' + '''
(function(){
  const E = __EARN__;
  const won = v => (v==null) ? '' : (v>=0?'':'-') + Math.abs(v).toFixed(1) + '조';
  const dss = E.sets.map(([type,label,data,color],i)=>({
    type, label, data, order: type==='line'?0:1,
    borderColor: color, backgroundColor: color,
    borderWidth: type==='line'?2.5:0, pointRadius: type==='line'?3.5:0,
    pointBackgroundColor: color, tension:0,
    barPercentage:0.9, categoryPercentage:0.72,
  }));
  const unitPlugin = { id:'earnUnit', afterDraw(ch){
    const {ctx,chartArea:a}=ch; ctx.save();
    ctx.font='11px Pretendard, sans-serif'; ctx.fillStyle='#888';
    ctx.textAlign='left'; ctx.textBaseline='bottom';
    ctx.fillText('(조원)', a.left, a.top-4); ctx.restore(); } };
  const zeroPlugin = { id:'earnZero', afterDraw(ch){
    const y=ch.scales.y; if(!y) return; const {ctx,chartArea:a}=ch;
    const zy=y.getPixelForValue(0); if(zy<a.top||zy>a.bottom) return;
    ctx.save(); ctx.strokeStyle='#111'; ctx.lineWidth=1;
    ctx.beginPath(); ctx.moveTo(a.left,zy); ctx.lineTo(a.right,zy); ctx.stroke(); ctx.restore(); } };
  new Chart(document.getElementById('earnChart'), {
    data: { labels: E.years, datasets: dss },
    plugins: [unitPlugin, zeroPlugin],
    options: {
      responsive:true, maintainAspectRatio:false, animation:false,
      interaction:{ mode:'index', intersect:false },
      scales:{
        x:{ grid:{display:false}, ticks:{ color:'#111', font:{size:12} }, border:{color:'#000'} },
        y:{ grid:{color:'#eee'}, ticks:{ color:'#111', font:{size:11}, callback:v=>v.toLocaleString() }, border:{color:'#000'} },
      },
      plugins:{
        legend:{ position:'bottom', labels:{ color:'#111', usePointStyle:true, pointStyleWidth:14, boxHeight:8, font:{size:12.5} } },
        tooltip:{ backgroundColor:'rgba(255,255,255,0.96)', titleColor:'#111', bodyColor:'#111',
          borderColor:'#c8c8c8', borderWidth:1, cornerRadius:8, padding:10, animation:false,
          titleFont:{weight:'bold',size:12.5}, bodyFont:{size:12}, boxWidth:12, boxHeight:8, usePointStyle:true,
          callbacks:{ title:it=>it[0].label+'년', label:c=>' '+c.dataset.label+': '+won(c.parsed.y) } },
      }
    }
  });
})();
'''.replace('__EARN__', json.dumps(EARN, ensure_ascii=False, separators=(',',':'))) + '</script>'

html = html.replace('</div>\n</div>\n<script>', '</div>\n</div>\n' + EARN_SECTION + '\n<script>', 1)
html = html.replace('\nbuild();\n</script>', '\nbuild();\n</script>\n' + EARN_JS, 1)

out = os.path.join(BASE, 'chart_viewer_etf.html')
with open(out, 'w', encoding='utf-8') as f:
    f.write(apply_common(html, 'chart_viewer_etf.html'))
print('저장:', out, f'{os.path.getsize(out)/1024:.0f}KB')

# 요약 수치 (보고용)
eok = lambda v: f'{v/1e4:.1f}조' if v >= 1e4 else f'{v:,.0f}억'
for k, lb in [('agg|sec', '삼성 합산'), ('agg|sk', 'SK 합산'), ('agg|all', '전체'), ('agg|inv', '인버스')]:
    s = DATA['series'][k]
    valid = [(dates[i], v) for i, v in enumerate(s) if v is not None]
    pk = max(valid, key=lambda x: x[1])
    print(f'{lb}: 첫날 {valid[0][0]} {eok(valid[0][1])} → 피크 {pk[0]} {eok(pk[1])} → 최근 {valid[-1][0]} {eok(valid[-1][1])} ({(valid[-1][1]/pk[1]-1)*100:+.1f}% vs 피크)')
