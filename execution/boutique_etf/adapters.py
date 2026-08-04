# -*- coding: utf-8 -*-
"""운용사별 구성종목 어댑터 — 공통 반환형 (rows, meta).

row  = {raw_code, stock_code(정규화, 미해결=None), stock_name, qty_cu, eval_cu, weight, px, mcap_krw}
meta = {source, truncated, effective_date(YYYYMMDD | None)}

수량·평가금액은 전 출처가 1CU 기준(운용사 PDF 관례) — 펀드 전체 금액은
invest_amt = AUM × weight/100 로 collect 단계에서 산출한다.
현금성·파생 행은 여기서 제외.
"""
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request

_EXEC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _EXEC_DIR not in sys.path:
    sys.path.insert(0, _EXEC_DIR)

from kis_token import kis_get  # noqa: E402

UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
CASH_KW = ('현금', '예수금', '예금', 'KRW', 'CASH', '원화', '설정현금')
DERIV_KW = ('선물', '스왑', 'SWAP', 'FUTURE')


def _get(url, timeout=25, data=None, headers=None):
    h = dict(UA)
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    return urllib.request.urlopen(req, timeout=timeout).read()


def _num(v):
    if v in (None, ''):
        return None
    try:
        return float(str(v).replace(',', ''))
    except ValueError:
        return None


def _is_cash(raw, name):
    up = (name or '').upper()
    return (raw or '').startswith('KRD01') or any(k in up for k in CASH_KW)


def _is_deriv(name):
    up = (name or '').upper()
    return any(k in up for k in DERIV_KW)


def normalize_code(raw):
    """국내 6자리/신형코드·KR ISIN·블룸버그식 → 표준 코드. 미해결 None."""
    raw = (raw or '').strip()
    if re.fullmatch(r'\d{6}', raw) or re.fullmatch(r'\d{4}[0-9A-Z]\d', raw):
        return 'KRX:' + raw
    m = re.fullmatch(r'KR7(\w{6})\w{3}', raw)
    if m:
        return 'KRX:' + m.group(1)
    m = re.fullmatch(r'([A-Z0-9./]{1,12})\s+(US|UW|UN|UQ)\s+EQUITY', raw, re.I)
    if m:
        return 'US:' + m.group(1).upper().replace('/', '.')
    m = re.fullmatch(r'(\d{1,5})\s+HK\s+EQUITY', raw, re.I)
    if m:
        return 'HK:' + m.group(1).zfill(4)
    if re.fullmatch(r'[A-Z][A-Z0-9.]{0,9}', raw) and not raw.startswith('KR'):
        return 'US:' + raw  # KoAct 해외(미국 티커 관례) 추정
    return None


def _row(raw, name, qty, ev, w, px=None, mcap=None):
    return {'raw_code': raw, 'stock_code': normalize_code(raw), 'stock_name': name,
            'qty_cu': qty, 'eval_cu': ev, 'weight': w, 'px': px, 'mcap_krw': mcap}


def fetch_timefolio(idx):
    """timeetf.co.kr 구성종목 xlsx — 컬럼: 종목코드·종목명·수량·평가금액(원)·비중(%)"""
    import openpyxl
    b = _get('https://timeetf.co.kr/pdf_excel.php?idx=%s' % idx)
    if not b.startswith(b'PK'):
        raise RuntimeError('timefolio: xlsx 아님 (차단/구조변경 의심)')
    ws = openpyxl.load_workbook(io.BytesIO(b), read_only=True).active
    rows = []
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue
        vals = (list(r) + [None] * 5)[:5]
        raw = str(vals[0] or '').strip()
        name = str(vals[1] or '').strip()
        if (not raw and not name) or _is_cash(raw, name) or _is_deriv(name):
            continue
        qty, ev, w = _num(vals[2]), _num(vals[3]), _num(vals[4])
        px = (ev / qty) if (ev and qty) else None
        rows.append(_row(raw, name, qty, ev, w, px))
    if not rows:
        raise RuntimeError('timefolio: 구성종목 0행')
    return rows, {'source': 'timefolio', 'truncated': 0, 'effective_date': None}


