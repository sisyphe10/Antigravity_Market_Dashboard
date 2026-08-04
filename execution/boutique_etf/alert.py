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
        return '%s%.1f조원' % (sign, a / 10000)
    if a >= 10:
        return '%s%d억원' % (sign, round(a))
    return '%s%.1f억원' % (sign, a)


def _fmt_w(v):
    return '-' if v is None else ('%.1f' % v)


WEEKDAY = '월화수목금토일'
BULLET1 = '•'  # 1단계(브랜드) — 노션식 점 크기
BULLET2 = '◦'  # 2단계(ETF·종목) — 속 빈 점
# ★C안 확정(2026-08-04): 텔레그램 비례폰트에서 ◦ 가 • 보다 넓게 잡혀 글자 시작 위치가 어긋난다.
#   1단계만 불릿 뒤 공백 2칸을 줘서 두 단계의 첫 글자 위치를 맞춘다.
GAP1 = '  '
GAP2 = ' '


def _head(date, test=False, extra=False):
    """제목 = <b><u>8.4(화) [액티브 ETF 변동 현황]</u></b>  (사용자 확정 2026-08-04, 볼드+밑줄)"""
    from datetime import datetime
    dt = datetime.strptime(date, '%Y-%m-%d')
    suffix = ' (테스트)' if test else (' (추가)' if extra else '')
    return '<b><u>%d.%d(%s) [액티브 ETF 변동 현황]</u></b>%s' % (
        dt.month, dt.day, WEEKDAY[dt.weekday()], suffix)


def _cells(r):
    """공통 뒷부분: 구분 | 비중 | 유입·유출 | 금액"""
    kind = r['kind']
    if kind == 'in':
        gubun, w = 'NEW', '+%s%%' % _fmt_w(r.get('w_cur'))       # 신규 편입
    elif kind == 'out':
        gubun, w = 'X', '-%s%%' % _fmt_w(r.get('w_prev'))        # 편출
    else:
        dw = (r.get('w_cur') or 0) - (r.get('w_prev') or 0)
        gubun = '+' if dw > 0 else '-'                            # 비중 급증 / 급감
        w = '%s→%s%%' % (_fmt_w(r.get('w_prev')), _fmt_w(r.get('w_cur')))
    amt = r.get('trade_amt') or 0
    flow = '유입' if amt > 0 else ('유출' if amt < 0 else '-')
    return '<b><u>%s</u></b> | %s | %s | %s | <b><u>%s</u></b>' % (
        r['stock'], gubun, w, flow, _fmt_eok(r.get('trade_amt')))


def _brand(etf):
    """'TIME 코스닥액티브' → ('TIME', '코스닥액티브')"""
    parts = (etf or '').split(' ', 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (etf, etf)


def _amt(r):
    return r.get('trade_amt') or 0


def build_message(date, rows, test=False, layout='tree', extra=False):
    """rows: [{etf, kind(in|out|spike), stock, w_prev, w_cur, trade_amt}].

    정렬 = 금액(마지막 칼럼) 부호 내림차순 — 유입 큰 순 → 유출 큰 순 (사용자 확정 2026-08-04).
    layout='tree'  운용사 브랜드로 묶고 하위 불릿 (기본)
    layout='flat'  단일 목록
    """
    ordered = sorted(rows, key=lambda x: -_amt(x))
    if layout == 'flat':
        body = ['%s%s%s | %s' % (BULLET1, GAP1, r['etf'], _cells(r)) for r in ordered]
    else:
        groups = {}
        for r in ordered:
            groups.setdefault(_brand(r['etf'])[0], []).append(r)
        body = []
        for brand in sorted(groups, key=lambda b: -max(_amt(r) for r in groups[b])):
            body.append('%s%s<b>%s</b>' % (BULLET1, GAP1, brand))
            for r in groups[brand]:
                body.append('   %s%s%s | %s' % (BULLET2, GAP2, _brand(r['etf'])[1], _cells(r)))
    return '\n'.join([_head(date, test, extra), ''] + body)


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


def load_changes(conn, date, unsent_only=True):
    """미발송 변경만 반환 — 늦게 올라온 운용사는 다음 실행에서 '추가'로 나간다."""
    sql = ('SELECT c.*, d.name etf_name FROM etf_changes c '
           'JOIN etf_daily d ON d.date=c.date AND d.etf_code=c.etf_code ')
    if unsent_only:
        sql += ('LEFT JOIN alert_sent s ON s.date=c.date AND s.etf_code=c.etf_code '
                'AND s.stock_code=c.stock_code AND s.kind=c.kind ')
    sql += 'WHERE c.date=? AND c.drift=0'
    if unsent_only:
        sql += ' AND s.date IS NULL'
    rows = []
    for r in conn.execute(sql, (date,)):
        rows.append({'etf': r['etf_name'], 'kind': r['kind'], 'stock': r['stock_name'],
                     'w_prev': r['w_prev'], 'w_cur': r['w_cur'],
                     'trade_amt': r['trade_amt'],
                     'etf_code': r['etf_code'], 'stock_code': r['stock_code']})
    return rows


def mark_sent(conn, date, rows):
    ts = __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.executemany(
        'INSERT OR REPLACE INTO alert_sent VALUES (?,?,?,?,?)',
        [(date, r['etf_code'], r['stock_code'], r['kind'], ts) for r in rows])
    conn.commit()


SAMPLE = [
    {'etf': 'TIME 코스닥액티브', 'kind': 'in', 'stock': '삼양식품',
     'w_cur': 2.1, 'w_prev': None, 'trade_amt': 7.5e9},
    {'etf': 'TIME 코스피액티브', 'kind': 'spike', 'stock': '삼성전자',
     'w_prev': 23.9, 'w_cur': 25.2, 'trade_amt': 4.1e9},
    {'etf': 'TIME K바이오액티브', 'kind': 'out', 'stock': '알테오젠',
     'w_prev': 3.2, 'w_cur': None, 'trade_amt': -0.9e9},
    {'etf': 'KoAct 배당성장액티브', 'kind': 'out', 'stock': '한화에어로스페이스',
     'w_prev': 1.4, 'w_cur': None, 'trade_amt': -1.4e9},
    {'etf': 'KoAct 코스닥액티브', 'kind': 'in', 'stock': '파마리서치',
     'w_cur': 1.1, 'w_prev': None, 'trade_amt': 2.3e9},
    {'etf': 'TRUSTON 주주가치액티브', 'kind': 'spike', 'stock': 'SK하이닉스',
     'w_prev': 15.8, 'w_cur': 17.3, 'trade_amt': 1.9e9},
    {'etf': 'DS 코스닥액티브', 'kind': 'spike', 'stock': '테스',
     'w_prev': 8.1, 'w_cur': 6.9, 'trade_amt': -2.8e9},
]


def main():
    if '--test' in sys.argv:
        from datetime import datetime
        layout = 'flat' if '--flat' in sys.argv else 'tree'
        msg = build_message(datetime.now().strftime('%Y-%m-%d'), SAMPLE,
                            test=True, layout=layout)
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
    rows = load_changes(conn, date)
    if not rows:
        logging.info('%s 신규 특이사항 없음 — 무발송', date)
        return 0
    already = conn.execute(
        'SELECT COUNT(*) c FROM alert_sent WHERE date=?', (date,)).fetchone()['c']
    n = send(build_message(date, rows, extra=bool(already)))
    if n:
        mark_sent(conn, date, rows)
    logging.info('%s 발송 %d건 (항목 %d%s)', date, n, len(rows),
                 ', 추가분' if already else '')
    return 0


if __name__ == '__main__':
    sys.exit(main())
