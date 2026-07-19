# -*- coding: utf-8 -*-
"""미국(+홍콩) ETF NAV·AUM 일별 수집 + 한국 비중 변동 텔레그램 (Sisyphe-Bot).

맥미니 launchd us-etf-collect.timer(화~토 08:30 KST — 미국 마감 후·한국장 개장 전)가 실행한다.
- yfinance: NAV(navPrice)·AUM(totalAssets)·종가·보수 + USDKRW 환율
- 삼성전자·SK하이닉스 보유비중: funds_data.top_holdings 자동 (미검출 시 정적 폴백)
- us_etf_history.csv 에 미국 세션 날짜 기준 append (동일 날짜 재실행 = idempotent 스킵)
- 수집 후 한국 비중 변동 4지표를 Sisyphe-Bot 으로 발송 (.us_etf_alert_sent.json dedup)

수동:
  python3 execution/etf_collector/collect_us_etf.py            # 수집+발송
  python3 execution/etf_collector/collect_us_etf.py --no-send  # 수집만
  python3 execution/etf_collector/collect_us_etf.py --backfill-close  # YTD 종가 백필(1회)
"""
import csv
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from us_etf_config import US_ETFS, FALLBACK_WEIGHTS, HK_SINGLE, HISTORY_CSV, KR_SH_RATIO  # noqa: E402

CSV_PATH = os.path.join(REPO, HISTORY_CSV)
STATE_FILE = os.path.join(REPO, '.us_etf_alert_sent.json')
SUBSCRIBERS_FILE = os.path.join(REPO, 'subscribers.json')
ENV_FILE = os.path.join(REPO, '.env')
TOKEN_KEY = 'TELEGRAM_' + 'SISYPHE_BOT_TOKEN'  # Sisyphe-Bot (etf_active_alert 와 동일)

FIELDS = ['date', 'ticker', 'close', 'nav', 'aum_usd', 'currency', 'expense',
          'fx_usdkrw', 'w_samsung', 'w_hynix']

SAMSUNG_KEYS = ('005930', '005935')  # 보통주 + 우선주
HYNIX_KEYS = ('000660',)


def us_session_date():
    """미국 세션 날짜 (09:00 KST 실행 = 직전 미국 장 마감일). 주말이면 금요일로 스냅."""
    et = datetime.now(ZoneInfo('America/New_York')) if ZoneInfo else datetime.utcnow() - timedelta(hours=4)
    d = et.date()
    if d.weekday() == 5:
        d -= timedelta(days=1)
    elif d.weekday() == 6:
        d -= timedelta(days=2)
    return d.isoformat()


def _retry(fn, tries=2, default=None):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            if i == tries - 1:
                logging.warning('fetch 실패(%d회): %s', tries, e)
    return default


def fetch_fx():
    import yfinance as yf
    info = _retry(lambda: yf.Ticker('KRW=X').info, default={}) or {}
    fx = info.get('regularMarketPrice') or info.get('previousClose')
    if not fx:
        raise RuntimeError('USDKRW 환율 조회 실패')
    return float(fx)


def fetch_holdings_weights(ticker):
    """top holdings 에서 (삼성전자, SK하이닉스) 비중 추출. 미검출 항목은 폴백 사용."""
    import yfinance as yf
    fb = FALLBACK_WEIGHTS.get(ticker, (0.0, 0.0))
    th = _retry(lambda: yf.Ticker(ticker).funds_data.top_holdings)
    if th is None or getattr(th, 'empty', True):
        return fb
    w_s = w_h = 0.0
    try:
        for sym, row in th.iterrows():
            pct = float(row.get('Holding Percent', 0) or 0)
            key = str(sym)
            if key.startswith(SAMSUNG_KEYS):
                w_s += pct
            elif key.startswith(HYNIX_KEYS):
                w_h += pct
    except Exception as e:
        logging.warning('%s holdings 파싱 실패: %s', ticker, e)
        return fb
    # top10 컷오프로 안 잡힌 쪽만 폴백 (실측 우선)
    return (w_s or fb[0], w_h or fb[1])


