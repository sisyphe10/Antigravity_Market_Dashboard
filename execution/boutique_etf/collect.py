# -*- coding: utf-8 -*-
"""부티크 액티브 ETF 일일 수집 오케스트레이터.

흐름: 레지스트리 갱신 → ETF별 구성종목(어댑터, 실패 시 KIS 폴백) + KIS 시세(NAV·AUM)
      → 시총 보강(국내 KIS·해외 KIS×환율) → invest_amt 산출 → 변경 탐지.
어댑터 연속 실패 3회 → 그 어댑터 회로 차단(나머지 운용사는 계속).
주말은 스킵. 실행: venv python -m execution.boutique_etf.collect (repo 루트에서).
"""
import sys
import time
import traceback
from datetime import datetime

from . import adapters, changes, enrich, registry
from .db import init_db

SITE_SLEEP = 0.8   # 운용사 사이트 콜 간격
CIRCUIT_MAX = 3    # 어댑터 연속 실패 허용


def _collect_one(reg, ymd, date_dash):
    a, param, code = reg['adapter'], reg['param'], reg['etf_code']
    if a == 'timefolio':
        time.sleep(SITE_SLEEP)
        return adapters.fetch_timefolio(param)
    if a == 'koact':
        time.sleep(2.0)  # KoAct 는 25종 연속 호출 시 429 — 간격 상향
        try:
            return adapters.fetch_koact(param, ymd)
        except Exception as e:
            if '429' not in str(e):
                raise
            time.sleep(8)  # 429 → 1회 백오프 재시도
            return adapters.fetch_koact(param, ymd)
    if a == 'truston':
        time.sleep(SITE_SLEEP)
        return adapters.fetch_truston(param, date_dash)
    return adapters.fetch_kis(code)


def main():
    now = datetime.now()
    if now.weekday() >= 5:
        print('[boutique] 주말 — 스킵')
        return 0
    date = now.strftime('%Y-%m-%d')
    ymd = now.strftime('%Y%m%d')
    conn = init_db()

    warns = registry.sync(conn)
    for w in warns:
        print('[boutique][warn] %s' % w)

    regs = conn.execute(
        'SELECT * FROM etf_registry ORDER BY manager, etf_code').fetchall()
    fails = {}          # adapter → 연속 실패 수
    n_ok = n_fail = 0
    for reg in regs:
        code, a = reg['etf_code'], reg['adapter']
        prior = conn.execute(
            'SELECT status FROM collection_log WHERE date=? AND etf_code=?',
            (date, code)).fetchone()
        if prior and prior['status'] == 'ok':
            n_ok += 1  # 멱등 재실행: 당일 ok 는 재수집·다운그레이드 금지
            continue
        rows, meta, err = None, None, None
        if fails.get(a, 0) < CIRCUIT_MAX:
            try:
                rows, meta = _collect_one(reg, ymd, date)
                fails[a] = 0
            except Exception as e:
                fails[a] = fails.get(a, 0) + 1
                err = '%s: %s' % (a, e)
        else:
            err = '%s: 회로 차단' % a
        if rows is None and a != 'kis':
            try:
                rows, meta = adapters.fetch_kis(code)
                err = (err or '') + ' → kis 폴백'
            except Exception as e:
                err = '%s / kis 폴백도 실패: %s' % (err, e)
        quote = None
        try:
            time.sleep(0.12)
            quote = enrich.fetch_etf_quote(code)
        except Exception as e:
            print('[boutique][warn] %s KIS 시세 실패: %s' % (code, e))
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if rows is None:
            conn.execute(
                'INSERT OR REPLACE INTO collection_log VALUES (?,?,?,?,?,?,?)',
                (date, code, 'fail', a, 0, (err or '')[:300], ts))
            conn.commit()
            n_fail += 1
            print('[boutique][fail] %s %s: %s' % (code, reg['name'], err))
            continue
        aum = quote['aum'] if quote else None
        with conn:
            conn.execute('DELETE FROM etf_constituents WHERE date=? AND etf_code=?', (date, code))
            for r in rows:
                sc = r['stock_code'] or ('RAW:' + (r['raw_code'] or r['stock_name']))
                inv = (aum * r['weight'] / 100.0) if (aum and r['weight'] is not None) else None
                conn.execute(
                    'INSERT OR REPLACE INTO etf_constituents '
                    '(date,etf_code,stock_code,raw_code,stock_name,weight,qty_cu,eval_cu,px,'
                    ' mcap_krw,invest_amt,trade_amt,drift,source) '
                    'VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,0,?)',
                    (date, code, sc, r['raw_code'], r['stock_name'], r['weight'],
                     r['qty_cu'], r['eval_cu'], r['px'], r.get('mcap_krw'), inv,
                     meta['source']))
            conn.execute(
                'INSERT OR REPLACE INTO etf_daily VALUES (?,?,?,?,?,?,?,?,?)',
                (date, code, reg['name'], reg['manager'],
                 quote['close'] if quote else None,
                 quote['nav'] if quote else None,
                 quote['nav_prdy_ctrt'] if quote else None,
                 quote['lstn_stcn'] if quote else None, aum))
            conn.execute(
                'INSERT OR REPLACE INTO collection_log VALUES (?,?,?,?,?,?,?)',
                (date, code, 'ok', meta['source'], meta['truncated'],
                 (err or '')[:300] or None, ts))
        n_ok += 1

    _enrich_mcaps(conn, date)
    changes.compute_changes(conn, date)

    n_ch = conn.execute('SELECT COUNT(*) c FROM etf_changes WHERE date=?', (date,)).fetchone()['c']
    print('[boutique] %s 수집 ok=%d fail=%d 변경=%d' % (date, n_ok, n_fail, n_ch))
    return 0 if n_ok >= 10 else 1


