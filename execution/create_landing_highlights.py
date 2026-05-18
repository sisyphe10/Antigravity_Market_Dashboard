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
    'Sector':    '#2d7a3a',
    'Liquidity': '#2d7a3a',
    'Alert':     '#c2410c',
    'Universe':  '#6B21A8',
    'SEIBro':    '#0369a1',
    'Featured':  '#d97706',
}

SPARK_DAYS = 90

WEEKDAY_KR = ['월', '화', '수', '목', '금', '토', '일']


def fmt_short_date(date_str):
    """'YYYY-MM-DD' → 'M.D(요일)'. 파싱 실패 시 원본 반환."""
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return f"{dt.month}.{dt.day}({WEEKDAY_KR[dt.weekday()]})"
    except (ValueError, TypeError):
        return date_str

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


def classify_trend(series, base_idx=8):
    """series 변화율 ±3% 기준으로 up/down/flat 분류.
    base_idx: vals[-base_idx]를 기준값으로 사용. 기본 8 = vals[-8] = 7일 전.
    빌더의 본문 분석 기간(1M=22, 7일=8)과 일치시켜야 텍스트와 색이 어긋나지 않음.
    """
    valid = [v for v in series if v is not None]
    if len(valid) < 2:
        return 'flat'
    base = valid[-base_idx] if len(valid) >= base_idx else valid[0]
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


def fmt_price_dynamic(v, threshold=50):
    """$threshold 미만이면 소수 1자리, 이상이면 정수(천단위)."""
    if v is None:
        return 'N/A'
    if abs(v) < threshold:
        return f"{v:.1f}"
    return f"{v:,.0f}"


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


def slot(sid, category, tone, text, href, spark_values=None, trend_idx=8):
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
            'trend': classify_trend(spark_values, base_idx=trend_idx),
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
    return slot('market-1m-leader', 'Market', 'fact', text, 'market.html', spark, trend_idx=22)


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
    text = f"DDR5 1W {fmt_pct(chg)} (${vals[-1]:,.0f}) — {phrase}"
    return slot('memory-ddr5', 'Memory', 'interpret', text, 'market.html', vals)


def b_crypto_btc(ctx):
    srs = get_series(ctx['ds'], 'CRYPTO', 'BTC')
    if not srs or len(srs['values']) < 22:
        return None
    vals = srs['values']
    base = vals[-22]
    if not base:
        return None
    chg = (vals[-1] - base) / base
    text = f"BTC 1M {fmt_pct(chg)} (${vals[-1]:,.0f})"
    return slot('crypto-btc', 'Crypto', 'fact', text, 'market.html', vals, trend_idx=22)


def b_commodity_gold(ctx):
    srs = get_series(ctx['ds'], 'COMMODITY', 'Gold')
    if not srs or len(srs['values']) < 22:
        return None
    vals = srs['values']
    chg = (vals[-1] - vals[-22]) / vals[-22] if vals[-22] else 0
    text = f"Gold 1M {fmt_pct(chg)} (${vals[-1]:,.0f}/oz)"
    return slot('commodity-gold', 'Commodity', 'fact', text, 'market.html', vals)


def b_fx_usdkrw(ctx):
    srs = get_series(ctx['ds'], 'FX', 'KRW/USD')
    if not srs or len(srs['values']) < 8:
        return None
    vals = srs['values']
    chg = vals[-1] - vals[-8]
    text = f"USD/KRW 1W {chg:+.1f}원 ({vals[-1]:,.0f}원)"
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
    text = f"DXY 1W {fmt_pct(chg)} ({vals[-1]:,.0f}) — {phrase}"
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
    text = f"US 10Y 1W {chg_bp:+.0f}bp ({vals[-1]:.1f}%)"
    return slot('us-10y', 'Rate', 'fact', text, 'market.html', vals)


