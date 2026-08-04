# -*- coding: utf-8 -*-
"""NAV·AUM(KIS ETF 시세) + 시가총액(국내 KIS, 해외 KIS 해외시세×환율) 보강."""
import glob
import os
import sys
import time

_EXEC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _EXEC_DIR not in sys.path:
    sys.path.insert(0, _EXEC_DIR)

from kis_token import kis_get  # noqa: E402
from kis_marcap import fetch_marcap  # noqa: E402

_KIS_SLEEP = 0.12  # 초당 8콜 수준 보수 스로틀


def fetch_etf_quote(etf_code):
    """KIS ETF 현재가 — nav·상장좌수·순자산. AUM = nav × lstn_stcn (원)."""
    j = kis_get('/uapi/etfetn/v1/quotations/inquire-price', 'FHPST02400000',
                {'FID_COND_MRKT_DIV_CODE': 'J', 'FID_INPUT_ISCD': etf_code})
    o = j.get('output') or {}

    def f(k):
        try:
            return float(o.get(k) or 0)
        except ValueError:
            return 0.0

    nav, lstn = f('nav'), f('lstn_stcn')
    # ★빈 응답(장 전·조회 실패)은 전 필드가 0 으로 온다. 그대로 쓰면 AUM=0 이 되어
    #   etf_daily 는 0 으로 덮이고 constituents 의 invest_amt 는 남아 두 표가 어긋난다.
    if nav <= 0 or lstn <= 0:
        raise RuntimeError('KIS ETF 시세 이상치 (nav=%s, lstn=%s)' % (nav, lstn))
    return {'close': f('stck_prpr'), 'nav': nav, 'nav_prdy_ctrt': f('nav_prdy_ctrt'),
            'prdy_last_nav': f('prdy_last_nav'),
            'lstn_stcn': int(lstn), 'aum': nav * lstn,
            'ntas_e8': f('etf_ntas_ttam') * 1e8,
            'manager_kis': (o.get('mbcr_name') or '').strip()}


def domestic_mcaps(codes):
    """국내 종목 시총 (억원→원). kis_marcap 재사용."""
    time.sleep(_KIS_SLEEP)
    m = fetch_marcap(codes)
    return {c: v * 1e8 for c, v in m.items()}


_EXCD_TRY = ('NAS', 'NYS', 'AMS')
# HHDFS76200200 tomv 단위 = USD (2026-08-04 NVDA 실측: tomv 5,000,688,000,000 = last×shar)
TOMV_SCALE = float(os.environ.get('BOUTIQUE_TOMV_SCALE') or 1.0)


def us_mcap_usd(ticker, excd_hint=None):
    """KIS 해외주식 현재가상세 → (mcap_usd, excd). 실패 시 (None, None)."""
    order = ([excd_hint] if excd_hint else []) + [e for e in _EXCD_TRY if e != excd_hint]
    for excd in order:
        try:
            time.sleep(_KIS_SLEEP)
            j = kis_get('/uapi/overseas-price/v1/quotations/price-detail', 'HHDFS76200200',
                        {'AUTH': '', 'EXCD': excd, 'SYMB': ticker})
            o = j.get('output') or {}
            tomv = o.get('tomv')
            if tomv and float(tomv) > 0:
                return float(tomv) * TOMV_SCALE, excd
        except Exception:
            continue
    return None, None


def get_usdkrw():
    """차트뷰어와 동일 소스(ECOS fx.csv, usdkrw 컬럼) 마지막 값. 실패 시 None."""
    override = os.environ.get('BOUTIQUE_USDKRW')
    if override:
        return float(override)
    candidates = glob.glob(os.path.expanduser('~/work/charts/*/fx.csv'))
    for path in sorted(candidates):
        try:
            with open(path, encoding='utf-8') as fh:
                header = fh.readline().strip().split(',')
                if 'usdkrw' not in header:
                    continue
                idx = header.index('usdkrw')
                last = None
                for line in fh:
                    parts = line.strip().split(',')
                    if len(parts) > idx and parts[idx]:
                        last = parts[idx]
                if last:
                    return float(last)
        except Exception:
            continue
    return None
