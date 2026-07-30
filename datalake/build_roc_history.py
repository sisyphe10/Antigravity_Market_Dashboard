# -*- coding: utf-8 -*-
"""RoC² 전용 월말 백필 — datalake → roc_history.csv  (2026-07-30)

DATA 탭 RoC² 서브패널(create_dashboard.py `cmbRocCompute`)은 YoY lag 12개월 + MA3 때문에
월 14버킷 이상을 요구한다. 그런데 dataset.csv 의 일별 시장 시리즈는 이력이 12개월뿐이라
KOSPI·S&P500·환율 등 31종이 계산 불가였다(2026-07-29 실측: 120/184종만 가능).

★일별 원계열을 dataset.csv 에 통째로 백필하지 않는 이유
  ① RoC² 는 월 버킷만 쓴다 — 일별은 전량이 낭비다.
  ② dataset.csv 에 월말 과거를 섞으면 메인 차트의 과거 구간이 월별로 끊겨 보인다.
  ③ market.html 은 cmbData 를 인라인 JSON 으로 싣는다 — 일별 25만행은 페이지를 폭발시킨다.
  → 그래서 dataset.csv 는 손대지 않고, RoC² 전용 월말 채널을 따로 만든다.

사용: venv/bin/python3 datalake/build_roc_history.py [--from 1990-01] [--out roc_history.csv]
출력: roc_history.csv  (series,date,value — 각 월의 마지막 관측)
"""
import argparse
import csv
import io
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'execution'))

DUCKDB_PATH = os.path.expanduser('~/datalake/market/market.duckdb')

# dataset.csv 시리즈명 ← global_markets.symbol
# ★티커 정의는 execution/config.py YFINANCE_TICKERS 에서 읽어 온다(단일 출처).
#   아래 EXTRA_YF 는 config 에 없는(= 다른 수집기가 담당하는) 시리즈만 명시.
EXTRA_YF = {
    'S&P 500': '^GSPC',
    'NASDAQ': '^IXIC',          # ★종합(^IXIC) — 100(^NDX) 아님. 실측 24,876.91 일치로 확인
    'RUSSELL 2000': '^RUT',
}

# dataset.csv 시리즈명 ← kr_index_ohlcv.index_code
KRX_INDEX = {
    'KOSPI': '1001',
    'KOSDAQ': '2001',
}

# dataset.csv 시리즈명 ← kr_index_ohlcv.marcap
# ★단위는 '원' 그대로 — dataset.csv 값과 같은 스케일이라 cmbRocCompute 에서 바로 병합된다
#   (표시용 1e12 나눗셈은 create_dashboard.py 의 seriesScale 이 담당. RoC 는 비율이라 무관).
# ★1990년대 초 구간은 marcap 이 0 으로 채워져 있어 반드시 걸러낸다 — 0 을 분모로 쓰면
#   YoY 가 발산하거나 null 이 되어 이력을 늘린 효과가 사라진다.
KRX_MARCAP = {
    'KOSPI Market Cap': '1001',
    'KOSDAQ Market Cap': '2001',
}

# 파생 = 지수 ÷ 환율. market_crawler.py 와 동일 정의(round 4).
DERIVED = {
    'KOSPI/USD': ('KOSPI', 'KRW/USD'),
    'KOSDAQ/USD': ('KOSDAQ', 'KRW/USD'),
}


def yf_map():
    """execution/config.py 의 yfinance 티커 맵 + EXTRA_YF."""
    import config
    m = {name: spec['ticker'] for name, spec in config.YFINANCE_TICKERS.items()}
    m.update(EXTRA_YF)
    return m


def fmt(v):
    """소수 4자리 이하, 불필요한 0 제거."""
    s = f'{v:.4f}'.rstrip('0').rstrip('.')
    return s if s not in ('', '-0') else '0'