def b_battery_lithium(ctx):
    srs = get_series(ctx['ds'], 'BATTERY_METAL', 'Lithium Carbonate')
    if not srs or len(srs['values']) < 8:
        return None
    vals = srs['values']
    if len(vals) >= 22:
        base, label, tidx = vals[-22], '1M', 22
    else:
        base, label, tidx = vals[-8], '1W', 8
    if not base:
        return None
    chg = (vals[-1] - base) / base
    if chg >= 0.05:
        phrase = pick('up_strong')
    elif chg <= -0.05:
        phrase = pick('down_strong')
    else:
        phrase = pick('flat')
    text = f"리튬카보네이트 {label} {fmt_pct(chg)} — {phrase}"
    return slot('battery-lithium', 'Commodity', 'interpret', text, 'market.html', vals, trend_idx=tidx)


def b_smp(ctx):
    srs = get_series(ctx['ds'], 'SMP_KPX', 'SMP')
    if not srs or len(srs['values']) < 8:
        return None
    vals = srs['values']
    chg = (vals[-1] - vals[-8]) / vals[-8] if vals[-8] else 0
    text = f"SMP 1W {fmt_pct(chg)} ({vals[-1]:,.0f}원/kWh)"
    return slot('smp', 'Commodity', 'fact', text, 'market.html', vals)


def b_scfi(ctx):
    srs = get_series(ctx['ds'], 'OCEAN_FREIGHT', 'SCFI Comprehensive Index')
    if not srs or len(srs['values']) < 4:
        return None
    vals = srs['values']
    base = vals[-4]
    if not base:
        return None
    chg = (vals[-1] - base) / base
    text = f"SCFI 1M {fmt_pct(chg)} ({vals[-1]:,.0f})"
    return slot('scfi', 'Commodity', 'fact', text, 'market.html', vals, trend_idx=4)


def b_index_kospi(ctx):
    srs = get_series(ctx['ds'], 'INDEX_KR', 'KOSPI')
    if not srs or len(srs['values']) < 22:
        return None
    vals = srs['values']
    base = vals[-22]
    if not base:
        return None
    chg = (vals[-1] - base) / base
    text = f"KOSPI 1M {fmt_pct(chg)} ({vals[-1]:,.0f})"
    return slot('index-kospi', 'Index', 'fact', text, 'market.html', vals, trend_idx=22)


def b_index_nasdaq(ctx):
    srs = get_series(ctx['ds'], 'INDEX_US', 'NASDAQ')
    if not srs or len(srs['values']) < 22:
        return None
    vals = srs['values']
    base = vals[-22]
    if not base:
        return None
    chg = (vals[-1] - base) / base
    text = f"NASDAQ 1M {fmt_pct(chg)} ({vals[-1]:,.0f})"
    return slot('index-nasdaq', 'Index', 'fact', text, 'market.html', vals, trend_idx=22)


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
    text = f"{fmt_short_date(latest_d)} 거래대금 1위: {top.get('name','')} {amt}원"
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
    text = f"{fmt_short_date(latest_d)} {market} 상승률 1위: {top.get('name','')} {v:+.1f}%"
    return slot('featured-chg-top', 'Featured', 'fact', text, 'featured.html')


def _generic_1m(ctx, dtype, name, label, sid, category, href='market.html', unit='', fmt='comma'):
    srs = get_series(ctx['ds'], dtype, name)
    if not srs or len(srs['values']) < 22:
        return None
    vals = srs['values']
    base = vals[-22]
    if not base:
        return None
    chg = (vals[-1] - base) / base
    if fmt == 'price4':
        cur = f"{vals[-1]:.4f}"
    elif fmt == 'dynamic':
        cur = fmt_price_dynamic(vals[-1])
    else:
        cur = f"{vals[-1]:,.0f}"
    text = f"{label} 1M {fmt_pct(chg)} ({unit}{cur})"
    return slot(sid, category, 'fact', text, href, vals, trend_idx=22)