def fetch_koact(fid, ymd):
    """samsungactive etf-pdf JSON — itmNo·secNm·applyQ(수량)·evalA(평가액 원)·ratio(비중)"""
    d = json.loads(_get(
        'https://www.samsungactive.co.kr/api/v1/product/etf-pdf/%s.do?gijunYMD=%s' % (fid, ymd)))
    pdf = d.get('pdf') or {}
    eff = str(pdf.get('gijunYMD') or '') or None
    rows = []
    for r in pdf.get('list') or []:
        raw = str(r.get('itmNo') or '').strip()
        name = str(r.get('secNm') or '').strip()
        if _is_cash(raw, name) or _is_deriv(name):
            continue
        qty, ev, w = _num(r.get('applyQ')), _num(r.get('evalA')), _num(r.get('ratio'))
        px = _num(r.get('curp')) or ((ev / qty) if (ev and qty) else None)
        rows.append(_row(raw, name, qty, ev, w, px))
    if not rows:
        raise RuntimeError('koact: 구성종목 0행 (fid=%s)' % fid)
    return rows, {'source': 'koact', 'truncated': 0, 'effective_date': eff}


def fetch_truston(page_url, date_dash):
    """트러스톤 WP admin-ajax query_pdf — 페이지에서 nonce·fund_code 추출 후 POST"""
    p = _get(page_url).decode('utf-8', 'ignore')
    n = re.search(r'"nonce":"([a-f0-9]+)"', p)
    fc = re.search(r'id="fund_code" value="([A-Z0-9]+)"', p)
    if not (n and fc):
        raise RuntimeError('truston: nonce/fund_code 추출 실패')
    data = urllib.parse.urlencode({
        'action': 'query_pdf', 'nonce': n.group(1),
        'fund_code': fc.group(1), 'date': date_dash}).encode()
    d = json.loads(_get('https://www.trustonasset.com/wp-admin/admin-ajax.php',
                        data=data, headers={'X-Requested-With': 'XMLHttpRequest'}))
    if not d.get('success'):
        raise RuntimeError('truston: query_pdf 실패')
    dd = d.get('data') or {}
    eff = (dd.get('date') or '').replace('-', '') or None
    rows = []
    for r in dd.get('pdf') or []:
        raw = str(r.get('stock_code') or '').strip()
        name = str(r.get('stock_name') or '').strip()
        if _is_cash(raw, name) or _is_deriv(name):
            continue
        qty, ev, w = _num(r.get('quantity')), _num(r.get('price')), _num(r.get('ratio'))
        px = (ev / qty) if (ev and qty) else None
        rows.append(_row(raw, name, qty, ev, w, px))
    if not rows:
        raise RuntimeError('truston: 구성종목 0행')
    return rows, {'source': 'truston', 'truncated': 0, 'effective_date': eff}


def fetch_kis(etf_code):
    """KIS ETF 구성종목 시세 — 상위 30종목 한도. hts_avls(시총 억원)까지 동봉."""
    j = kis_get('/uapi/etfetn/v1/quotations/inquire-component-stock-price', 'FHKST121600C0',
                {'FID_COND_MRKT_DIV_CODE': 'J', 'FID_INPUT_ISCD': etf_code,
                 'FID_COND_SCR_DIV_CODE': '11216'})
    out = j.get('output2') or []
    rows = []
    for r in out:
        raw = str(r.get('stck_shrn_iscd') or '').strip()
        name = str(r.get('hts_kor_isnm') or '').strip()
        if _is_cash(raw, name) or _is_deriv(name):
            continue
        qty = _num(r.get('etf_cu_unit_scrt_cnt'))
        ev = _num(r.get('etf_cnfg_issu_avls'))
        avls = _num(r.get('hts_avls'))
        rows.append(_row(raw, name, qty, ev, None,
                         _num(r.get('stck_prpr')), avls * 1e8 if avls else None))
    if not rows:
        raise RuntimeError('kis: 구성종목 0행 (%s)' % etf_code)
    tot = sum(r['eval_cu'] or 0 for r in rows)
    if tot:
        for r in rows:
            r['weight'] = round((r['eval_cu'] or 0) / tot * 100, 2)
    return rows, {'source': 'kis', 'truncated': 1 if len(out) >= 30 else 0,
                  'effective_date': None}
