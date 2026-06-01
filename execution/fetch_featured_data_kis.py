"""
Featured 데이터 수집 (KIS 전종목 배치 버전).

기존 fetch_featured_data.py(KRX OpenAPI, 일별배치 ~18:10)를 KIS로 대체.
KIS 랭킹 API는 top-30 하드캡이라 회전율·등락률(소형주 위주)을 못 채우는 한계가 있어,
**전 종목을 multprice로 배치 수집 → 로컬에서 필터·정렬**(KRX 방식 그대로)하는 구조.
→ 장 마감(15:30) 직후 값이 있어 16:00 같은날 6종 전부 생성 가능.

방식:
1) 마스터(code→상장주식수·시장·이름)를 FDR StockListing으로 주1회 구축(shares는 거의 불변).
2) 매일: KIS multprice(30종목/콜, ~96콜/~1분)로 현재가+거래대금+등락률 배치 수집.
3) 시총=현재가×shares, 회전율=거래대금/시총. 클라 필터 후 6종 nlargest 랭킹.

필터(결정적): 스팩/리츠 제외, code끝자리 0(보통주), **시총 2,000억 이상**.
범위: 랭킹 6종. 신고가(newhigh_*)는 별도(history) — 추후 포팅.
출력: featured_data_kis.json (기존과 동일 bare-array 누적 포맷 → 컷오버 시 drop-in).
"""
import sys
import os
import json
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', stream=sys.stdout)

from kis_token import kis_get

KST = timezone(timedelta(hours=9))
OUTPUT = 'featured_data_kis.json'
MASTER_FILE = 'kis_universe_master.json'
MASTER_MAX_AGE_DAYS = 7
TOP_N = 30
MIN_MKTCAP = 200_000_000_000   # 2,000억 (원)

# 20일 신고가 (텔레그램 알림용 산출물) — ra_sisyphe_bot이 16:00에 읽어 전송
YF_HISTORY_FILE = 'stock_price_history.json'    # yfinance 과거(폴백/초기 seed)
KIS_HISTORY_FILE = 'kis_price_history.json'      # 오늘부터 KIS 당일고가/종가 누적
KIS_HIST_KEEP_DAYS = 300                         # 52주(252) 룩백 + 버퍼 보관 (yfinance 폴백 의존도 점진 감소)
NEWHIGH_OUTPUT = 'newhigh_20d.json'
NEWHIGH_DAYS = 20
NEWHIGH_52W_DAYS = 252                           # 52주 ≈ 252거래일
WICS_FILE = 'wics_all.json'              # 전종목 WICS(GICS형) 섹터 (sub_sector=산업군 27종)
UNIVERSE_CSV = 'universe_tickers.csv'    # 섹터 폴백(수동 큐레이션 529종목)


def load_sector_map():
    """code → 섹터(GICS 산업군). wics_all 우선, universe CSV 폴백."""
    smap = {}
    try:
        for e in json.load(open(WICS_FILE, encoding='utf-8')):
            c = e.get('code'); s = e.get('sub_sector') or e.get('sector')
            if c and s:
                smap[c] = s
    except Exception as e:
        logging.warning('wics_all 로드 실패: %s', e)
    try:
        import csv
        for r in csv.DictReader(open(UNIVERSE_CSV, encoding='utf-8-sig')):
            tk = (r.get('티커') or '').strip()
            s = (r.get('섹터') or '').strip()
            if ':' in tk:
                c = tk.split(':')[1]
                if c.isdigit() and s and c not in smap:
                    smap[c] = s
    except Exception as e:
        logging.warning('universe CSV 섹터 폴백 실패: %s', e)
    return smap

MULTI_PATH = '/uapi/domestic-stock/v1/quotations/intstock-multprice'
MULTI_TRID = 'FHKST11300006'

# 마스터(상장주식수) 전용 KRX OpenAPI 키 — 정적 참조(주1회)용. 일일 시세는 KIS.
KRX_API_KEY = 'E9E8B0A915D74BC59CFA41D5534CF19EF4B24C9E'


def _to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def passes_filter(name, code, mktcap):
    if not name or not code:
        return False
    if '스팩' in name or '리츠' in name:
        return False
    if code[-1:] != '0':
        return False
    if mktcap < MIN_MKTCAP:
        return False
    return True