def _generic_7d(ctx, dtype, name, label, sid, category, href='market.html', unit='', fmt='price2'):
    srs = get_series(ctx['ds'], dtype, name)
    if not srs or len(srs['values']) < 8:
        return None
    vals = srs['values']
    base = vals[-8]
    if not base:
        return None
    chg = (vals[-1] - base) / base
    if fmt == 'price4':
        cur = f"{vals[-1]:.4f}"
    elif fmt == 'dynamic':
        cur = fmt_price_dynamic(vals[-1])
    else:
        cur = f"{vals[-1]:,.0f}"
    text = f"{label} 1W {fmt_pct(chg)} ({unit}{cur})"
    return slot(sid, category, 'fact', text, href, vals)


def b_index_kosdaq(ctx):
    return _generic_1m(ctx, 'INDEX_KR', 'KOSDAQ', 'KOSDAQ', 'index-kosdaq', 'Index', fmt='price1')


def b_index_sp500(ctx):
    return _generic_1m(ctx, 'INDEX_US', 'S&P 500', 'S&P 500', 'index-sp500', 'Index', fmt='comma')


def b_index_nikkei(ctx):
    return _generic_1m(ctx, 'INDEX_GLOBAL', 'NIKKEI', 'NIKKEI', 'index-nikkei', 'Index', fmt='comma')


def b_index_russell(ctx):
    return _generic_1m(ctx, 'INDEX_US', 'RUSSELL 2000', 'RUSSELL 2000', 'index-russell', 'Index', fmt='comma')


def b_index_tsec(ctx):
    return _generic_1m(ctx, 'INDEX_GLOBAL', 'TSEC', '대만 가권', 'index-tsec', 'Index', fmt='comma')


def b_valuation_sp500_per(ctx):
    srs = get_series(ctx['ds'], 'INDEX_US', 'S&P 500 PER')
    if not srs or len(srs['values']) < 22:
        return None
    vals = srs['values']
    diff = vals[-1] - vals[-22]
    if vals[-1] >= 25:
        phrase = '역사적 고밸류 영역'
    elif vals[-1] >= 20:
        phrase = '평균 이상'
    elif vals[-1] <= 15:
        phrase = '저평가권'
    else:
        phrase = '중립권'
    text = f"S&P500 PER 1M {diff:+.1f}p ({vals[-1]:,.0f}배) — {phrase}"
    return slot('val-sp500-per', 'Index', 'interpret', text, 'market.html', vals, trend_idx=22)


def b_valuation_russell_per(ctx):
    srs = get_series(ctx['ds'], 'INDEX_US', 'RUSSELL 2000 PER')
    if not srs or len(srs['values']) < 22:
        return None
    vals = srs['values']
    diff = vals[-1] - vals[-22]
    text = f"RUSSELL 2000 PER 1M {diff:+.1f}p ({vals[-1]:,.0f}배) — 소형주 밸류"
    return slot('val-russell-per', 'Index', 'interpret', text, 'market.html', vals, trend_idx=22)


def b_commodity_wti(ctx):
    return _generic_1m(ctx, 'COMMODITY', 'WTI Crude Oil', 'WTI 유가', 'commodity-wti', 'Commodity', unit='$', fmt='dynamic')


def b_commodity_copper(ctx):
    return _generic_1m(ctx, 'COMMODITY', 'Copper', '구리', 'commodity-copper', 'Commodity', unit='$', fmt='dynamic')


def b_commodity_silver(ctx):
    return _generic_1m(ctx, 'COMMODITY', 'Silver', '은', 'commodity-silver', 'Commodity', unit='$', fmt='dynamic')


def b_commodity_natgas(ctx):
    return _generic_7d(ctx, 'COMMODITY', 'Natural Gas', '천연가스', 'commodity-natgas', 'Commodity', unit='$', fmt='dynamic')


