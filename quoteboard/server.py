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
MASTER_FILE = os.path.join(ROOT, 'kis_universe_master.json')
SHARES_CACHE = os.path.join(BASE, 'shares_cache.json')
WL_PATH = os.path.join(BASE, 'watchlists.json')     # 관심종목 그룹 (기기 공통, 서버 저장)

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
            if not code.isdigit() or code in seen:
                continue
            seen.add(code)
            rows.append({'code': code,
                         'name': (r.get('기업명') or '').strip(),
                         'sector': (r.get('섹터') or '').strip() or '기타'})
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


def refresh_shares():
    """KIS inquire-price로 전 종목 상장주식수 갱신 (매일 1회, 백그라운드)."""
    today = datetime.now(KST).strftime('%Y-%m-%d')
    got, fail = {}, 0
    for s in STOCKS:
        try:
            j = kis_get(PRICE_PATH, tr_id=PRICE_TRID,
                        params={'FID_COND_MRKT_DIV_CODE': 'J',
                                'FID_INPUT_ISCD': s['code']})
            n = _to_int((j.get('output') or {}).get('lstn_stcn'))
            if n:
                got[s['code']] = n
        except Exception:
            fail += 1
    if got:
        with _LOCK:
            SHARES.update(got)
            META['shares_date'] = today
        json.dump({'date': today, 'shares': got},
                  open(SHARES_CACHE, 'w', encoding='utf-8'))
    logging.info('상장주식수 갱신 완료 %d/%d (실패 %d)', len(got), len(STOCKS), fail)


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
        if not all(isinstance(c, str) and c.isdigit() and len(c) == 6 for c in codes):
            return False
    return True


def save_wl(w):
    tmp = WL_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(w, f, ensure_ascii=False)
    os.replace(tmp, WL_PATH)


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
        if self.path.startswith('/data'):
            self._send(build_payload(), 'application/json')
        elif self.path.startswith('/wl'):
            with _LOCK:
                body = json.dumps(load_wl(), ensure_ascii=False)
            self._send(body, 'application/json')
        elif self.path in ('/', '/index.html'):
            html = open(os.path.join(BASE, 'index.html'), encoding='utf-8').read()
            self._send(html, 'text/html')
        else:
            self.send_error(404)

    def do_POST(self):
        if not self.path.startswith('/wl'):
            self.send_error(404)
            return
        try:
            n = int(self.headers.get('Content-Length') or 0)
            if not 0 < n <= 100_000:
                raise ValueError
            w = json.loads(self.rfile.read(n).decode('utf-8'))
            if not valid_wl(w):
                raise ValueError
        except Exception:
            self.send_error(400)
            return
        with _LOCK:
            save_wl(w)
        self._send('{"ok": 1}', 'application/json')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--interval', type=float, default=1.0, help='스윕 주기(초)')
    ap.add_argument('--port', type=int, default=8778)
    args = ap.parse_args()

    STOCKS.extend(load_universe())
    logging.info('유니버스 로드: %d종목', len(STOCKS))
    fresh = seed_shares()
    if not fresh:
        threading.Thread(target=refresh_shares, daemon=True).start()
    threading.Thread(target=poll_loop, args=(args.interval,), daemon=True).start()

    srv = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    logging.info('시세판: http://127.0.0.1:%d/  (스윕 %.1fs)', args.port, args.interval)
    srv.serve_forever()


if __name__ == '__main__':
    main()
