# -*- coding: utf-8 -*-
"""부티크 액티브 ETF 특이사항 텔레그램 알림 (Sisyphe-Bot, subscribers.json 브로드캐스트).

- 편입/편출/급변(etf_changes)이 있을 때만 발송 — 없으면 침묵.
- dedup: .boutique_alert_sent.json (키=날짜) — 재실행 중복 발송 방지.
- 테스트: python -m execution.boutique_etf.alert --test  (샘플 데이터로 즉시 발송)
"""
import json
import logging
import os
import sys

import requests

_EXEC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(_EXEC_DIR)
SUBSCRIBERS_FILE = os.path.join(REPO, 'subscribers.json')
STATE_FILE = os.path.join(REPO, '.boutique_alert_sent.json')
TOKEN_KEY = 'TELEGRAM_' + 'SISYPHE_BOT_TOKEN'

from .db import get_conn  # noqa: E402

logging.basicConfig(level=logging.INFO, format='[boutique-alert] %(message)s')


def _fmt_eok(v):
    """원 → 억원 표기. |v|>=1조 는 조 단위."""
    if v is None:
        return '-'
    eok = v / 1e8
    sign = '+' if eok > 0 else ('-' if eok < 0 else '')
    a = abs(eok)
    if a >= 10000:
        return '%s%.1f조' % (sign, a / 10000)
    if a >= 10:
        return '%s%d억' % (sign, round(a))
    return '%s%.1f억' % (sign, a)


def _fmt_w(v):
    return '-' if v is None else ('%.1f' % v)


def build_message(date, rows, test=False):
    """rows: [{etf, kind(in|out|spike), stock, w_prev, w_cur, trade_amt}] — |금액| 내림차순."""
    head = '[부티크 액티브 ETF] %s%s' % (date[5:].replace('-', '/'),
                                    ' (테스트)' if test else '')
    sec = {'in': [], 'out': [], 'spike': []}
    for r in sorted(rows, key=lambda x: -abs(x.get('trade_amt') or 0)):
        etf, stock = r['etf'], r['stock']
        amt = r.get('trade_amt')
        if r['kind'] == 'in':
            sec['in'].append('· %s — %s 신규 %s%% · 유입 %s'
                             % (etf, stock, _fmt_w(r.get('w_cur')), _fmt_eok(amt)))
        elif r['kind'] == 'out':
            sec['out'].append('· %s — %s %s%% → 0 · 유출 %s'
                              % (etf, stock, _fmt_w(r.get('w_prev')), _fmt_eok(amt)))
        else:
            sec['spike'].append('· %s — %s %s→%s%% · %s'
                                % (etf, stock, _fmt_w(r.get('w_prev')),
                                   _fmt_w(r.get('w_cur')), _fmt_eok(amt)))
    parts = [head]
    for key, title in (('in', '편입'), ('out', '편출'), ('spike', '급변')):
        if sec[key]:
            parts.append('')
            parts.append('<b><u>%s</u></b>' % title)
            parts.extend(sec[key])
    return '\n'.join(parts)


def _chunks(text, limit=3900):
    lines, buf, out = text.split('\n'), [], []
    n = 0
    for ln in lines:
        if n + len(ln) + 1 > limit and buf:
            out.append('\n'.join(buf))
            buf, n = [], 0
        buf.append(ln)
        n += len(ln) + 1
    if buf:
        out.append('\n'.join(buf))
    return out


def send(text):
    token = os.environ.get(TOKEN_KEY)
    if not token:
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(REPO, '.env'))
            token = os.environ.get(TOKEN_KEY)
        except ImportError:
            pass
    if not token:
        raise RuntimeError('%s 미설정' % TOKEN_KEY)
    try:
        subs = json.load(open(SUBSCRIBERS_FILE, encoding='utf-8'))
    except Exception as e:
        raise RuntimeError('subscribers.json 읽기 실패: %s' % e)
    ok = 0
    for chat_id in subs:
        for chunk in _chunks(text):
            r = requests.post(
                'https://api.telegram.org/bot%s/sendMessage' % token,
                json={'chat_id': chat_id, 'text': chunk, 'parse_mode': 'HTML',
                      'disable_web_page_preview': True}, timeout=15)
            if r.status_code == 200:
                ok += 1
            else:
                logging.error('send fail chat=%s status=%s body=%s',
                              chat_id, r.status_code, r.text[:200])
    return ok


def load_changes(conn, date):
    rows = []
    for r in conn.execute(
            'SELECT c.*, d.name etf_name FROM etf_changes c '
            'JOIN etf_daily d ON d.date=c.date AND d.etf_code=c.etf_code '
            'WHERE c.date=? AND c.drift=0', (date,)):
        rows.append({'etf': r['etf_name'], 'kind': r['kind'], 'stock': r['stock_name'],
                     'w_prev': r['w_prev'], 'w_cur': r['w_cur'],
                     'trade_amt': r['trade_amt']})
    return rows


SAMPLE = [
    {'etf': 'TIME 코스피액티브', 'kind': 'in', 'stock': '삼양식품',
     'w_cur': 2.1, 'w_prev': None, 'trade_amt': 7.5e9},
    {'etf': 'KoAct 배당성장액티브', 'kind': 'out', 'stock': '한화에어로스페이스',
     'w_prev': 1.4, 'w_cur': None, 'trade_amt': -1.4e9},
    {'etf': 'TRUSTON 주주가치액티브', 'kind': 'spike', 'stock': 'SK하이닉스',
     'w_prev': 15.8, 'w_cur': 17.3, 'trade_amt': 1.9e9},
    {'etf': 'DS 코스닥액티브', 'kind': 'spike', 'stock': '테스',
     'w_prev': 8.1, 'w_cur': 6.9, 'trade_amt': -2.8e9},
]


def main():
    if '--test' in sys.argv:
        from datetime import datetime
        msg = build_message(datetime.now().strftime('%Y-%m-%d'), SAMPLE, test=True)
        print(msg)
        if '--dry' in sys.argv:  # 미리보기만 — 발송 안 함
            logging.info('dry-run (미발송)')
            return 0
        n = send(msg)
        logging.info('테스트 발송 %d건', n)
        return 0
    conn = get_conn()
    row = conn.execute("SELECT MAX(date) d FROM collection_log WHERE status='ok'").fetchone()
    date = row['d'] if row else None
    if not date:
        logging.info('수집 데이터 없음 — 스킵')
        return 0
    try:
        state = json.load(open(STATE_FILE, encoding='utf-8'))
    except Exception:
        state = {}
    if state.get('sent') == date:
        logging.info('%s 이미 발송 — 스킵', date)
        return 0
    rows = load_changes(conn, date)
    if not rows:
        logging.info('%s 특이사항 없음 — 무발송', date)
        return 0
    n = send(build_message(date, rows))
    if n:
        json.dump({'sent': date}, open(STATE_FILE, 'w', encoding='utf-8'))
    logging.info('%s 발송 %d건 (항목 %d)', date, n, len(rows))
    return 0


if __name__ == '__main__':
    sys.exit(main())
