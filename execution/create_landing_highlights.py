#!/usr/bin/env python3
"""랜딩 페이지(index.html) 회전 위젯용 데이터 생성기.

출력: landing_highlights.json
- updated_at, slots[]
- 각 슬롯: id, category, color, tone(fact|interpret), text, href, spark{series,trend}|null
- 입력 누락 슬롯은 skip, 빌더 예외는 로그만 남기고 다른 슬롯은 살림
- atomic write (tmp -> os.replace)
"""
import csv
import json
import os
import random
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'landing_highlights.json'

CATEGORY_COLORS = {
    'Market':    '#2d7a3a',
    'Memory':    '#2d7a3a',
    'Commodity': '#2d7a3a',
    'Crypto':    '#2d7a3a',
    'FX':        '#2d7a3a',
    'Index':     '#2d7a3a',
    'Rate':      '#2d7a3a',
    'WRAP':      '#1e40af',
    'Alert':     '#c2410c',
    'Universe':  '#6B21A8',
    'SEIBro':    '#0369a1',
    'Featured':  '#d97706',
    'ETF':       '#6366f1',
}

SPARK_DAYS = 90

INTERPRET_VARIANTS = {
    'up_strong':      ['반등 신호', '상승 모멘텀', '수요 회복', '추세 전환 가능성'],
    'up_mild':        ['저점 형성 가능성', '점진적 반등', '하방 압력 완화'],
    'down_strong':    ['약세 지속', '공급 부담 가중', '조정 국면 확대', '수요 위축'],
    'down_mild':      ['상승세 둔화', '단기 조정', '숨고르기'],
    'flat':           ['박스권 유지', '관망세 지속', '방향성 부재'],
    'breadth_strong': ['위험자산 동반 강세', '광범위한 상승', '시장 전반 호조'],
    'breadth_weak':   ['광범위한 조정', '리스크 오프 분위기', '선별적 약세'],
    'breadth_mixed':  ['혼조 양상', '엇갈린 흐름', '방향성 부재'],
    'corr_high':      ['분산효과 약함', '한 방향 변동성 노출 큼', '리스크 집중'],
    'corr_low':       ['분산효과 양호', '상관 낮아 안정적'],
    'vix_calm':       ['위험선호 회복', '시장 진정 국면'],
    'vix_alert':      ['공포 심리 확산', '단기 변동성 경계'],
}


def now_kst():
    return datetime.now(tz=KST)


def pick(key):
    pool = INTERPRET_VARIANTS.get(key, [])
    return random.choice(pool) if pool else ''


def safe_float(v):
    try:
        f = float(v)
        if f != f:
            return None
        return f
    except (TypeError, ValueError):
        return None


def classify_trend(series):
    valid = [v for v in series if v is not None]
    if len(valid) < 2:
        return 'flat'
    base = valid[0]
    if not base:
        return 'flat'
    chg = (valid[-1] - base) / abs(base)
    if chg >= 0.03:
        return 'up'
    if chg <= -0.03:
        return 'down'
    return 'flat'


def fmt_pct(x):
    if x is None:
        return 'N/A'
    return f'{x*100:+.1f}%'