def b_commodity_uranium(ctx):
    srs = get_series(ctx['ds'], 'COMMODITY', 'Uranium')
    if not srs or len(srs['values']) < 8:
        return None
    vals = srs['values']
    if len(vals) >= 22:
        base, label, tidx = vals[-22], '1M', 22
    else:
        base, label, tidx = vals[-8], '1W', 8
    if not base:
        return None
    chg = (vals[-1] - base) / base
    text = f"우라늄 {label} {fmt_pct(chg)} (${fmt_price_dynamic(vals[-1])}) — 원전 테마"
    return slot('commodity-uranium', 'Commodity', 'interpret', text, 'market.html', vals, trend_idx=tidx)


def b_memory_ddr4(ctx):
    srs = get_series(ctx['ds'], 'DRAM', 'DDR4 8Gb (1Gx8) 3200')
    if not srs or len(srs['values']) < 8:
        return None
    vals = srs['values']
    chg = (vals[-1] - vals[-8]) / vals[-8] if vals[-8] else 0
    text = f"DDR4 1W {fmt_pct(chg)} (${vals[-1]:,.0f})"
    return slot('memory-ddr4', 'Memory', 'fact', text, 'market.html', vals)


def b_memory_nand(ctx):
    srs = get_series(ctx['ds'], 'NAND', 'MLC 64Gb 8GBx8')
    if not srs or len(srs['values']) < 8:
        return None
    vals = srs['values']
    base = vals[-8]
    if not base:
        return None
    chg = (vals[-1] - base) / base
    text = f"NAND MLC 64Gb 1W {fmt_pct(chg)} (${vals[-1]:,.0f})"
    return slot('memory-nand', 'Memory', 'fact', text, 'market.html', vals)


def b_fx_eurusd(ctx):
    return _generic_7d(ctx, 'FX', 'EUR/USD', 'USD/EUR', 'fx-eurusd', 'FX', fmt='price4')


def b_fx_jpyusd(ctx):
    srs = get_series(ctx['ds'], 'FX', 'JPY/USD')
    if not srs or len(srs['values']) < 8:
        return None
    vals = srs['values']
    base = vals[-8]
    if not base:
        return None
    chg = (vals[-1] - base) / base
    text = f"USD/JPY 1W {fmt_pct(chg)} ({vals[-1]:,.0f}엔)"
    return slot('fx-jpyusd', 'FX', 'fact', text, 'market.html', vals)


def b_fx_cnyusd(ctx):
    srs = get_series(ctx['ds'], 'FX', 'CNY/USD')
    if not srs or len(srs['values']) < 8:
        return None
    vals = srs['values']
    base = vals[-8]
    if not base:
        return None
    chg = (vals[-1] - base) / base
    text = f"USD/CNY 1W {fmt_pct(chg)} ({vals[-1]:.4f}위안)"
    return slot('fx-cnyusd', 'FX', 'fact', text, 'market.html', vals)


def b_rate_us13w(ctx):
    srs = get_series(ctx['ds'], 'INTEREST_RATE', 'US 13 Week Treasury Yield')
    if not srs or len(srs['values']) < 8:
        return None
    vals = srs['values']
    chg_bp = (vals[-1] - vals[-8]) * 100
    text = f"US 13W 1W {chg_bp:+.0f}bp ({vals[-1]:.1f}%) — 단기금리"
    return slot('rate-us13w', 'Rate', 'fact', text, 'market.html', vals)


def b_crypto_eth(ctx):
    srs = get_series(ctx['ds'], 'CRYPTO', 'ETH')
    if not srs or len(srs['values']) < 22:
        return None
    vals = srs['values']
    base = vals[-22]
    if not base:
        return None
    chg = (vals[-1] - base) / base
    text = f"ETH 1M {fmt_pct(chg)} (${vals[-1]:,.0f})"
    return slot('crypto-eth', 'Crypto', 'fact', text, 'market.html', vals, trend_idx=22)


def b_crypto_sol(ctx):
    srs = get_series(ctx['ds'], 'CRYPTO', 'SOL')
    if not srs or len(srs['values']) < 22:
        return None
    vals = srs['values']
    base = vals[-22]
    if not base:
        return None
    chg = (vals[-1] - base) / base
    text = f"SOL 1M {fmt_pct(chg)} (${vals[-1]:,.0f})"
    return slot('crypto-sol', 'Crypto', 'fact', text, 'market.html', vals, trend_idx=22)