def month_end(rows):
    """[(date, value)] → {YYYY-MM: (date, value)} 각 월의 마지막 관측."""
    out = {}
    for d, v in rows:
        if v is None:
            continue
        out[d[:7]] = (d, float(v))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='since', default='1990-01',
                    help="시작 월 (기본 1990-01). 표시 구간은 dataset.csv 가 정하므로 "
                         "그 이전 이력은 RoC² 계산에도 쓰이지 않는다.")
    ap.add_argument('--out', default=os.path.join(ROOT, 'roc_history.csv'))
    ap.add_argument('--dataset', default=os.path.join(ROOT, 'dataset.csv'))
    args = ap.parse_args()

    import duckdb
    con = duckdb.connect(DUCKDB_PATH, read_only=True)

    series = {}   # name -> {month: (date, val)}
    ymap = yf_map()

    # 1) global_markets
    have = {r[0] for r in con.execute('SELECT DISTINCT symbol FROM global_markets').fetchall()}
    missing = []
    for name, sym in sorted(ymap.items()):
        if sym not in have:
            missing.append(f'{name}({sym})')
            continue
        rows = con.execute(
            'SELECT strftime(date, %s), close FROM global_markets '
            'WHERE symbol = ? AND close IS NOT NULL ORDER BY date' % "'%Y-%m-%d'",
            [sym]).fetchall()
        series[name] = month_end(rows)

    # 2) kr_index_ohlcv
    for name, code in KRX_INDEX.items():
        rows = con.execute(
            "SELECT strftime(date, '%Y-%m-%d'), close FROM kr_index_ohlcv "
            "WHERE index_code = ? AND close IS NOT NULL ORDER BY date",
            [code]).fetchall()
        series[name] = month_end(rows)

    # 2-b) kr_index_ohlcv.marcap (시가총액)
    for name, code in KRX_MARCAP.items():
        rows = con.execute(
            "SELECT strftime(date, '%Y-%m-%d'), marcap FROM kr_index_ohlcv "
            "WHERE index_code = ? AND marcap IS NOT NULL AND marcap > 0 ORDER BY date",
            [code]).fetchall()
        series[name] = month_end(rows)

    # 3) 파생 (지수 ÷ 환율) — 같은 월 버킷끼리만
    for name, (num, den) in DERIVED.items():
        a, b = series.get(num, {}), series.get(den, {})
        out = {}
        for m in a:
            if m in b and b[m][1]:
                out[m] = (a[m][0], round(a[m][1] / b[m][1], 4))
        series[name] = out

    # 4) dataset.csv 의 시리즈별 최초/최종 월 — 겹치는 달로 정의 일치를 검증한다.
    ds = defaultdict(dict)
    with io.open(args.dataset, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            nm, d, v = (row.get('제품명') or '').strip(), (row.get('날짜') or '').strip(), (row.get('가격') or '').strip()
            if nm in series and d and v:
                try:
                    ds[nm][d[:7]] = float(v)
                except ValueError:
                    pass

    # ★검증은 '완결된' 겹침 월로만 한다. 당월은 dataset.csv 와 datalake 의 스냅숏
    #   시각이 달라(장중/마감·거래일 차이) 원자재·크립토·VIX 가 1~2% 어긋나는데,
    #   이건 정의 불일치가 아니라 시점 차이다. 게다가 JS 는 겹치는 달을 전부
    #   dataset.csv 우선으로 버리므로 실사용에 영향도 없다.
    cur_month = max(max(v) for v in ds.values() if v)
    print("=== 정의 검증 (완결 겹침 월 전체, 당월 %s 제외) ===" % cur_month)
    print(f"{'시리즈':<28}{'겹침월':>6}{'최대괴리%':>11}{'발생월':>10}{'중위괴리%':>11}")
    warn = []
    for name in sorted(series):
        common = sorted(m for m in (set(series[name]) & set(ds.get(name, {}))) if m < cur_month)
        if not common:
            warn.append(f'{name}: 완결 겹침 월 없음 (검증 불가)')
            print(f'{name:<28}{0:>6}{"-":>11}{"-":>10}{"-":>11}')
            continue
        diffs = []
        for m in common:
            dv, lv = ds[name][m], series[name][m][1]
            diffs.append(((lv / dv - 1) * 100 if dv else float('inf'), m))
        worst = max(diffs, key=lambda x: abs(x[0]))
        med = sorted(abs(d) for d, _ in diffs)[len(diffs) // 2]
        flag = '  <== 확인필요' if abs(worst[0]) > 0.5 else ''
        print(f'{name:<28}{len(common):>6}{worst[0]:>11.3f}{worst[1]:>10}{med:>11.3f}{flag}')
        if abs(worst[0]) > 0.5:
            warn.append(f'{name}: {worst[1]} 괴리 {worst[0]:+.2f}% (중위 {med:.2f}%)')

    # 5) 기록 — dataset.csv 최초 월 '이전'만 실제로 쓰이지만, 검증·재현을 위해
    #    --from 이후 전 구간을 남긴다(JS 가 겹치는 달은 dataset.csv 우선으로 버린다).
    n = 0
    tmp = args.out + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['series', 'date', 'value'])
        for name in sorted(series):
            for m in sorted(series[name]):
                if m < args.since:
                    continue
                d, v = series[name][m]
                w.writerow([name, d, fmt(v)])
                n += 1
    os.replace(tmp, args.out)

    print()
    print(f'시리즈 {len(series)}종 / 행 {n:,} → {args.out} ({os.path.getsize(args.out):,} bytes)')
    if missing:
        print('★ datalake 미수집: ' + ', '.join(missing))
    if warn:
        print('★ 경고:')
        for x in warn:
            print('   - ' + x)
    return 1 if missing else 0


if __name__ == '__main__':
    sys.exit(main())
