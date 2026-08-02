# -*- coding: utf-8 -*-
"""web-chart 스킬 표준 템플릿 기반 비교용 뷰어 v2 생성 (같은 데이터)"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from chart_common import apply_common
TPL = r'C:\Users\user\.claude\skills\web-chart\assets\chart_template.html'
if not os.path.exists(TPL):
    TPL = os.path.join(BASE, 'chart_template.html')   # 맥미니 동봉본

import pandas as pd
from daily_common import REPO

ps = pd.read_csv(os.path.join(BASE, 'price_short.csv'), parse_dates=['date'])
fu = pd.read_csv(os.path.join(BASE, 'futures.csv'), parse_dates=['date'])
mc = pd.read_csv(os.path.join(BASE, 'mktcap.csv'), parse_dates=['date'])
fx = pd.read_csv(os.path.join(BASE, 'fx.csv'), parse_dates=['date'])
us = pd.read_csv(os.path.join(BASE, 'us30y.csv'), parse_dates=['date'])
ix = pd.read_csv(os.path.join(BASE, 'index.csv'), parse_dates=['date'])
vk = pd.read_csv(os.path.join(BASE, 'vkospi.csv'), parse_dates=['date'])

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
fu['oi_val'] = fu['total_oi'] * 10 * fu['fut_close']   # 미결제약정 금액 (전월물 합산 계약수 × 승수 10주 × 최근월물 종가)
for nm in ['삼성전자', 'SK하이닉스']:
    DATA['series'][f'{nm}|price'] = series(ps, nm, 'close')
    DATA['series'][f'{nm}|mktcap'] = series(mc, nm, 'mktcap', 1e8)
    DATA['series'][f'{nm}|basis'] = series(fu, nm, 'basis_pct')
    DATA['series'][f'{nm}|oi']    = series(fu, nm, 'total_oi', 1e4)
    DATA['series'][f'{nm}|oival'] = series(fu, nm, 'oi_val', 1e8)
    DATA['series'][f'{nm}|short'] = series(ps, nm, 'short_amt', 1e8)

# 단일종목 레버리지 ETF 합산 AUM(억원) + NAV 지수(상장일=100, AUM가중) — 인버스 제외 각 7종, 2026-05-27 상장~
etf_raw = json.load(open(os.path.join(BASE, 'etf_aum_raw.json'), encoding='utf-8'))
fnum = lambda s: None if s in (None, '', '-') else float(str(s).replace(',', ''))
etf = {'삼성전자': {}, 'SK하이닉스': {}}   # {under: {name: {date: (aum억, nav)}}}
for name, d in etf_raw.items():
    if '인버스' in name:
        continue
    under = '삼성전자' if '삼성전자' in name else 'SK하이닉스'
    etf[under][name] = {r['TRD_DD'].replace('/', '-'): (fnum(r['INVSTASST_NETASST_TOTAMT']),
                                                        fnum(r['LST_NAV'])) for r in d['rows']}
for under, funds in etf.items():
    base_nav = {}   # 상장일 NAV
    for name, rows in funds.items():
        d0 = min(dt for dt, (a, nv) in rows.items() if nv)
        base_nav[name] = rows[d0][1]
    aum_s, nav_s = [None] * len(dates), [None] * len(dates)
    for dt, i in idx.items():
        tot_aum, wsum = 0.0, 0.0
        for name, rows in funds.items():
            a, nv = rows.get(dt, (None, None))
            if a:
                tot_aum += a / 1e8
            if a and nv:
                wsum += (a / 1e8) * (nv / base_nav[name] * 100)
        if tot_aum > 0:
            aum_s[i] = round(tot_aum, 1)
            nav_s[i] = round(wsum / tot_aum, 1)
    DATA['series'][f'{under}|etfaum'] = aum_s
    DATA['series'][f'{under}|etfnav'] = nav_s

# 원/달러 환율 (ECOS 731Y003 원/달러 종가, fx.csv)
fx_map = {d.strftime('%Y-%m-%d'): round(float(v), 1) for d, v in zip(fx['date'], fx['usdkrw'])}
DATA['series']['fx|usdkrw'] = [fx_map.get(d) for d in dates]

# 미국채 30년물 금리 (FRED DGS30, us30y.csv — T+1 공시라 마지막 1영업일 없음, 미 휴장일 null)
us_map = {d.strftime('%Y-%m-%d'): float(v) for d, v in zip(us['date'], us['us30y'])}
DATA['series']['fx|us30y'] = [us_map.get(d) for d in dates]

# KOSPI·KOSDAQ 종가 (pykrx, index.csv)
for col in ['kospi', 'kosdaq']:
    m = {d.strftime('%Y-%m-%d'): round(float(v), 2) for d, v in zip(ix['date'], ix[col])}
    DATA['series'][f'ix|{col}'] = [m.get(d) for d in dates]

# VKOSPI (KIS FHKUP03500100, U/0503 — vkospi.csv)
vk_map = {d.strftime('%Y-%m-%d'): round(float(v), 2) for d, v in zip(vk['date'], vk['vkospi'])}
DATA['series']['ix|vkospi'] = [vk_map.get(d) for d in dates]

# DRAM·NAND 현물가 (USD) — 대시보드 dataset.csv에서 직접 읽음(매일 자동 수집분).
# 주말 고시분은 이 페이지 날짜축(KRX 거래일)에 없어 자연 탈락, spanGaps로 연결.
MEM_PRODUCTS = {'DDR4 8Gb (1Gx8) 3200': 'ddr4', 'DDR5 16G (2Gx8) 4800/5600': 'ddr5',
                'MLC 64Gb 8GBx8': 'mlc64', 'MLC 32Gb 4GBx8': 'mlc32',
                'SLC 2Gb 256MBx8': 'slc2', 'SLC 1Gb 128MBx8': 'slc1'}
mem = pd.read_csv(os.path.join(REPO, 'dataset.csv'), encoding='utf-8-sig')
mem = mem[mem['데이터 타입'].isin(['DRAM', 'NAND'])]
for pname, key in MEM_PRODUCTS.items():
    sub = mem[mem['제품명'] == pname]
    m = {d: round(float(v), 4) for d, v in zip(sub['날짜'], sub['가격'])}
    DATA['series'][f'mem|{key}'] = [m.get(d) for d in dates]

PALETTE = {
    '삼성전자': {'price': '#404040', 'mktcap': '#A21CAF', 'basis': '#DC2626', 'oi': '#1B5E20',
              'oival': '#0891B2', 'short': '#1F4E9C', 'etfaum': '#C2185B', 'etfnav': '#B45309'},
    'SK하이닉스': {'price': '#EA580C', 'mktcap': '#64748B', 'basis': '#9333EA', 'oi': '#0072CE',
               'oival': '#713F12', 'short': '#00854A', 'etfaum': '#0F766E', 'etfnav': '#5B21B6'},
}
LABELS = {'price': '주가', 'mktcap': '시가총액', 'basis': '현선물 괴리율', 'oi': '미결제약정',
          'oival': '미결제약정 금액', 'short': '공매도 잔고',
          'etfaum': '레버리지 ETF AUM', 'etfnav': '레버리지 ETF NAV'}
FMTS = {'price': 'won', 'mktcap': 'eok', 'basis': 'pct', 'oi': 'man', 'oival': 'eok',
        'short': 'eok', 'etfaum': 'eok', 'etfnav': 'num'}

CONFIG = {
    'groups': [
        {'name': nm, 'items': [
            {'key': f'{nm}|{mk}', 'label': LABELS[mk], 'color': PALETTE[nm][mk],
             'axis': 'pct' if mk == 'basis' else 'idx', 'fmt': FMTS[mk]}
            for mk in ['price', 'mktcap', 'basis', 'oi', 'oival', 'short', 'etfaum', 'etfnav']]}
        for nm in ['삼성전자', 'SK하이닉스']
    ] + [
        {'name': '지수', 'prefix': False, 'items': [
            {'key': 'ix|kospi', 'label': 'KOSPI', 'color': '#111827', 'axis': 'idx', 'fmt': 'num'},
            {'key': 'ix|kosdaq', 'label': 'KOSDAQ', 'color': '#D97706', 'axis': 'idx', 'fmt': 'num'},
            {'key': 'ix|vkospi', 'label': 'VKOSPI', 'color': '#DB2777', 'axis': 'pct', 'fmt': 'num'}]},
        {'name': '매크로', 'prefix': False, 'items': [
            {'key': 'fx|usdkrw', 'label': '원/달러', 'color': '#4D7C0F', 'axis': 'idx', 'fmt': 'won1'},
            {'key': 'fx|us30y', 'label': '미국채 30Y 금리', 'color': '#B91C1C', 'axis': 'pct', 'fmt': 'pctlv'}]},
        {'name': 'DRAM·NAND 현물', 'prefix': False, 'items': [
            {'key': 'mem|ddr4', 'label': 'DDR4 8Gb 3200', 'color': '#DC2626', 'axis': 'idx', 'fmt': 'usd'},
            {'key': 'mem|ddr5', 'label': 'DDR5 16G 4800/5600', 'color': '#EA580C', 'axis': 'idx', 'fmt': 'usd'},
            {'key': 'mem|mlc64', 'label': 'NAND MLC 64Gb', 'color': '#1F4E9C', 'axis': 'idx', 'fmt': 'usd'},
            {'key': 'mem|mlc32', 'label': 'NAND MLC 32Gb', 'color': '#0072CE', 'axis': 'idx', 'fmt': 'usd'},
            {'key': 'mem|slc2', 'label': 'NAND SLC 2Gb', 'color': '#1B5E20', 'axis': 'idx', 'fmt': 'usd'},
            {'key': 'mem|slc1', 'label': 'NAND SLC 1Gb', 'color': '#00854A', 'axis': 'idx', 'fmt': 'usd'}]}
    ],
    'defaultOn': ['삼성전자|price', 'SK하이닉스|price'],
}

with open(TPL, encoding='utf-8') as f:
    html = f.read()

# 2026-07-15 확정분(원값 기본+정규화 버튼·Log 기본 ON·조 단위 금액 포맷)은 템플릿에 내장됨.
# usd 포맷터(DRAM·NAND 현물, 달러 소수 2자리)만 추가 패치.
html = html.replace(
    "  num:  v => v.toLocaleString(),",
    "  num:  v => v.toLocaleString(),\n"
    "  usd:  v => '$' + v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }),",
)
html = (html
        .replace('__TITLE__', '삼성전자 · SK하이닉스 — 현선물 격차 / 미결제약정 / 공매도 잔고 / 주가')
        .replace('__NOTE__', '')
        .replace('__DLNAME__', 'samsung_hynix_chart_v2')
        .replace('__CONFIG__', json.dumps(CONFIG, ensure_ascii=False, separators=(',', ':')))
        .replace('__DATA__', json.dumps(DATA, ensure_ascii=False, separators=(',', ':'))))

out = os.path.join(BASE, 'chart_viewer2.html')
with open(out, 'w', encoding='utf-8') as f:
    f.write(apply_common(html, 'chart_viewer2.html'))
print('저장:', out, f'{os.path.getsize(out)/1024:.0f}KB')
