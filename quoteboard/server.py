"""
관심종목 실시간 시세판 서버 (POP HTS 상시실행 대체).

- 종목: universe_tickers.csv의 KRX:/KOSDAQ: 종목 전부 (~463)
- 시세: KIS multprice(FHKST11300006) 30종목/콜 배치, 기본 1초 스윕(실패 시 최대 10초 백오프)
- 시총: 현재가 x 상장주식수 (상장주식수는 KIS inquire-price로 매일 1회 갱신,
        첫 기동은 kis_universe_master.json / 이전 캐시로 즉시 시작)
- 서빙: http://127.0.0.1:8778/  (index.html + /data JSON, 프런트는 1초 폴링)

실행:  python quoteboard/server.py [--interval 3.0] [--port 8778]
"""
import os
import sys
import csv
import json
import time
import logging
import argparse
import threading
from datetime import datetime, timezone, timedelta
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
sys.path.insert(0, os.path.join(ROOT, 'execution'))
from kis_token import kis_get  # noqa: E402  (0.06s 자체 스로틀 내장)

KST = timezone(timedelta(hours=9))
UNIVERSE_CSV = os.path.join(ROOT, 'universe_tickers.csv')
ETF_CSV = os.path.join(BASE, 'etf_tickers.csv')     # 선별 ETF (universe와 분리, 섹터='ETF')
MASTER_FILE = os.path.join(ROOT, 'kis_universe_master.json')
SHARES_CACHE = os.path.join(BASE, 'shares_cache.json')
WL_PATH = os.path.join(BASE, 'watchlists.json')     # 관심종목 그룹 (기기 공통, 서버 저장)
STARS_PATH = os.path.join(BASE, 'market_stars.json')  # market DATA 차트 별표 (기기 공통, 서버 저장)
PREFS_PATH = os.path.join(BASE, 'prefs.json')       # AoE 화면 뷰 설정 KV (기기 공통, POST=병합)

MULTI_PATH = '/uapi/domestic-stock/v1/quotations/intstock-multprice'
MULTI_TRID = 'FHKST11300006'
PRICE_PATH = '/uapi/domestic-stock/v1/quotations/inquire-price'
PRICE_TRID = 'FHKST01010100'

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

STOCKS = []          # [{code, name, sector}]
SHARES = {}          # code -> 상장주식수
SNAP = {}            # code -> {price, chg, trdval}
META = {'sweep_at': None, 'sweep_ms': 0, 'fail': 0, 'shares_date': None}
_LOCK = threading.Lock()


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


