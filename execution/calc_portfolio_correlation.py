"""
포트폴리오 종목 간 30거래일 상관계수 매트릭스 + 위험 클러스터 탐지.

입력
----
- portfolio_data.json : 포트폴리오별 보유 종목 (code, weight)
- stock_price_history.json : 종목별 일별 종가 (VM 로컬, ~370일 보관)

출력
----
- correlation_matrix.json : 포트폴리오별 매트릭스 + 위험 페어/클러스터

임계값 (포트폴리오별 독립 평가)
----
- 페어 상관 0.70+  → "주의"
- 페어 상관 0.85+  → "경고"
- 클러스터 (페어 0.7+ 연결) 비중 합 30%+ → 알람 대상

실행 위치: VM (stock_price_history.json이 VM에만 fresh)
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

PORTFOLIO_FILE = 'portfolio_data.json'
PRICE_HISTORY_FILE = 'stock_price_history.json'
OUTPUT_FILE = 'correlation_matrix.json'

WINDOW_DAYS = 30
PAIR_WATCH = 0.70
PAIR_ALERT = 0.85
CLUSTER_WEIGHT_PCT = 30.0

KST = timezone(timedelta(hours=9))


def load_price_history():
    with open(PRICE_HISTORY_FILE, 'r', encoding='utf-8') as f:
        h = json.load(f)
    dates = sorted(h['dates'])
    return dates, h['stocks']


def build_returns_matrix(stocks_data, dates, codes):
    """주어진 종목 코드의 최근 WINDOW_DAYS+1 거래일 종가 → 일간 수익률 DataFrame."""
    window_dates = dates[-(WINDOW_DAYS + 1):]
    if len(window_dates) < WINDOW_DAYS + 1:
        logging.warning(f"가용 거래일 부족: {len(window_dates)} < {WINDOW_DAYS + 1}")

    closes = {}
    missing = []
    for code in codes:
        if code not in stocks_data:
            missing.append(code)
            continue
        c = stocks_data[code].get('closes', {})
        series = [c.get(d) for d in window_dates]
        if sum(1 for v in series if v) < WINDOW_DAYS * 0.8:
            missing.append(code)
            continue
        closes[code] = series

    if missing:
        logging.warning(f"데이터 부족으로 제외: {missing}")

    df = pd.DataFrame(closes, index=window_dates).astype(float)
    returns = df.pct_change().dropna(how='all')
    return returns, missing


def find_clusters(corr_df, threshold, holdings):
    """페어 상관이 threshold 이상인 종목들을 연결 그래프 connected components로 묶음."""
    codes = list(corr_df.index)
    parent = {c: c for c in codes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i, a in enumerate(codes):
        for b in codes[i + 1:]:
            if corr_df.at[a, b] >= threshold:
                union(a, b)

    clusters = {}
    for c in codes:
        r = find(c)
        clusters.setdefault(r, []).append(c)

    weight_map = {h['code']: h['weight'] for h in holdings}
    name_map = {h['code']: h['name'] for h in holdings}

    result = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        wsum = sum(weight_map.get(c, 0) for c in members)
        # 평균 페어 상관 (구성원 모든 페어)
        pair_corrs = []
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                pair_corrs.append(float(corr_df.at[a, b]))
        result.append({
            'members': [{'code': c, 'name': name_map.get(c, ''), 'weight': weight_map.get(c, 0)} for c in members],
            'weight_sum': round(wsum, 2),
            'avg_corr': round(np.mean(pair_corrs), 4) if pair_corrs else 0.0,
            'is_concentration_risk': wsum >= CLUSTER_WEIGHT_PCT,
        })
    result.sort(key=lambda x: x['weight_sum'], reverse=True)
    return result


def analyze_portfolio(name, holdings, stocks_data, dates):
    codes = [h['code'] for h in holdings if h.get('code')]
    name_map = {h['code']: h['name'] for h in holdings}
    weight_map = {h['code']: h['weight'] for h in holdings}

    returns, missing = build_returns_matrix(stocks_data, dates, codes)
    if returns.empty or returns.shape[1] < 2:
        logging.warning(f"[{name}] 분석 불가 (유효 종목 {returns.shape[1] if not returns.empty else 0}개)")
        return None

    corr = returns.corr()

    # 페어 경고/주의 추출 (자기상관 제외, 중복 제외)
    pairs = []
    valid_codes = list(corr.index)
    for i, a in enumerate(valid_codes):
        for b in valid_codes[i + 1:]:
            c = corr.at[a, b]
            if pd.isna(c) or c < PAIR_WATCH:
                continue
            level = '경고' if c >= PAIR_ALERT else '주의'
            pairs.append({
                'a': a, 'a_name': name_map.get(a, ''), 'a_weight': weight_map.get(a, 0),
                'b': b, 'b_name': name_map.get(b, ''), 'b_weight': weight_map.get(b, 0),
                'corr': round(float(c), 4),
                'level': level,
            })
    pairs.sort(key=lambda x: x['corr'], reverse=True)

    clusters = find_clusters(corr, PAIR_WATCH, holdings)

    return {
        'window_days': WINDOW_DAYS,
        'date_range': [returns.index[0], returns.index[-1]],
        'stock_count': len(valid_codes),
        'missing_codes': missing,
        'stocks': [
            {'code': c, 'name': name_map.get(c, ''), 'weight': weight_map.get(c, 0)}
            for c in valid_codes
        ],
        'matrix': corr.round(4).fillna(0).values.tolist(),
        'codes_order': valid_codes,
        'pairs': pairs,
        'clusters': clusters,
        'summary': {
            'pair_watch_count': sum(1 for p in pairs if p['level'] == '주의'),
            'pair_alert_count': sum(1 for p in pairs if p['level'] == '경고'),
            'concentration_clusters': sum(1 for c in clusters if c['is_concentration_risk']),
        },
    }


def main():
    if not os.path.exists(PORTFOLIO_FILE):
        logging.error(f"{PORTFOLIO_FILE} 없음")
        sys.exit(1)
    if not os.path.exists(PRICE_HISTORY_FILE):
        logging.error(f"{PRICE_HISTORY_FILE} 없음")
        sys.exit(1)

    with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f:
        portfolios = json.load(f)

    dates, stocks_data = load_price_history()
    logging.info(f"가격 데이터: {len(dates)}일 ({dates[0]} ~ {dates[-1]}), {len(stocks_data)}종목")

    output = {
        'updated': datetime.now(tz=KST).isoformat(timespec='seconds'),
        'window_days': WINDOW_DAYS,
        'thresholds': {
            'pair_watch': PAIR_WATCH,
            'pair_alert': PAIR_ALERT,
            'cluster_weight_pct': CLUSTER_WEIGHT_PCT,
        },
        'portfolios': {},
    }

    for name, holdings in portfolios.items():
        if not isinstance(holdings, list) or not holdings:
            continue
        logging.info(f"분석: [{name}] {len(holdings)}종목")
        result = analyze_portfolio(name, holdings, stocks_data, dates)
        if result:
            output['portfolios'][name] = result
            s = result['summary']
            logging.info(
                f"  → 페어 주의 {s['pair_watch_count']}, 경고 {s['pair_alert_count']}, "
                f"집중 클러스터 {s['concentration_clusters']}"
            )

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logging.info(f"완료: {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