# ───────────────────────── 마스터 (상장주식수·시장·이름) ─────────────────────────
def build_master():
    """
    KRX OpenAPI(LIST_SHRS)로 code→{name,market,shares} 구축.
    최근 거래일 1일치면 충분(shares는 정적). 오늘 KRX 배치는 ~18:10이라 전일부터 탐색.
    FDR StockListing은 KRX HTML 차단/포맷오류로 불안정 → 사용 안 함.
    """
    from pykrx_openapi import KRXOpenAPI
    api = KRXOpenAPI(KRX_API_KEY)
    base = datetime.now(KST).date()
    for back in range(1, 9):
        d = base - timedelta(days=back)
        if d.weekday() >= 5:                     # 주말 제외
            continue
        ds = d.strftime('%Y%m%d')
        kospi = api.get_stock_daily_trade(ds).get('OutBlock_1', [])
        kosdaq = api.get_kosdaq_stock_daily_trade(ds).get('OutBlock_1', [])
        if not (kospi or kosdaq):
            continue
        master = {}
        for r in list(kospi) + list(kosdaq):
            code = str(r.get('ISU_CD', '')).strip()
            name = str(r.get('ISU_NM', '')).strip()
            market = str(r.get('MKT_NM', '')).strip()
            shares = _to_int(r.get('LIST_SHRS'))
            if market not in ('KOSPI', 'KOSDAQ'):
                continue
            if code and name and shares:
                master[code] = {'name': name, 'market': market, 'shares': shares}
        logging.info('마스터 소스 날짜 %s (KOSPI %d + KOSDAQ %d → %d종목)',
                     ds, len(kospi), len(kosdaq), len(master))
        return master
    raise RuntimeError('KRX 마스터 소스 거래일 없음(최근 8일)')


def load_master():
    """캐시가 신선하면 사용, 아니면 재구축. 재구축 실패 시 stale 폴백."""
    cached = None
    if os.path.exists(MASTER_FILE):
        try:
            with open(MASTER_FILE, encoding='utf-8') as f:
                cached = json.load(f)
            built = datetime.fromisoformat(cached['built_at'])
            age = (datetime.now(KST) - built).days
            if age < MASTER_MAX_AGE_DAYS and cached.get('master'):
                logging.info('마스터 캐시 사용 (%d일 전, %d종목)', age, len(cached['master']))
                return cached['master']
        except Exception as e:
            logging.warning('마스터 캐시 로드 실패: %s', e)

    logging.info('마스터 재구축 (KRX OpenAPI)...')
    try:
        master = build_master()
        if len(master) < 1000:
            raise RuntimeError(f'마스터 종목수 비정상({len(master)})')
        with open(MASTER_FILE, 'w', encoding='utf-8') as f:
            json.dump({'built_at': datetime.now(KST).isoformat(), 'master': master},
                      f, ensure_ascii=False)
        logging.info('마스터 구축 완료 (%d종목)', len(master))
        return master
    except Exception as e:
        if cached and cached.get('master'):
            logging.warning('마스터 재구축 실패(%s) → stale 캐시 사용', e)
            return cached['master']
        raise


# ───────────────────────── 배치 시세 수집 ─────────────────────────
def fetch_all_prices(codes):
    """multprice 30종목/콜 배치. code→{price,trdval,chg,high}."""
    result = {}
    chunks = [codes[i:i + 30] for i in range(0, len(codes), 30)]
    fail = 0
    for n, ch in enumerate(chunks, 1):
        params = {}
        for i, c in enumerate(ch, 1):
            params[f'FID_COND_MRKT_DIV_CODE_{i}'] = 'J'
            params[f'FID_INPUT_ISCD_{i}'] = c
        try:
            j = kis_get(MULTI_PATH, tr_id=MULTI_TRID, params=params)
            for row in (j.get('output') or []):
                code = row.get('inter_shrn_iscd')
                if not code:
                    continue
                result[code] = {
                    'price': _to_int(row.get('inter2_prpr')),
                    'trdval': _to_int(row.get('acml_tr_pbmn')),
                    'chg': _to_float(row.get('prdy_ctrt')),
                    'high': _to_int(row.get('inter2_hgpr')),
                }
        except Exception as e:
            fail += 1
            logging.warning('배치 %d/%d 실패: %s', n, len(chunks), e)
    logging.info('시세 배치 완료: %d/%d종목 (%d콜, 실패 %d)',
                 len(result), len(codes), len(chunks), fail)
    return result