def load_universe():
    rows = []
    seen = set()
    with open(UNIVERSE_CSV, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            tk = (r.get('티커') or '').strip()
            if not tk.startswith(('KRX:', 'KOSDAQ:')):
                continue
            code = tk.split(':')[1]
            # KRX 신형 영숫자 코드 허용 (예: 0126Z0 삼성에피스홀딩스, 0009K0 에임드바이오)
            if not (len(code) == 6 and code.isalnum()) or code in seen:
                continue
            seen.add(code)
            rows.append({'code': code,
                         'name': (r.get('기업명') or '').strip(),
                         'sector': (r.get('섹터') or '').strip() or '기타'})
    return rows


def load_etfs():
    """quoteboard/etf_tickers.csv → 선별 ETF 목록 (섹터='ETF'). 파일 없으면 빈 목록."""
    rows, seen = [], set()
    try:
        with open(ETF_CSV, encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                code = (r.get('코드') or '').strip().upper()
                if not (len(code) == 6 and code.isalnum()) or code in seen:
                    continue
                seen.add(code)
                rows.append({'code': code,
                             'name': (r.get('종목명') or '').strip() or code,
                             'sector': 'ETF'})
    except FileNotFoundError:
        pass
    return rows


def seed_shares():
    """기동 즉시 쓸 상장주식수: 오늘자 캐시 > 이전 캐시 > featured 마스터."""
    today = datetime.now(KST).strftime('%Y-%m-%d')
    try:
        c = json.load(open(SHARES_CACHE, encoding='utf-8'))
        SHARES.update({k: int(v) for k, v in c.get('shares', {}).items()})
        META['shares_date'] = c.get('date')
        logging.info('상장주식수 캐시 로드 (%s, %d종목)', c.get('date'), len(SHARES))
        if c.get('date') == today:
            return True   # 오늘자 → 재조회 불필요
    except Exception:
        pass
    if not SHARES:
        try:
            m = json.load(open(MASTER_FILE, encoding='utf-8'))
            for code, v in (m.get('master') or {}).items():
                if code not in SHARES and v.get('shares'):
                    SHARES[code] = int(v['shares'])
            logging.info('featured 마스터에서 seed (%d종목)', len(SHARES))
        except Exception as e:
            logging.warning('마스터 seed 실패: %s', e)
    return False


def refresh_shares(targets=None):
    """KIS inquire-price로 상장주식수 갱신 (targets=None이면 전 종목, 지정 시 누락분만)."""
    today = datetime.now(KST).strftime('%Y-%m-%d')
    fetch_list = targets if targets else [s['code'] for s in STOCKS]
    got, fail = {}, 0
    for code in fetch_list:
        try:
            j = kis_get(PRICE_PATH, tr_id=PRICE_TRID,
                        params={'FID_COND_MRKT_DIV_CODE': 'J',
                                'FID_INPUT_ISCD': code})
            n = _to_int((j.get('output') or {}).get('lstn_stcn'))
            if n:
                got[code] = n
        except Exception:
            fail += 1
    if got:
        with _LOCK:
            SHARES.update(got)
            META['shares_date'] = today
            merged = dict(SHARES)
        json.dump({'date': today, 'shares': merged},
                  open(SHARES_CACHE, 'w', encoding='utf-8'))
    logging.info('상장주식수 갱신 완료 %d/%d (실패 %d)', len(got), len(fetch_list), fail)


def sweep_once(codes):
    """multprice 30종목/콜 전체 1회 스윕 → SNAP 갱신."""
    fail = 0
    for i in range(0, len(codes), 30):
        ch = codes[i:i + 30]
        params = {}
        for k, c in enumerate(ch, 1):
            params[f'FID_COND_MRKT_DIV_CODE_{k}'] = 'J'
            params[f'FID_INPUT_ISCD_{k}'] = c
        try:
            j = kis_get(MULTI_PATH, tr_id=MULTI_TRID, params=params)
            with _LOCK:
                for row in (j.get('output') or []):
                    code = row.get('inter_shrn_iscd')
                    if not code:
                        continue
                    SNAP[code] = {
                        'price': _to_int(row.get('inter2_prpr')),
                        'chg': _to_float(row.get('prdy_ctrt')),
                        'trdval': _to_int(row.get('acml_tr_pbmn')),
                    }
        except Exception as e:
            fail += 1
            logging.warning('배치 %d 실패: %s', i // 30 + 1, e)
    return fail


def effective_interval(base):
    """장중(평일 08:50~15:45 KST)=base, 장외=60초 (KIS 쿼터 절약)."""
    now = datetime.now(KST)
    if now.weekday() < 5 and '08:50' <= now.strftime('%H:%M') < '15:45':
        return base
    return 60.0


def poll_loop(interval):
    codes = [s['code'] for s in STOCKS]
    backoff = 0.0     # 배치 실패(KIS 한도 충돌 등) 시 스윕 간격 일시 확대 → 정상 복귀 시 해제
    while True:
        t0 = time.time()
        fail = sweep_once(codes)
        backoff = min((backoff or 1.0) * 2, 10.0) if fail else 0.0
        with _LOCK:
            META['sweep_at'] = datetime.now(KST).strftime('%H:%M:%S')
            META['sweep_ms'] = int((time.time() - t0) * 1000)
            META['fail'] = fail
        target = max(effective_interval(interval), backoff)
        time.sleep(max(0.0, target - (time.time() - t0)))


def build_payload():
    with _LOCK:
        rows = []
        for s in STOCKS:
            q = SNAP.get(s['code'])
            if not q or not q['price']:
                continue
            shares = SHARES.get(s['code'], 0)
            rows.append({
                'code': s['code'], 'name': s['name'], 'sector': s['sector'],
                'price': q['price'], 'chg': q['chg'], 'trdval': q['trdval'],
                'mcap': q['price'] * shares,
            })
        meta = dict(META, total=len(STOCKS), quoted=len(rows))
    return json.dumps({'meta': meta, 'rows': rows}, ensure_ascii=False)


# ── 관심그룹 1·2 = 포트폴리오 자동 동기화 (10분 주기, 키워드 매칭이라 회차 변경에도 추종) ──
PF_JSON = os.path.join(ROOT, 'portfolio_data.json')
PF_GROUP_PATTERNS = [('트루밸류', '지속형'),          # 그룹1: 일반형/개방형/지속형
                     ('목표전환형', '성과모집형')]    # 그룹2: 목표전환형/성과모집형
PF_SYNC_SEC = 600


def _pf_codes(v):
    out = []

    def walk(x):
        if isinstance(x, dict):
            for k, vv in x.items():
                if k in ('code', '코드') and isinstance(vv, str) and vv.isdigit() and len(vv) == 6:
                    out.append(vv)
                else:
                    walk(vv)
        elif isinstance(x, list):
            for e in x:
                walk(e)
    walk(v)
    return out


def sync_wl_from_portfolio():
    """portfolio_data.json → 관심그룹 1·2 codes 갱신 (이름·그룹3 보존, 변경 시에만 저장)."""
    while True:
        try:
            pf = json.load(open(PF_JSON, encoding='utf-8'))
            with _LOCK:
                wl = load_wl()
                changed = False
                for gi, pats in enumerate(PF_GROUP_PATTERNS):
                    codes = []
                    for key, v in pf.items():
                        if any(p in key for p in pats):
                            codes += _pf_codes(v)
                    codes = list(dict.fromkeys(codes))
                    if not codes:
                        continue
                    # 수동 추가분(직전 auto에 없던 코드)은 보존, 포트 이탈 종목(auto였던 것)만 제거
                    prev_auto = set(wl[gi].get('auto') or [])
                    manual = [c for c in wl[gi]['codes'] if c not in prev_auto and c not in codes]
                    new_codes = codes + manual
                    if new_codes != wl[gi]['codes'] or codes != (wl[gi].get('auto') or []):
                        wl[gi]['codes'] = new_codes
                        wl[gi]['auto'] = codes
                        changed = True
                if changed:
                    save_wl(wl)
                    logging.info('관심그룹 포트 동기화: 1=%d종목, 2=%d종목',
                                 len(wl[0]['codes']), len(wl[1]['codes']))
        except Exception as e:
            logging.warning('포트 동기화 실패: %s', e)
        time.sleep(PF_SYNC_SEC)


def load_wl():
    try:
        w = json.load(open(WL_PATH, encoding='utf-8'))
        if isinstance(w, list) and len(w) == 3:
            return w
    except Exception:
        pass
    return [{'name': '관심종목 %d' % i, 'codes': []} for i in (1, 2, 3)]


def valid_wl(w):
    if not (isinstance(w, list) and len(w) == 3):
        return False
    for g in w:
        if not isinstance(g, dict):
            return False
        if not isinstance(g.get('name'), str) or not (0 < len(g['name']) <= 40):
            return False
        codes = g.get('codes')
        if not isinstance(codes, list) or len(codes) > 500:
            return False
        # KRX 신형 영숫자 코드·ETF 포함 (예: 0167A0)
        if not all(isinstance(c, str) and len(c) == 6 and c.isalnum() for c in codes):
            return False
    return True


def save_wl(w):
    tmp = WL_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(w, f, ensure_ascii=False)
    os.replace(tmp, WL_PATH)


def load_stars():
    """market.html DATA 차트 별표(시리즈명 리스트). 기기 공통, 서버 저장 (2026-07-20)."""
    try:
        s = json.load(open(STARS_PATH, encoding='utf-8'))
        if valid_stars(s):
            return s
    except Exception:
        pass
    return []


def valid_stars(s):
    return (isinstance(s, list) and len(s) <= 300
            and all(isinstance(x, str) and 0 < len(x) <= 80 for x in s))


def save_stars(s):
    tmp = STARS_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(s, f, ensure_ascii=False)
    os.replace(tmp, STARS_PATH)


def load_prefs():
    """AoE 페이지 화면 뷰 설정 KV (탭 선택·정렬 등). POST는 키 단위 병합 (2026-07-20)."""
    try:
        p = json.load(open(PREFS_PATH, encoding='utf-8'))
        if isinstance(p, dict):
            return p
    except Exception:
        pass
    return {}


def valid_prefs(p):
    return (isinstance(p, dict) and 0 < len(p) <= 100
            and all(isinstance(k, str) and 0 < len(k) <= 64 for k in p))


def save_prefs(p):
    tmp = PREFS_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(p, f, ensure_ascii=False)
    os.replace(tmp, PREFS_PATH)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype):
        data = body.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', ctype + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split('?', 1)[0]           # 쿼리스트링 무시
        if path.startswith('/data'):
            self._send(build_payload(), 'application/json')
        elif path.startswith('/wl'):
            with _LOCK:
                body = json.dumps(load_wl(), ensure_ascii=False)
            self._send(body, 'application/json')
        elif path.startswith('/stars'):
            with _LOCK:
                body = json.dumps(load_stars(), ensure_ascii=False)
            self._send(body, 'application/json')
        elif path.startswith('/prefs'):
            with _LOCK:
                body = json.dumps(load_prefs(), ensure_ascii=False)
            self._send(body, 'application/json')
        elif path in ('/', '/index.html'):
            html = open(os.path.join(BASE, 'index.html'), encoding='utf-8').read()
            self._send(html, 'text/html')
        else:
            self.send_error(404)

    def do_POST(self):
        path = self.path.split('?', 1)[0]
        if not (path.startswith('/wl') or path.startswith('/stars') or path.startswith('/prefs')):
            self.send_error(404)
            return
        try:
            n = int(self.headers.get('Content-Length') or 0)
            if not 0 < n <= 100_000:
                raise ValueError
            body = json.loads(self.rfile.read(n).decode('utf-8'))
            if path.startswith('/wl'):
                if not valid_wl(body):
                    raise ValueError
            elif path.startswith('/stars'):
                if not valid_stars(body):
                    raise ValueError
            elif not valid_prefs(body):
                raise ValueError
        except Exception:
            self.send_error(400)
            return
        with _LOCK:
            if path.startswith('/wl'):
                save_wl(body)
            elif path.startswith('/stars'):
                save_stars(body)
            else:                       # /prefs = 키 단위 병합 (다른 페이지 키 보존)
                merged = load_prefs()
                merged.update(body)
                save_prefs(merged)
        self._send('{"ok": 1}', 'application/json')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--interval', type=float, default=2.0, help='스윕 주기(초)')
    ap.add_argument('--port', type=int, default=8778)
    args = ap.parse_args()

    STOCKS.extend(load_universe())
    have = {s['code'] for s in STOCKS}
    STOCKS.extend(e for e in load_etfs() if e['code'] not in have)
    logging.info('유니버스 로드: %d종목 (ETF 포함)', len(STOCKS))
    fresh = seed_shares()
    missing = [s['code'] for s in STOCKS if s['code'] not in SHARES]
    if not fresh:
        threading.Thread(target=refresh_shares, daemon=True).start()
    elif missing:   # 오늘자 캐시라도 신규 추가 종목의 상장주식수는 즉시 보충
        threading.Thread(target=refresh_shares, args=(missing,), daemon=True).start()
    threading.Thread(target=poll_loop, args=(args.interval,), daemon=True).start()
    threading.Thread(target=sync_wl_from_portfolio, daemon=True).start()

    srv = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    logging.info('시세판: http://127.0.0.1:%d/  (스윕 %.1fs)', args.port, args.interval)
    srv.serve_forever()


if __name__ == '__main__':
    main()
