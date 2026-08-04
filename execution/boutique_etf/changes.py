# -*- coding: utf-8 -*-
"""편입/편출/급변 탐지 + 실매매 추정액 — 기존 active_etf_changes 규칙 승계.

- 편입: prev 없음 & 당일 비중 ≥ 0.5%
- 편출: 당일 없음 & 직전 비중 ≥ 0.5% (KIS 30종목 잘림 ETF 는 편출 판정 억제)
- 급변: |Δ비중| ≥ 1.0%p
- 드리프트: |Δqty_cu|/qty_cu ≤ 0.5% → 실매매 0 처리 (주가만 움직인 경우)
- 실매매 추정액 = invest_t − invest_p × (px_t/px_p)  (가격효과 제거)
- 양일 모두 status='ok' 인 ETF 만 비교 (수집갭 '전부 신규' 오탐 방지)
"""
TH_IN = 0.5
TH_OUT = 0.5
TH_SPIKE = 1.0
DRIFT_REL = 0.005


def _prev_ok(conn, etf_code, date):
    """직전 정상 수집일과 그날의 잘림 여부·출처. (date, truncated, source)"""
    r = conn.execute(
        "SELECT date, truncated, source FROM collection_log WHERE etf_code=? AND date<? "
        "AND status='ok' ORDER BY date DESC LIMIT 1", (etf_code, date)).fetchone()
    return (r['date'], bool(r['truncated']), r['source']) if r else (None, False, None)


def compute_changes(conn, date):
    conn.execute('DELETE FROM etf_changes WHERE date=?', (date,))
    oks = conn.execute(
        "SELECT etf_code, truncated, source FROM collection_log WHERE date=? AND status='ok'",
        (date,)).fetchall()
    for ok in oks:
        etf = ok['etf_code']
        prev_d, prev_trunc, prev_src = _prev_ok(conn, etf, date)
        if not prev_d:
            continue
        # 잘린 스냅숏(KIS 폴백 상위30)과의 비교는 한쪽 방향만 신뢰할 수 있다.
        #   전일이 잘렸으면 → 오늘 새로 보이는 종목은 '원래 있었는데 안 보였을' 뿐 → 편입 억제
        #   오늘이 잘렸으면  → 오늘 안 보이는 종목은 '30위 밖으로 밀린' 것일 뿐 → 편출 억제
        allow_in = not prev_trunc
        allow_out = not ok['truncated']
        # ★출처가 바뀐 날은 보유목록 자체의 범위·표기가 달라 편입·편출을 신뢰할 수 없다
        #   (예: KIS 폴백 → 운용사 PDF 복구). 양일 공통 종목의 급변만 남긴다.
        if prev_src and ok['source'] and prev_src != ok['source']:
            allow_in = allow_out = False
        cur = {r['stock_code']: r for r in conn.execute(
            'SELECT * FROM etf_constituents WHERE date=? AND etf_code=?', (date, etf))
            if r['stock_code']}
        prv = {r['stock_code']: r for r in conn.execute(
            'SELECT * FROM etf_constituents WHERE date=? AND etf_code=?', (prev_d, etf))
            if r['stock_code']}
        ch_rows = []
        for c, r in cur.items():
            trade, drift = None, 0
            if c not in prv:
                if allow_in and (r['weight'] or 0) >= TH_IN:
                    ch_rows.append((date, etf, c, 'in', r['stock_name'],
                                    None, r['weight'], r['invest_amt'], 0))
                trade = r['invest_amt']
            else:
                p = prv[c]
                if r['qty_cu'] and p['qty_cu']:
                    rel = abs(r['qty_cu'] - p['qty_cu']) / p['qty_cu']
                    if rel <= DRIFT_REL:
                        trade, drift = 0.0, 1
                if trade is None:
                    px_t = (r['eval_cu'] / r['qty_cu']) if (r['eval_cu'] and r['qty_cu']) else None
                    px_p = (p['eval_cu'] / p['qty_cu']) if (p['eval_cu'] and p['qty_cu']) else None
                    if r['invest_amt'] is not None and p['invest_amt'] is not None and px_t and px_p:
                        trade = r['invest_amt'] - p['invest_amt'] * (px_t / px_p)
                    elif r['invest_amt'] is not None and p['invest_amt'] is not None:
                        trade = r['invest_amt'] - p['invest_amt']
                dw = (r['weight'] or 0) - (p['weight'] or 0)
                if abs(dw) >= TH_SPIKE and not drift:
                    ch_rows.append((date, etf, c, 'spike', r['stock_name'],
                                    p['weight'], r['weight'], trade, drift))
            conn.execute(
                'UPDATE etf_constituents SET trade_amt=?, drift=? WHERE date=? AND etf_code=? AND stock_code=?',
                (trade, drift, date, etf, c))
        if allow_out:
            for c, p in prv.items():
                if c not in cur and (p['weight'] or 0) >= TH_OUT:
                    ch_rows.append((date, etf, c, 'out', p['stock_name'],
                                    p['weight'], None,
                                    -(p['invest_amt'] or 0) if p['invest_amt'] is not None else None, 0))
        if ch_rows:
            conn.executemany(
                'INSERT OR REPLACE INTO etf_changes '
                '(date,etf_code,stock_code,kind,stock_name,w_prev,w_cur,trade_amt,drift) '
                'VALUES (?,?,?,?,?,?,?,?,?)', ch_rows)
    conn.commit()