# ───────────────────────── 유니버스 합성 + 필터 ─────────────────────────
def build_universe(master, prices):
    """마스터+시세 병합 → 시총·회전율 계산 → 필터 통과 종목."""
    rows = []
    for code, m in master.items():
        p = prices.get(code)
        if not p or not p['price']:
            continue
        mktcap = p['price'] * m['shares']
        if not passes_filter(m['name'], code, mktcap):
            continue
        trdval = p['trdval']
        rows.append({
            'code': code, 'name': m['name'], 'market': m['market'],
            'price': p['price'], 'chg': p['chg'],
            'trdval': trdval, 'mktcap': mktcap,
            'turnover': (trdval / mktcap * 100) if mktcap else 0,
        })
    return rows


def _records(sorted_rows, type_name, date_disp):
    out = []
    for rank, r in enumerate(sorted_rows[:TOP_N], 1):
        out.append({
            'd': date_disp, 'type': type_name, 'rank': rank,
            'name': r['name'], 'code': r['code'], 'market': r['market'],
            'trdval': int(r['trdval']), 'mktcap': int(r['mktcap']),
            'turnover': round(r['turnover'], 2), 'chg': round(r['chg'], 2),
            'price': int(r['price']),
        })
    return out


def rank_all(rows, date_disp):
    """기존 fetch_featured_data.py와 동일한 nlargest 랭킹 (6종)."""
    kospi = [r for r in rows if r['market'] == 'KOSPI']
    kosdaq = [r for r in rows if r['market'] == 'KOSDAQ']
    recs = []
    recs += _records(sorted(rows, key=lambda x: x['trdval'], reverse=True), 'absolute', date_disp)
    recs += _records(sorted(rows, key=lambda x: x['turnover'], reverse=True), 'turnover', date_disp)
    recs += _records(sorted(kospi, key=lambda x: x['mktcap'], reverse=True), 'kospi_cap', date_disp)
    recs += _records(sorted(kosdaq, key=lambda x: x['mktcap'], reverse=True), 'kosdaq_cap', date_disp)
    recs += _records(sorted(kospi, key=lambda x: x['chg'], reverse=True), 'kospi_chg', date_disp)
    recs += _records(sorted(kosdaq, key=lambda x: x['chg'], reverse=True), 'kosdaq_chg', date_disp)
    return recs