def _enrich_mcaps(conn, date):
    """국내(KIS 일괄) + 미국(KIS 해외×환율) 시총 보강. 실패해도 수집 성공엔 영향 없음."""
    cached = {r['stock_code']: r['mcap_krw'] for r in conn.execute(
        'SELECT stock_code, mcap_krw FROM mcap_cache WHERE date=?', (date,))}
    need = [r['stock_code'] for r in conn.execute(
        "SELECT DISTINCT stock_code FROM etf_constituents "
        "WHERE date=? AND mcap_krw IS NULL AND stock_code LIKE 'KRX:%'", (date,))]
    dom = [c for c in need if c not in cached]
    if dom:
        try:
            got = enrich.domestic_mcaps([c.split(':', 1)[1] for c in dom])
            for c in dom:
                v = got.get(c.split(':', 1)[1])
                if v:
                    cached[c] = v
                    conn.execute('INSERT OR REPLACE INTO mcap_cache VALUES (?,?,?,?)',
                                 (date, c, v, 'kis'))
        except Exception as e:
            print('[boutique][warn] 국내 시총 보강 실패: %s' % e)
    fx = None
    try:
        fx = enrich.get_usdkrw()
    except Exception:
        pass
    if fx:
        us_need = [r['stock_code'] for r in conn.execute(
            "SELECT DISTINCT stock_code FROM etf_constituents "
            "WHERE date=? AND mcap_krw IS NULL AND stock_code LIKE 'US:%'", (date,))]
        excd = {r['ticker']: r['excd'] for r in conn.execute('SELECT * FROM excd_map')}
        for c in us_need:
            if c in cached:
                continue
            t = c.split(':', 1)[1]
            usd, ex = enrich.us_mcap_usd(t, excd.get(t))
            if usd:
                cached[c] = usd * fx
                conn.execute('INSERT OR REPLACE INTO mcap_cache VALUES (?,?,?,?)',
                             (date, c, usd * fx, 'kis_us'))
                if ex:
                    conn.execute('INSERT OR REPLACE INTO excd_map VALUES (?,?)', (t, ex))
    else:
        print('[boutique][warn] USDKRW 미확보 — 미국 시총 보강 생략')
    for c, v in cached.items():
        conn.execute(
            'UPDATE etf_constituents SET mcap_krw=? WHERE date=? AND stock_code=? AND mcap_krw IS NULL',
            (v, date, c))
    conn.commit()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
