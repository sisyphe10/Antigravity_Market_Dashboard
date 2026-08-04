# -*- coding: utf-8 -*-
"""부티크 액티브 ETF 일일 수집 오케스트레이터.

흐름: 레지스트리 갱신 → ETF별 구성종목(어댑터, 실패 시 KIS 폴백) + KIS 시세(NAV·AUM)
      → 시총 보강(국내 KIS·해외 KIS×환율) → invest_amt 산출 → 변경 탐지.
어댑터 연속 실패 3회 → 그 어댑터 회로 차단(나머지 운용사는 계속).
주말은 스킵. 실행: venv python -m execution.boutique_etf.collect (repo 루트에서).
"""
import hashlib
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


def _fingerprint(rows):
    """구성종목 스냅숏 지문 — 전일과 동일하면 PDF 미갱신(롤오버 전)으로 간주."""
    key = '|'.join('%s:%s:%s' % (r['raw_code'], r['qty_cu'], r['weight'])
                   for r in sorted(rows, key=lambda x: str(x['raw_code'])))
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]


def main(managers=None, quiet_alert=False):
    """managers=None 이면 전체. {'타임폴리오', ...} 를 주면 그 운용사만 수집(워처용)."""
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

    if managers:
        qs = ','.join('?' * len(managers))
        regs = conn.execute(
            'SELECT * FROM etf_registry WHERE manager IN (%s) ORDER BY manager, etf_code' % qs,
            tuple(managers)).fetchall()
    else:
        regs = conn.execute(
            'SELECT * FROM etf_registry ORDER BY manager, etf_code').fetchall()
    fails = {}          # adapter → 연속 실패 수
    n_ok = n_fail = n_stale = 0
    for reg in regs:
        code, a = reg['etf_code'], reg['adapter']
        prior = conn.execute(
            'SELECT status, collected_at, source, truncated FROM collection_log '
            'WHERE date=? AND etf_code=?', (date, code)).fetchone()
        # status='stale'(PDF 미갱신)은 재시도 대상.
        # ★열등 스냅숏(KIS 폴백 상위30 / 전용 어댑터가 아닌 출처)도 재시도 대상이다.
        #   429 로 폴백된 뒤 그날 내내 잘린 데이터로 굳으면, 다음날 31위 이하가
        #   전부 '신규편입' 으로 오인된다(2026-08-04 KoAct 9종 실제 발생).
        degraded = bool(prior) and (
            bool(prior['truncated']) or (a != 'kis' and prior['source'] == 'kis'))
        if prior and prior['status'] == 'ok' and not degraded:
            # 멱등 재실행: 구성종목은 재수집·다운그레이드 금지.
            # NAV·AUM 은 **장중에 잡힌 잠정치일 때만** 갱신한다.
            #   장 개시 전 수집분(아침 워처)은 PDF(D)=전일 종가 기준 보유분과 짝이 맞는
            #   전일 종가 NAV·AUM 을 이미 담고 있으므로 덮어쓰면 오히려 어긋난다.
            hhmm = (prior['collected_at'] or '')[11:16]
            if not ('09:00' <= hhmm <= '15:30'):
                n_ok += 1
                continue
            try:
                time.sleep(0.12)
                q = enrich.fetch_etf_quote(code)
                with conn:
                    conn.execute(
                        'UPDATE etf_daily SET close=?, nav=?, nav_prdy_ctrt=?, lstn_stcn=?, aum=? '
                        'WHERE date=? AND etf_code=?',
                        (q['close'], q['nav'], q['nav_prdy_ctrt'], q['lstn_stcn'],
                         q['aum'], date, code))
                    if q['aum']:
                        conn.execute(
                            'UPDATE etf_constituents SET invest_amt = ? * weight / 100.0 '
                            'WHERE date=? AND etf_code=? AND weight IS NOT NULL',
                            (q['aum'], date, code))
            except Exception as e:
                print('[boutique][warn] %s NAV/AUM 갱신 실패: %s' % (code, e))
            n_ok += 1
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
            if prior and prior['status'] == 'ok':
                # 열등 스냅숏 재시도가 실패한 경우 — 기존 ok 를 fail 로 강등하지 않는다.
                n_ok += 1
                print('[boutique][warn] %s 재시도 실패, 기존 스냅숏 유지: %s' % (code, err))
                continue
            conn.execute(
                'INSERT OR REPLACE INTO collection_log '
                '(date,etf_code,status,source,truncated,error_msg,collected_at,fingerprint) '
                'VALUES (?,?,?,?,?,?,?,NULL)',
                (date, code, 'fail', a, 0, (err or '')[:300], ts))
            conn.commit()
            n_fail += 1
            print('[boutique][fail] %s %s: %s' % (code, reg['name'], err))
            continue
        # PDF 롤오버 가드: 직전 ok 스냅숏과 지문이 같으면 미갱신 → status='stale'
        #   (변경탐지는 status='ok' 끼리만 비교하므로, 다음 갱신일에 옛 기준일과 정상 비교된다)
        fp = _fingerprint(rows)
        prev_fp = conn.execute(
            "SELECT fingerprint FROM collection_log WHERE etf_code=? AND date<? "
            "AND status='ok' ORDER BY date DESC LIMIT 1", (code, date)).fetchone()
        status = 'stale' if (prev_fp and prev_fp['fingerprint'] == fp) else 'ok'
        if status == 'stale':
            err = (err or '') + ' 동일 스냅숏(PDF 미갱신)'
            n_stale += 1
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
                'INSERT OR REPLACE INTO collection_log '
                '(date,etf_code,status,source,truncated,error_msg,collected_at,fingerprint) '
                'VALUES (?,?,?,?,?,?,?,?)',
                (date, code, status, meta['source'], meta['truncated'],
                 (err or '')[:300] or None, ts, fp))
        if status == 'ok':
            n_ok += 1

    _enrich_mcaps(conn, date)
    changes.compute_changes(conn, date)

    n_ch = conn.execute('SELECT COUNT(*) c FROM etf_changes WHERE date=?', (date,)).fetchone()['c']
    print('[boutique] %s 수집 ok=%d stale=%d fail=%d 변경=%d'
          % (date, n_ok, n_stale, n_fail, n_ch))
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