# ───────────────────────── KIS 가격 히스토리 누적 + 20일 신고가 ─────────────────────────
def accumulate_kis_history(master, prices, date_disp):
    """오늘 KIS 당일고가/종가를 kis_price_history.json에 누적(오늘 것 덮어쓰기) + 오래된 날짜 prune."""
    try:
        with open(KIS_HISTORY_FILE, encoding='utf-8') as f:
            hist = json.load(f)
    except Exception:
        hist = {'dates': [], 'stocks': {}}
    stocks = hist.setdefault('stocks', {})
    for code, p in prices.items():
        if not p.get('price') or not p.get('high'):
            continue
        m = master.get(code, {})
        st = stocks.setdefault(code, {'name': m.get('name', ''), 'market': m.get('market', ''),
                                      'highs': {}, 'closes': {}})
        st['highs'][date_disp] = p['high']       # 당일 고가
        st['closes'][date_disp] = p['price']     # 마감 후 현재가 = 종가
    dates = sorted(set(hist.get('dates', [])) | {date_disp})
    keep = set(dates[-KIS_HIST_KEEP_DAYS:])      # 최근 N거래일만 보관
    for st in stocks.values():
        st['highs'] = {d: v for d, v in st['highs'].items() if d in keep}
        st['closes'] = {d: v for d, v in st['closes'].items() if d in keep}
    hist['dates'] = sorted(keep)
    with open(KIS_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(hist, f, ensure_ascii=False)
    logging.info('KIS 히스토리 누적: %s (보관 %d거래일)', date_disp, len(keep))


def compute_newhigh_20d(master, prices, date_disp, now_iso):
    """
    20일 신고가: 당일 고가(KIS) > 과거 20거래일 고가 최대값. 거래대금순 stocks 리스트.
    각 종목에 is_52w 플래그(당일 고가 > 과거 252거래일 최대값=52주 신고가도 달성)를 부여.
    52주는 20일의 부분집합(252⊃20)이라 별도 리스트 대신 플래그로 표시 → 봇이 🔥 뱃지로 강조.
    과거 고가는 KIS 히스토리 우선 + yfinance 폴백 머지 → 누적될수록 자연히 KIS 단일화.
    ⚠️ yfinance 시드가 오래되면 그 갭 구간 고가 누락 → KIS 누적이 252일 채우기 전까지 52주 과다판정 여지.
    """
    def _load(path):
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {'dates': [], 'stocks': {}}
    yf_hist = _load(YF_HISTORY_FILE)
    kis_hist = _load(KIS_HISTORY_FILE)
    yf_stocks = yf_hist.get('stocks', {})
    kis_stocks = kis_hist.get('stocks', {})
    sector_map = load_sector_map()

    out20 = []
    for code, m in master.items():
        p = prices.get(code)
        if not p or not p.get('price') or not p.get('high'):
            continue
        mktcap = p['price'] * m['shares']
        if not passes_filter(m['name'], code, mktcap):
            continue
        # 과거 고가 머지: 날짜별 KIS 우선, 없으면 yfinance
        yf_h = (yf_stocks.get(code) or {}).get('highs', {})
        kis_h = (kis_stocks.get(code) or {}).get('highs', {})
        past = {}
        for d, v in yf_h.items():
            if d < date_disp and v:
                past[d] = v
        for d, v in kis_h.items():                # KIS가 덮어씀(우선)
            if d < date_disp and v:
                past[d] = v
        if not past:
            continue
        dates_sorted = sorted(past)
        recent20 = dates_sorted[-NEWHIGH_DAYS:]
        prev20 = max(past[d] for d in recent20)
        if p['high'] <= prev20:
            continue
        # 20일 신고가 → 52주 신고가 여부도 판정(부분집합이라 20일 통과분만 검사)
        recent52 = dates_sorted[-NEWHIGH_52W_DAYS:]
        prev52 = max(past[d] for d in recent52)
        is_52w = p['high'] > prev52
        out20.append({
            'code': code, 'name': m['name'], 'market': m['market'],
            'sector': sector_map.get(code, '기타'),
            'price': p['price'], 'chg': round(p['chg'], 2),
            'high': p['high'], 'prev_high': prev20, 'trdval': p['trdval'], 'mktcap': mktcap,
            'lookback': len(recent20), 'is_52w': is_52w, 'lookback_52w': len(recent52),
        })
    out20.sort(key=lambda x: x['trdval'], reverse=True)   # 거래대금순
    n52 = sum(1 for s in out20 if s['is_52w'])
    with open(NEWHIGH_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump({'date': date_disp, 'ranked_at': now_iso,
                   'lookback_days': NEWHIGH_DAYS, 'lookback_52w_days': NEWHIGH_52W_DAYS,
                   'count': len(out20), 'count_52w': n52, 'stocks': out20},
                  f, ensure_ascii=False)
    logging.info('신고가: 20일 %d종목 (그중 52주 %d) → %s', len(out20), n52, NEWHIGH_OUTPUT)
    return out20


def main():
    now = datetime.now(tz=KST)
    date_disp = now.strftime('%Y-%m-%d')
    logging.info('KIS Featured(전종목 배치) 수집 시작 (%s)', date_disp)

    master = load_master()
    prices = fetch_all_prices(list(master.keys()))
    rows = build_universe(master, prices)
    logging.info('필터 통과(시총 %d억 이상): %d종목', MIN_MKTCAP // 100_000_000, len(rows))

    records = rank_all(rows, date_disp)

    # 20일 신고가(텔레그램용) 계산 → 오늘 KIS 고가/종가 누적
    newhigh = compute_newhigh_20d(master, prices, date_disp, now.isoformat())
    accumulate_kis_history(master, prices, date_disp)

    from collections import Counter
    cnt = Counter(r['type'] for r in records)
    for t in ['absolute', 'turnover', 'kospi_cap', 'kosdaq_cap', 'kospi_chg', 'kosdaq_chg']:
        n = cnt.get(t, 0)
        logging.info('  %-12s %d건%s', t, n, '  (주의) <30' if n < TOP_N else '')

    # 기존 포맷(bare array) 누적: 오늘 레코드 교체 후 저장 (drop-in 호환)
    if os.path.exists(OUTPUT):
        try:
            with open(OUTPUT, encoding='utf-8') as f:
                allrec = json.load(f)
            if isinstance(allrec, dict):       # 과거 PoC의 {meta,records} 포맷 정리
                allrec = allrec.get('records', [])
        except Exception:
            allrec = []
    else:
        allrec = []
    allrec = [r for r in allrec if r.get('d') != date_disp]   # 오늘 것 제거 후
    allrec.extend(records)                                    # 새로 추가
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(allrec, f, ensure_ascii=False)

    dates = sorted({r['d'] for r in allrec})
    logging.info('완료! ranked_at=%s | 오늘 %d건 / 전체 %d건 (%s~%s) → %s',
                 now.isoformat(), len(records), len(allrec),
                 dates[0] if dates else '-', dates[-1] if dates else '-', OUTPUT)


if __name__ == '__main__':
    main()
