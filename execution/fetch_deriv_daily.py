# -*- coding: utf-8 -*-
"""삼성전자·SK하이닉스 파생·수급 + VKOSPI 일별 수집 → dataset.csv 적재.

시리즈 13종 (2026-07-16 신설, 이력 백필=커밋 19eeefcd):
  종목별(삼성전자·SK하이닉스):
    '<종목> 현선물 괴리율'      %  — KRX MDCSTAT12501 최근월물 (선물-현물)/현물×100
    '<종목> 미결제약정'         계약 — 전월물 합산
    '<종목> 미결제약정 금액'    억원 — 합산계약×승수10주×최근월물 종가
    '<종목> 공매도잔고'         억원 — pykrx 공매도금액 (T+2 공시)
    '<종목> 시가총액'           억원 — pykrx get_market_cap_by_date
    '<종목> 레버리지 ETF AUM'   억원 — KRX MDCSTAT04501 단일종목 레버리지(인버스 제외) 순자산 합산
  'VKOSPI'                      pt — KIS FHKUP03500100 (업종 U/0503)

실행: 맥미니 launchd deriv-daily (23:40 KST, kodex-sectors 23:30 뒤 — KRX 로그인 직렬화).
기본 최근 7일 upsert(휴장일 조용 skip, T+2 공매도 자연 보정). --days N 로 조정.
차트: create_dashboard.py DATA 탭 '파생·수급' 그룹.
"""
import os
import sys
import time
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET = os.path.join(DASHBOARD_DIR, 'dataset.csv')

import pandas as pd

NAMES = {'005930': '삼성전자', '000660': 'SK하이닉스'}
KRX_URL = 'https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd'


def _num(s):
    s = str(s).replace(',', '').strip()
    return None if s in ('-', '', 'None', 'nan') else float(s)


def krx_session():
    from fetch_krx_valuation import load_krx_creds
    kid, kpw = load_krx_creds()
    if not (kid and kpw):
        raise RuntimeError('KRX 자격증명 없음 (secrets/data.krx.txt)')
    os.environ['KRX_ID'], os.environ['KRX_PW'] = kid, kpw
    from pykrx.website.comm import auth
    sess = auth.build_krx_session(kid, kpw)
    if not sess:
        raise RuntimeError('KRX 로그인 실패')
    return sess