def collect(fx):
    """전 종목 조회 → row dict 리스트."""
    import yfinance as yf
    rows = []
    for spec in US_ETFS:
        tk = spec['ticker']
        info = _retry(lambda t=tk: yf.Ticker(t).info, default={}) or {}
        aum = info.get('totalAssets')  # .HK 포함 USD (2026-07-19 뉴스 교차검증)
        close = info.get('previousClose')
        is_hk = tk in HK_SINGLE
        nav = None if is_hk else info.get('navPrice')  # HK 는 yfinance NAV stale
        if aum is None and close is None:
            logging.warning('%s: 데이터 없음 — 스킵', tk)
            continue
        if is_hk:
            w_s = 2.0 if HK_SINGLE[tk] == 'samsung' else 0.0
            w_h = 2.0 if HK_SINGLE[tk] == 'hynix' else 0.0
        elif spec['kr']:
            w_s, w_h = fetch_holdings_weights(tk)
        else:
            w_s = w_h = 0.0
        rows.append({
            'ticker': tk, 'close': close, 'nav': nav, 'aum_usd': aum,
            'currency': info.get('currency') or ('HKD' if is_hk else 'USD'),
            'expense': info.get('netExpenseRatio'),
            'fx_usdkrw': round(fx, 2), 'w_samsung': round(w_s, 6), 'w_hynix': round(w_h, 6),
        })
    return rows


def load_history():
    if not os.path.exists(CSV_PATH):
        return []
    with open(CSV_PATH, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def append_rows(day, rows):
    exists = os.path.exists(CSV_PATH)
    with open(CSV_PATH, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow({'date': day, **r})


# ── 한국 비중 변동 지표 (대시보드·텔레그램 단일 출처) ──────────────────────

def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def kr_metrics(rows):
    """하이라이트 4지표 (단위: 억원). rows = 특정 날짜의 row 리스트."""
    spec_by_tk = {s['ticker']: s for s in US_ETFS}
    total_aum = invested = samsung = hynix = 0.0
    fx = _f(rows[0].get('fx_usdkrw'), 1400.0) if rows else 1400.0
    dram_w = None
    for r in rows:
        if r['ticker'] == 'DRAM':
            dram_w = _f(r.get('w_samsung')) + _f(r.get('w_hynix'))
    for r in rows:
        spec = spec_by_tk.get(r['ticker'])
        if not spec or not spec['kr']:
            continue
        aum = _f(r.get('aum_usd'))
        total_aum += aum
        kw = spec['kr_weight']
        sh = _f(r.get('w_samsung')) + _f(r.get('w_hynix'))
        if kw == 'auto':
            w = sh
            if r['ticker'] == 'RAM':
                w = 2.0 * (dram_w if dram_w is not None else w)
            invested += aum * w
        elif kw == 'idx':
            invested += aum * min(1.0, sh / KR_SH_RATIO)
        elif kw == 'lev2':
            invested += aum * 2.0
        else:
            invested += aum * float(kw)
        mult = 2.0 if r['ticker'] == 'RAM' else 1.0
        samsung += aum * _f(r.get('w_samsung')) * mult
        hynix += aum * _f(r.get('w_hynix')) * mult
    to_eok = fx / 1e8  # USD → 억원
    return {
        'fx': fx,
        'total_aum': total_aum * to_eok,
        'invested': invested * to_eok,
        'samsung': samsung * to_eok,
        'hynix': hynix * to_eok,
    }


def fmt_krw(eok):
    """억원 float → 'N조 N,NNN억원' (음수 지원)."""
    sign = '-' if eok < 0 else ''
    v = abs(int(round(eok)))
    jo, rem = divmod(v, 10000)
    if jo and rem:
        return f'{sign}{jo:,}조 {rem:,}억원'
    if jo:
        return f'{sign}{jo:,}조원'
    return f'{sign}{rem:,}억원'


def build_message(day, cur, prev=None):
    lines = [f'\U0001F1FA\U0001F1F8 <b>미국 ETF 한국 비중 변동</b> ({day} 종가)', '']
    items = [('한국 노출 ETF 총 AUM', 'total_aum'), ('한국 실투자 금액', 'invested'),
             ('삼성전자 노출액', 'samsung'), ('SK하이닉스 노출액', 'hynix')]
    for label, key in items:
        v = cur[key]
        if prev and prev.get(key):
            d = v - prev[key]
            pct = d / prev[key] * 100 if prev[key] else 0.0
            sign = '+' if d >= 0 else ''
            lines.append(f'{label}: <b>{fmt_krw(v)}</b> ({sign}{fmt_krw(d)}, {sign}{pct:.1f}%)')
        else:
            lines.append(f'{label}: <b>{fmt_krw(v)}</b>')
    if not prev:
        lines.append('')
        lines.append('<i>※ 첫 수집 — 변동은 다음 수집부터 표시</i>')
    lines.append('')
    fx_line = f'USDKRW {cur["fx"]:,.0f}'
    if prev and prev.get('fx'):
        d = cur['fx'] - prev['fx']
        sign = '+' if d >= 0 else ''
        fx_line += f' ({sign}{d:,.0f}원, {sign}{d / prev["fx"] * 100:.1f}%)'
    lines.append(f'<i>{fx_line}</i>')
    return '\n'.join(lines)


# ── 텔레그램 (etf_active_alert 패턴) ──────────────────────────────────────

def _load_token():
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE)
    except Exception:
        pass
    tok = os.getenv(TOKEN_KEY)
    if tok:
        return tok.strip().strip('"').strip("'")
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding='utf-8') as f:
            for ln in f:
                s = ln.strip()
                if s.startswith(TOKEN_KEY + '='):
                    return s.split('=', 1)[1].strip().strip('"').strip("'")
    return None