def atomic_write_json(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    json.loads(payload)
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(payload)
    os.replace(tmp, path)


def load_dataset_csv():
    series = defaultdict(list)
    path = ROOT / 'dataset.csv'
    if not path.exists():
        return series
    with open(path, 'r', encoding='utf-8') as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            if len(row) < 4:
                continue
            date, name, val, dtype = row[0], row[1], row[2], row[3]
            v = safe_float(val)
            if v is None:
                continue
            series[(dtype, name)].append((date, v))
    for k in series:
        series[k].sort()
    return series


def get_series(series, dtype, name, days=SPARK_DAYS):
    rows = series.get((dtype, name), [])
    if not rows:
        return None
    tail = rows[-days:]
    return {
        'dates': [r[0] for r in tail],
        'values': [round(r[1], 4) for r in tail],
    }


def safe_load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def load_featured_latest(path):
    rows = safe_load_json(path)
    if not rows or not isinstance(rows, list):
        return None
    latest = max((r.get('d', '') for r in rows), default='')
    if not latest:
        return None
    return [r for r in rows if r.get('d') == latest], latest


def slot(sid, category, tone, text, href, spark_values=None):
    s = {
        'id': sid,
        'category': category,
        'color': CATEGORY_COLORS.get(category, '#666'),
        'tone': tone,
        'text': text,
        'href': href,
    }
    if spark_values and len(spark_values) >= 2:
        s['spark'] = {
            'series': [round(v, 4) for v in spark_values],
            'trend': classify_trend(spark_values),
        }
    else:
        s['spark'] = None
    return s


def b_market_1m_leader(ctx):
    ir = ctx.get('index_returns')
    if not ir:
        return None
    r1m = ir.get('returns_1m', {})
    if not r1m:
        return None
    ranked = sorted(r1m.items(), key=lambda x: x[1], reverse=True)
    top = ranked[0]
    bot = ranked[-1]
    text = f"1M 1위 {top[0]} {fmt_pct(top[1])}, 꼴찌 {bot[0]} {fmt_pct(bot[1])}"
    spark = None
    for dt in ('INDEX_KR', 'INDEX_US', 'INDEX_GLOBAL'):
        srs = get_series(ctx['ds'], dt, top[0])
        if srs:
            spark = srs['values']
            break
    return slot('market-1m-leader', 'Market', 'fact', text, 'market.html', spark)


def b_market_breadth(ctx):
    mr = ctx.get('monthly_returns')
    if not mr or 'rows' not in mr or not mr['rows']:
        return None
    latest = mr['rows'][-1]
    returns = latest.get('returns', {})
    total = len(returns)
    if total == 0:
        return None
    ups = sum(1 for v in returns.values() if v > 0)
    ratio = ups / total
    if ratio >= 0.7:
        phrase = pick('breadth_strong')
    elif ratio <= 0.3:
        phrase = pick('breadth_weak')
    else:
        phrase = pick('breadth_mixed')
    ym = f"{latest.get('year')}-{latest.get('month',0):02d}"
    text = f"{ym} 11개 자산 중 {ups}/{total} 상승 — {phrase}"
    return slot('market-breadth', 'Market', 'interpret', text, 'market.html')


def b_memory_ddr5(ctx):
    srs = get_series(ctx['ds'], 'DRAM', 'DDR5 16G (2Gx8) 4800/5600')
    if not srs or len(srs['values']) < 8:
        return None
    vals = srs['values']
    base = vals[-8]
    if not base:
        return None
    chg = (vals[-1] - base) / base
    if chg >= 0.03:
        phrase = pick('up_strong')
    elif chg >= 0.01:
        phrase = pick('up_mild')
    elif chg <= -0.03:
        phrase = pick('down_strong')
    elif chg <= -0.01:
        phrase = pick('down_mild')
    else:
        phrase = pick('flat')
    text = f"DDR5 7일 {fmt_pct(chg)} (현재 ${vals[-1]:.2f}) — {phrase}"
    return slot('memory-ddr5', 'Memory', 'interpret', text, 'market.html', vals)


def b_crypto_btc(ctx):
    srs = get_series(ctx['ds'], 'CRYPTO', 'BTC')
    if not srs or len(srs['values']) < 22:
        return None
    vals = srs['values']
    chg = (vals[-1] - vals[-22]) / vals[-22] if vals[-22] else 0
    text = f"BTC 1M {fmt_pct(chg)} (현재 ${vals[-1]:,.0f})"
    return slot('crypto-btc', 'Crypto', 'fact', text, 'market.html', vals)


def b_commodity_gold(ctx):
    srs = get_series(ctx['ds'], 'COMMODITY', 'Gold')
    if not srs or len(srs['values']) < 22:
        return None
    vals = srs['values']
    chg = (vals[-1] - vals[-22]) / vals[-22] if vals[-22] else 0
    text = f"Gold 1M {fmt_pct(chg)} (현재 ${vals[-1]:,.0f}/oz)"
    return slot('commodity-gold', 'Commodity', 'fact', text, 'market.html', vals)


def b_fx_usdkrw(ctx):
    srs = get_series(ctx['ds'], 'FX', 'KRW/USD')
    if not srs or len(srs['values']) < 8:
        return None
    vals = srs['values']
    chg = vals[-1] - vals[-8]
    text = f"USD/KRW 1주 {chg:+.1f}원 (현재 {vals[-1]:,.1f}원)"
    return slot('fx-usdkrw', 'FX', 'fact', text, 'market.html', vals)


def b_dxy(ctx):
    srs = get_series(ctx['ds'], 'FX', 'Dollar Index (DXY)')
    if not srs or len(srs['values']) < 8:
        return None
    vals = srs['values']
    chg = (vals[-1] - vals[-8]) / vals[-8] if vals[-8] else 0
    if chg >= 0.01:
        phrase = '달러 강세 — 신흥국 자산 부담'
    elif chg <= -0.01:
        phrase = '달러 약세 — 위험자산 우호'
    else:
        phrase = '달러 횡보'
    text = f"DXY 7일 {fmt_pct(chg)} (현재 {vals[-1]:.2f}) — {phrase}"
    return slot('dxy', 'FX', 'interpret', text, 'market.html', vals)


def b_vix(ctx):
    srs = get_series(ctx['ds'], 'INDEX', 'VIX Index')
    if not srs or not srs['values']:
        return None
    vals = srs['values']
    cur = vals[-1]
    if cur < 15:
        phrase = pick('vix_calm')
    elif cur > 25:
        phrase = pick('vix_alert')
    else:
        phrase = '중립권'
    text = f"VIX {cur:.1f} — {phrase}"
    return slot('vix', 'Market', 'interpret', text, 'market.html', vals)


def b_us10y(ctx):
    srs = get_series(ctx['ds'], 'INTEREST_RATE', 'US 10 Year Treasury Yield')
    if not srs or len(srs['values']) < 8:
        return None
    vals = srs['values']
    chg_bp = (vals[-1] - vals[-8]) * 100
    text = f"US 10Y {vals[-1]:.2f}% (1주 {chg_bp:+.0f}bp)"
    return slot('us-10y', 'Rate', 'fact', text, 'market.html', vals)


def b_battery_lithium(ctx):
    srs = get_series(ctx['ds'], 'BATTERY_METAL', 'Lithium Carbonate')
    if not srs or len(srs['values']) < 8:
        return None
    vals = srs['values']
    if len(vals) >= 22:
        base, label = vals[-22], '1M'
    else:
        base, label = vals[-8], '7일'
    chg = (vals[-1] - base) / base if base else 0
    if chg >= 0.05:
        phrase = pick('up_strong')
    elif chg <= -0.05:
        phrase = pick('down_strong')
    else:
        phrase = pick('flat')
    text = f"리튬카보네이트 {label} {fmt_pct(chg)} — {phrase}"
    return slot('battery-lithium', 'Commodity', 'interpret', text, 'market.html', vals)


def b_smp(ctx):
    srs = get_series(ctx['ds'], 'SMP_KPX', 'SMP')
    if not srs or len(srs['values']) < 8:
        return None
    vals = srs['values']
    chg = (vals[-1] - vals[-8]) / vals[-8] if vals[-8] else 0
    text = f"SMP 7일 {fmt_pct(chg)} (현재 {vals[-1]:.1f}원/kWh)"
    return slot('smp', 'Commodity', 'fact', text, 'market.html', vals)


def b_scfi(ctx):
    srs = get_series(ctx['ds'], 'OCEAN_FREIGHT', 'SCFI Comprehensive Index')
    if not srs or len(srs['values']) < 4:
        return None
    vals = srs['values']
    chg = (vals[-1] - vals[-4]) / vals[-4] if vals[-4] else 0
    text = f"SCFI {vals[-1]:,.0f} (4주 {fmt_pct(chg)})"
    return slot('scfi', 'Commodity', 'fact', text, 'market.html', vals)


def b_index_kospi(ctx):
    srs = get_series(ctx['ds'], 'INDEX_KR', 'KOSPI')
    if not srs or len(srs['values']) < 22:
        return None
    vals = srs['values']
    chg = (vals[-1] - vals[-22]) / vals[-22] if vals[-22] else 0
    text = f"KOSPI 1M {fmt_pct(chg)} (현재 {vals[-1]:,.1f})"
    return slot('index-kospi', 'Index', 'fact', text, 'market.html', vals)


def b_index_nasdaq(ctx):
    srs = get_series(ctx['ds'], 'INDEX_US', 'NASDAQ')
    if not srs or len(srs['values']) < 22:
        return None
    vals = srs['values']
    chg = (vals[-1] - vals[-22]) / vals[-22] if vals[-22] else 0
    text = f"NASDAQ 1M {fmt_pct(chg)} (현재 {vals[-1]:,.0f})"
    return slot('index-nasdaq', 'Index', 'fact', text, 'market.html', vals)


def b_alert_counts(ctx):
    p = ROOT / 'market_alert.html'
    if not p.exists():
        return None
    try:
        html = p.read_text(encoding='utf-8')
    except Exception:
        return None
    counts = {}
    for cat in ('투자위험', '투자경고', '투자주의'):
        m = re.search(
            rf'section-title[^>]*>[^<]*{cat}.*?<tbody[^>]*>(.*?)</tbody>',
            html, re.DOTALL
        )
        if m:
            counts[cat] = len(re.findall(r'<tr[\s>]', m.group(1)))
    if not counts:
        return None
    text = (
        f"오늘 투자주의 {counts.get('투자주의',0)} · "
        f"경고 {counts.get('투자경고',0)} · "
        f"위험 {counts.get('투자위험',0)}"
    )
    return slot('alert-counts', 'Alert', 'fact', text, 'market_alert.html')


def b_etf_sector_top(ctx):
    d = ctx.get('kodex')
    if not d or 'sectors' not in d or not d['sectors']:
        return None
    top = sorted(d['sectors'].items(), key=lambda x: x[1], reverse=True)[0]
    text = f"KOSPI200+KOSDAQ150 섹터 1위: {top[0]} {top[1]:.1f}%"
    return slot('etf-sector-top', 'ETF', 'fact', text, 'etf.html')


def b_wrap_top_weight(ctx):
    d = ctx.get('correlation')
    if not d or 'portfolios' not in d:
        return None
    p = d['portfolios'].get('삼성 트루밸류 / NH Value ESG / DB 개방형')
    if not p or 'stocks' not in p:
        return None
    stocks = sorted(p['stocks'], key=lambda x: x.get('weight', 0), reverse=True)
    if not stocks:
        return None
    top = stocks[0]
    text = f"WRAP 일반형 상위 비중: {top['name']} {top.get('weight',0):.1f}%"
    return slot('wrap-top-weight', 'WRAP', 'fact', text, 'wrap.html')


def b_wrap_stock_count(ctx):
    d = ctx.get('correlation')
    if not d or 'portfolios' not in d:
        return None
    counts = []
    for name, p in d['portfolios'].items():
        sc = p.get('stock_count') or len(p.get('stocks', []))
        if sc:
            counts.append((name, sc))
    if not counts:
        return None
    text = ' · '.join(f'{n.split()[0]}/{n.split()[-1]} {c}종목' if ' / ' not in n else f'{n[:10]}.. {c}종목' for n, c in counts[:2])
    return slot('wrap-stock-count', 'WRAP', 'fact', text, 'wrap.html')


def b_featured_volume_top(ctx):
    fd = ctx.get('featured_latest')
    if not fd:
        return None
    rows, latest_d = fd
    abs_rows = [r for r in rows if r.get('type') == 'absolute']
    if not abs_rows:
        return None
    try:
        abs_rows.sort(key=lambda x: int(x.get('rank', 99)))
    except (ValueError, TypeError):
        return None
    top = abs_rows[0]
    trdval = safe_float(top.get('trdval'))
    if trdval is None:
        return None
    if trdval >= 1e12:
        amt = f"{trdval/1e12:.1f}조"
    else:
        amt = f"{trdval/1e8:,.0f}억"
    text = f"{latest_d} 거래대금 1위: {top.get('name','')} {amt}원"
    return slot('featured-volume-top', 'Featured', 'fact', text, 'featured.html')


def b_featured_chg_top(ctx):
    fd = ctx.get('featured_latest')
    if not fd:
        return None
    rows, latest_d = fd
    chg_rows = []
    for r in rows:
        if r.get('type') not in ('kospi_chg', 'kosdaq_chg'):
            continue
        v = safe_float(r.get('chg'))
        if v is None or not r.get('name'):
            continue
        if abs(v) > 30.5:
            continue
        chg_rows.append((v, r))
    if not chg_rows:
        return None
    chg_rows.sort(key=lambda x: x[0], reverse=True)
    v, top = chg_rows[0]
    market = top.get('market', '')
    text = f"{latest_d} {market} 상승률 1위: {top.get('name','')} {v:+.1f}%"
    return slot('featured-chg-top', 'Featured', 'fact', text, 'featured.html')


BUILDERS = [
    b_market_1m_leader,
    b_market_breadth,
    b_memory_ddr5,
    b_crypto_btc,
    b_commodity_gold,
    b_fx_usdkrw,
    b_dxy,
    b_vix,
    b_us10y,
    b_battery_lithium,
    b_smp,
    b_scfi,
    b_index_kospi,
    b_index_nasdaq,
    b_alert_counts,
    b_etf_sector_top,
    b_wrap_top_weight,
    b_wrap_stock_count,
    b_featured_volume_top,
    b_featured_chg_top,
]


def main():
    print(f"[{now_kst():%Y-%m-%d %H:%M:%S KST}] building landing_highlights.json")
    ds = load_dataset_csv()
    featured_path = ROOT / 'featured_data.json'
    featured_latest = load_featured_latest(featured_path) if featured_path.exists() else None
    ctx = {
        'ds': ds,
        'index_returns': safe_load_json(ROOT / 'index_returns.json'),
        'monthly_returns': safe_load_json(ROOT / 'monthly_returns.json'),
        'correlation': safe_load_json(ROOT / 'correlation_matrix.json'),
        'kodex': safe_load_json(ROOT / 'kodex_sectors.json'),
        'featured_latest': featured_latest,
    }
    print(f"  loaded: ds={len(ds)} series, featured_latest_rows={len(featured_latest[0]) if featured_latest else 0}")

    slots = []
    for b in BUILDERS:
        try:
            s = b(ctx)
            if s:
                slots.append(s)
                preview = s['text'][:60]
                print(f"  + {b.__name__:30s} -> {s['id']:20s} {preview}")
            else:
                print(f"  ~ {b.__name__:30s} skipped (no data)")
        except Exception as e:
            print(f"  ! {b.__name__:30s} error: {e}")

    if not slots:
        print("ERROR: no slots produced", file=sys.stderr)
        sys.exit(1)

    out = {
        'updated_at': now_kst().strftime('%Y-%m-%d %H:%M:%S KST'),
        'slots': slots,
    }
    atomic_write_json(OUTPUT, out)
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"[OK] wrote {OUTPUT.name} ({len(slots)} slots, {size_kb:.1f} KB)")


if __name__ == '__main__':
    main()