def collect(days):
    end = datetime.now()
    start = end - timedelta(days=days)
    s8, e8 = start.strftime('%Y%m%d'), end.strftime('%Y%m%d')
    rows = []  # (날짜, 제품명, 가격, 타입)

    sess = krx_session()
    from pykrx import stock

    # 1) 시가총액·공매도 (pykrx, 인증 세션 공유)
    for code, nm in NAMES.items():
        mc = stock.get_market_cap_by_date(s8, e8, code)
        for dt, r in mc.iterrows():
            rows.append((dt.strftime('%Y-%m-%d'), f'{nm} 시가총액',
                         round(float(r['시가총액']) / 1e8, 0), 'DERIV'))
        time.sleep(0.5)
        sb = stock.get_shorting_balance_by_date(s8, e8, code)
        for dt, r in sb.iterrows():
            amt = _num(r.get('공매도금액'))
            if amt:
                rows.append((dt.strftime('%Y-%m-%d'), f'{nm} 공매도잔고',
                             round(amt / 1e8, 1), 'DERIV'))
        time.sleep(0.5)

    # 거래일 축 = 시가총액 관측일
    trd_days = sorted({d for d, p, *_ in rows if p.endswith('시가총액')})

    # 2) 주식선물 (일자별 조회 — 괴리율·미결제)
    fails = 0
    for d in trd_days:
        d8 = d.replace('-', '')
        try:
            r = sess.post(KRX_URL, data={
                'bld': 'dbms/MDC/STAT/standard/MDCSTAT12501', 'locale': 'ko_KR',
                'trdDd': d8, 'prodId': 'KRDRVFUEQU', 'csvxls_isNo': 'false'}, timeout=40)
            r.raise_for_status()
            out = r.json().get('output', [])
            fails = 0
        except Exception as e:
            fails += 1
            print(f'  선물 {d} FAIL: {e} (연속 {fails})')
            if fails >= 5:
                raise RuntimeError('선물 조회 연속 5회 실패 — 중단 (KRX 잠금 예방)')
            time.sleep(3)
            continue
        for nm in NAMES.values():
            cons = []
            for x in out:
                name = str(x.get('ISU_NM', '')).strip()
                if not name.startswith(nm):
                    continue
                toks = name.split()
                if not (toks and toks[-1].isdigit()):
                    continue
                cons.append({'mat': toks[-1], 'close': _num(x['TDD_CLSPRC']),
                             'setl': _num(x.get('SETL_PRC')), 'spot': _num(x['SPOT_PRC']),
                             'oi': _num(x['ACC_OPNINT_QTY']) or 0})
            if not cons:
                continue
            cons.sort(key=lambda z: z['mat'])
            near = cons[0]
            fut = near['close'] if near['close'] is not None else near['setl']
            if fut is None or not near['spot']:
                continue
            total_oi = sum(z['oi'] for z in cons)
            rows.append((d, f'{nm} 현선물 괴리율', round((fut - near['spot']) / near['spot'] * 100, 4), 'DERIV'))
            rows.append((d, f'{nm} 미결제약정', float(total_oi), 'DERIV'))
            rows.append((d, f'{nm} 미결제약정 금액', round(total_oi * 10 * fut / 1e8, 1), 'DERIV'))
        time.sleep(0.5)

    # 3) 레버리지 ETF AUM (단일종목·인버스 제외, 기간 조회 후 일별 합산)
    base = sess.post(KRX_URL, data={
        'bld': 'dbms/MDC/STAT/standard/MDCSTAT04301', 'locale': 'ko_KR',
        'trdDd': trd_days[-1].replace('-', '') if trd_days else e8,
        'share': '1', 'money': '1', 'csvxls_isNo': 'false'}, timeout=40).json()
    targets = [t for t in (base.get('output') or base.get('OutBlock_1') or [])
               if '단일' in t.get('ISU_ABBRV', '') and '인버스' not in t.get('ISU_ABBRV', '')]
    agg = {}
    for t in targets:
        name = t.get('ISU_ABBRV', '')
        under = '삼성전자' if '삼성전자' in name else ('SK하이닉스' if '하이닉스' in name else None)
        if not under:
            continue
        isin = t.get('ISU_CD') or ''
        try:
            j = sess.post(KRX_URL, data={
                'bld': 'dbms/MDC/STAT/standard/MDCSTAT04501', 'locale': 'ko_KR',
                'tboxisuCd_finder_secuprodisu1_0': f"{t.get('ISU_SRT_CD')}/{name}",
                'isuCd': isin, 'isuCd2': isin,
                'codeNmisuCd_finder_secuprodisu1_0': name,
                'param1isuCd_finder_secuprodisu1_0': '',
                'strtDd': s8, 'endDd': e8,
                'share': '1', 'money': '1', 'csvxls_isNo': 'false'}, timeout=40).json()
        except Exception as e:
            print(f'  ETF {name} FAIL: {e}')
            continue
        for r in (j.get('output') or []):
            a = _num(r.get('INVSTASST_NETASST_TOTAMT'))
            if a:
                k = (r['TRD_DD'].replace('/', '-'), under)
                agg[k] = agg.get(k, 0.0) + a / 1e8
        time.sleep(0.5)
    for (d, under), v in agg.items():
        rows.append((d, f'{under} 레버리지 ETF AUM', round(v, 1), 'DERIV'))

    # 4) VKOSPI (KIS 업종 U/0503, FHKUP03500100)
    try:
        from kis_token import kis_get
        j = kis_get('/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice',
                    'FHKUP03500100',
                    {'FID_COND_MRKT_DIV_CODE': 'U', 'FID_INPUT_ISCD': '0503',
                     'FID_INPUT_DATE_1': s8, 'FID_INPUT_DATE_2': e8,
                     'FID_PERIOD_DIV_CODE': 'D'})
        for r in (j.get('output2') or []):
            d, v = r.get('stck_bsop_date'), _num(r.get('bstp_nmix_prpr'))
            if d and v:
                rows.append((f'{d[:4]}-{d[4:6]}-{d[6:]}', 'VKOSPI', round(v, 2), 'INDEX_KR'))
    except Exception as e:
        print(f'  VKOSPI FAIL (계속 진행): {e}')

    return rows


def upsert(rows):
    if not rows:
        print('신규 관측치 없음 (휴장일?) — 조용히 종료')
        return False
    new = pd.DataFrame(rows, columns=['날짜', '제품명', '가격', '데이터 타입'])
    df = pd.read_csv(DATASET, encoding='utf-8-sig')
    before = len(df)
    merged = pd.concat([df, new], ignore_index=True)
    merged = merged.drop_duplicates(subset=['날짜', '제품명'], keep='last')
    changed = not (len(merged) == before and new.merge(
        df, on=['날짜', '제품명'], suffixes=('', '_old'))['가격'].equals(
        new.merge(df, on=['날짜', '제품명'], suffixes=('', '_old'))['가격_old']))
    merged.to_csv(DATASET, index=False, encoding='utf-8-sig')
    print(f'dataset.csv {before} -> {len(merged)} (관측치 {len(new)}건 upsert)')
    latest = new.groupby('제품명')['날짜'].max()
    for p, d in latest.items():
        v = new[(new['제품명'] == p) & (new['날짜'] == d)]['가격'].iloc[-1]
        print(f'  {p}: ~{d} = {v}')
    return changed


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=7, help='조회 기간 (기본 7일)')
    args = ap.parse_args()
    upsert(collect(args.days))