def b_kodex_sector_leader(ctx):
    ks = safe_load_json(ROOT / 'kodex_sectors.json')
    if not ks:
        return None
    r = ks.get('sector_1m_returns')
    if not isinstance(r, dict) or not r:
        return None
    items = sorted(
        ((n, v) for n, v in r.items() if isinstance(v, (int, float))),
        key=lambda x: x[1], reverse=True,
    )
    if len(items) < 2:
        return None
    top_n, top_v = items[0]
    bot_n, bot_v = items[-1]
    text = f"KODEX 1M 최강 {top_n} {top_v:+.1f}% · 최약 {bot_n} {bot_v:+.1f}%"
    return slot('kodex-sector-leader', 'Sector', 'fact', text, 'market.html')


def b_seibro_top_settlement(ctx):
    candidates = []
    for (dtype, name), pairs in ctx['ds'].items():
        if dtype != 'SEIBro' or not pairs:
            continue
        d, v = pairs[-1]
        if v is None:
            continue
        candidates.append((d, name, v))
    if not candidates:
        return None
    latest = max(d for d, _, _ in candidates)
    today = [c for c in candidates if c[0] == latest]
    if not today:
        return None
    _, top_n, top_v = max(today, key=lambda x: x[2])
    if top_v >= 1e8:
        amt = f"{top_v/1e8:.1f}억$"
    elif top_v >= 1e6:
        amt = f"{top_v/1e6:.1f}백만$"
    else:
        amt = f"{top_v:,.0f}$"
    tickers = ctx.get('seibro_tickers') or {}
    ticker = tickers.get(top_n)
    display = ticker if ticker else (top_n if len(top_n) <= 30 else top_n[:28] + '…')
    text = f"SEIBro {fmt_short_date(latest)} 결제 1위 {display} {amt}"
    return slot('seibro-top-settlement', 'SEIBro', 'fact', text, 'seibro.html')


def b_deposit_customer(ctx):
    srs = get_series(ctx['ds'], 'DEPOSIT', '고객예탁금')
    if not srs or len(srs['values']) < 22:
        return None
    vals = srs['values']
    base = vals[-22]
    if not base:
        return None
    chg = (vals[-1] - base) / base
    trillion = vals[-1] / 10000.0
    text = f"고객예탁금 1M {fmt_pct(chg)} ({trillion:,.0f}조원)"
    return slot('deposit-customer', 'Liquidity', 'fact', text, 'market.html', vals, trend_idx=22)


BUILDERS = [
    b_market_1m_leader,
    b_market_breadth,
    b_memory_ddr5,
    b_memory_ddr4,
    b_memory_nand,
    b_crypto_btc,
    b_crypto_eth,
    b_crypto_sol,
    b_commodity_gold,
    b_commodity_wti,
    b_commodity_copper,
    b_commodity_silver,
    b_commodity_natgas,
    b_commodity_uranium,
    b_fx_usdkrw,
    b_fx_eurusd,
    b_fx_jpyusd,
    b_fx_cnyusd,
    b_dxy,
    b_vix,
    b_us10y,
    b_rate_us13w,
    b_battery_lithium,
    b_smp,
    b_scfi,
    b_index_kospi,
    b_index_kosdaq,
    b_index_nasdaq,
    b_index_sp500,
    b_index_nikkei,
    b_index_russell,
    b_index_tsec,
    b_valuation_sp500_per,
    b_valuation_russell_per,
    b_alert_counts,
    b_featured_volume_top,
    b_featured_chg_top,
    b_kodex_sector_leader,
    b_seibro_top_settlement,
    b_deposit_customer,
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
        'seibro_tickers': safe_load_json(ROOT / 'seibro_tickers.json') or {},
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