def send_telegram(day, msg):
    last = None
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding='utf-8') as f:
                last = json.load(f).get('last_sent_date')
        except Exception:
            pass
    if last == day:
        logging.info('이미 발송한 날짜(%s) — 무발송', day)
        return
    token = _load_token()
    if not token:
        logging.warning('텔레그램 토큰 없음 — 발송 스킵')
        return
    subs = []
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE, encoding='utf-8') as f:
            subs = list(json.load(f))
    if not subs:
        logging.warning('구독자 없음 — 발송 스킵')
        return
    import requests
    ok_any = False
    for chat_id in subs:
        r = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat_id, 'text': msg, 'parse_mode': 'HTML',
                  'disable_web_page_preview': True},
            timeout=15,
        )
        ok = r.ok and r.json().get('ok')
        ok_any = ok_any or bool(ok)
        logging.info('send chat=%s ok=%s', chat_id, ok)
    if ok_any:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'last_sent_date': day}, f)


# ── 백필 (YTD 종가만, 1회용) ──────────────────────────────────────────────

def backfill_close(start='2026-01-01'):
    """종가만 YTD 백필 — AUM·NAV·비중은 공란 (yfinance 한계, 수집 시작일부터 적재)."""
    import yfinance as yf
    hist = load_history()
    have = {(r['date'], r['ticker']) for r in hist}
    tickers = [s['ticker'] for s in US_ETFS]
    data = yf.download(tickers, start=start, auto_adjust=False, progress=False)['Close']
    added = 0
    rows_by_day = {}
    for day, ser in data.iterrows():
        d = day.strftime('%Y-%m-%d')
        for tk in tickers:
            v = ser.get(tk)
            if v is None or v != v:  # NaN
                continue
            if (d, tk) in have:
                continue
            rows_by_day.setdefault(d, []).append({
                'ticker': tk, 'close': round(float(v), 4), 'nav': None, 'aum_usd': None,
                'currency': 'HKD' if tk in HK_SINGLE else 'USD', 'expense': None,
                'fx_usdkrw': None, 'w_samsung': None, 'w_hynix': None,
            })
            added += 1
    for d in sorted(rows_by_day):
        append_rows(d, rows_by_day[d])
    logging.info('백필 완료: %d rows', added)


def main():
    if '--backfill-close' in sys.argv:
        backfill_close()
        return
    day = us_session_date()
    hist = load_history()
    todays = [r for r in hist if r['date'] == day and r.get('aum_usd')]
    if todays:
        # 이미 수집된 날 — 수집은 스킵하되 발송은 계속 (dedup 이 중복 발송을 막는다)
        logging.info('오늘(%s) 이미 수집됨 — 수집 스킵, 발송 단계 진행', day)
        rows_dated = todays
    else:
        fx = fetch_fx()
        rows = collect(fx)
        if len(rows) < len(US_ETFS) * 0.7:
            raise RuntimeError(f'수집 성공 {len(rows)}/{len(US_ETFS)} — 부분 실패로 중단')
        append_rows(day, rows)
        logging.info('%s 수집 완료: %d종', day, len(rows))
        rows_dated = [{'date': day, **r} for r in rows]

    cur = kr_metrics(rows_dated)
    prev_days = sorted({r['date'] for r in hist if r.get('aum_usd') and r['date'] != day})
    prev = kr_metrics([r for r in hist if r['date'] == prev_days[-1]]) if prev_days else None
    msg = build_message(day, cur, prev)
    plain = msg.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')
    try:
        print(plain)
    except UnicodeEncodeError:  # 콘솔이 cp949 등일 때 (수동 실행 방어)
        print(plain.encode('ascii', 'ignore').decode())
    if '--no-send' not in sys.argv:
        send_telegram(day, msg)


if __name__ == '__main__':
    main()
