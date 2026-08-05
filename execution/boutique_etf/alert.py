# -*- coding: utf-8 -*-
"""부티크 액티브 ETF 특이사항 텔레그램 알림 (Sisyphe-Bot, subscribers.json 브로드캐스트).

- 편입/편출/급변(etf_changes)이 있을 때만 발송 — 없으면 침묵.
- dedup: .boutique_alert_sent.json (키=날짜) — 재실행 중복 발송 방지.
- 테스트: python -m execution.boutique_etf.alert --test  (샘플 데이터로 즉시 발송)
"""
import html
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
MAX_BACKLOG_DAYS = 3   # 전송 장애로 밀린 날짜를 몇 일치까지 따라잡을지

# ── 알림 필터 (사용자 확정 2026-08-04) ───────────────────────────
#   신규(NEW)·편출(X)은 무조건 알린다. 급변(+/-)만 아래 둘 중 하나를 만족해야 한다.
#     ① 매매추정액 >= MIN_AMT
#     ② 매매추정액이 그 종목 시가총액의 MIN_MCAP_PCT% 이상 (소형주 소액 매매를 살린다)
#   ★②는 ETF·채권형 보유분에 적용하지 않는다. 이들은 현금성 파킹이라 자기 시총 대비
#     비율이 구조적으로 크다(실측 최대 58.6% — 통안채·단기채 ETF). 걸어두면 그것만 올라온다.
MIN_AMT = float(os.environ.get('BOUTIQUE_ALERT_MIN_AMT') or 5e9)          # 50억원
MIN_MCAP_PCT = float(os.environ.get('BOUTIQUE_ALERT_MIN_PCT') or 0.1)     # 시총의 0.1%

# ── 국내 종목만 알림 (사용자 확정 2026-08-05) ─────────────────
#   stock_code 접두사가 정규화 결과다: KRX:=국내 상장, US:/HK:/RAW:(TT·CH·JP·선물지수)=해외.
#   ★수집·DB·뷰어는 전량 그대로 두고 **알림에서만** 민다. env=0 으로 즉시 원복.
DOMESTIC_ONLY = (os.environ.get('BOUTIQUE_ALERT_DOMESTIC_ONLY') or '1') != '0'


def _is_domestic(r):
    return str(r.get('stock_code') or '').startswith('KRX:')
FUND_KW = ('KODEX', 'TIGER', 'KBSTAR', 'ACE ', 'RISE', 'KIWOOM', 'SOL ', 'PLUS ',
           'TIME ', 'KoAct', 'TRUSTON', 'ARIRANG', 'HANARO', 'ETF', 'ETN',
           '통안채', '단기채', '회사채', '금융채', '국고채', '종합채', 'MMF')


def _is_fund_like(name):
    up = (name or '').upper()
    return any(k.upper() in up for k in FUND_KW)


def passes_filter(r):
    """알림 대상 여부. 필터는 알림에만 적용하고 DB·뷰어에는 전량 남긴다."""
    if DOMESTIC_ONLY and not _is_domestic(r):
        return False
    if r['kind'] in ('in', 'out'):
        return True
    amt = abs(r.get('trade_amt') or 0)
    if amt >= MIN_AMT:
        return True
    m = r.get('mcap') or 0
    if m > 0 and not _is_fund_like(r.get('stock')) and amt / m * 100 >= MIN_MCAP_PCT:
        return True
    return False

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


def _head(date, test=False, extra=False, page=None, pages=None):
    """제목 = <b><u>8.4(화) [액티브 ETF 변동 현황]</u></b>  (사용자 확정 2026-08-04, 볼드+밑줄)

    괄호 꼬리표: 테스트 / 추가(늦게 올라온 운용사) / 2·3쪽(길어서 나뉜 경우)
    """
    from datetime import datetime
    dt = datetime.strptime(date, '%Y-%m-%d')
    tags = []
    if test:
        tags.append('테스트')
    if extra:
        tags.append('추가')
    if pages and pages > 1:
        tags.append('%d/%d' % (page, pages))
    suffix = ' (%s)' % ' '.join(tags) if tags else ''
    return '<b><u>%d.%d(%s) [액티브 ETF 변동 현황]</u></b>%s' % (
        dt.month, dt.day, WEEKDAY[dt.weekday()], suffix)


def _esc(s):
    """텔레그램 HTML 파스모드 — 데이터의 & < > 는 반드시 이스케이프.
    ★ETF·종목명에 '&' 가 실재한다(KoAct 글로벌AI&로봇, 반도체&2차전지 등).
      그대로 넣으면 그 메시지 전체가 400 으로 실패한다."""
    return html.escape(str(s or ''), quote=False)


def _cells(r):
    """공통 뒷부분: 구분 | 비중 | 금액  (사용자 확정 2026-08-05)

    ★유입/유출 칼럼 제거 — 마지막 금액의 부호가 이미 같은 정보를 담는다.
    ★구분은 New / 증가(+) / 감소(-) / X — 기호만 두면 눈에 안 띈다는 지적으로
      단어를 앞에 붙였다(2026-08-05). 그래서 특수 마이너스 기호는 불필요.
    ★비중 화살표 좌우에 공백: 29.7 → 25.1%
    """
    kind = r['kind']
    if kind == 'in':
        gubun, w = 'New', '+%s%%' % _fmt_w(r.get('w_cur'))       # 신규 편입
    elif kind == 'out':
        gubun, w = 'X', '-%s%%' % _fmt_w(r.get('w_prev'))        # 편출
    else:
        dw = (r.get('w_cur') or 0) - (r.get('w_prev') or 0)
        gubun = '증가(+)' if dw > 0 else '감소(-)'                        # 비중 급증 / 급감
        w = '%s → %s%%' % (_fmt_w(r.get('w_prev')), _fmt_w(r.get('w_cur')))
    return '<b><u>%s</u></b> | %s | %s | <b><u>%s</u></b>' % (
        _esc(r['stock']), gubun, w, _fmt_eok(r.get('trade_amt')))


def _brand(etf):
    """'TIME 코스닥액티브' → ('TIME', '코스닥액티브')"""
    parts = (etf or '').split(' ', 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (etf, etf)


def _amt(r):
    return r.get('trade_amt') or 0


def build_message(date, rows, test=False, layout='tree', extra=False,
                  page=None, pages=None):
    """rows: [{etf, kind(in|out|spike), stock, w_prev, w_cur, trade_amt}].

    정렬 = 금액(마지막 칼럼) 부호 내림차순 — 유입 큰 순 → 유출 큰 순 (사용자 확정 2026-08-04).
    layout='tree'  운용사 브랜드로 묶고 하위 불릿 (기본)
    layout='flat'  단일 목록
    """
    ordered = sorted(rows, key=lambda x: -_amt(x))
    if layout == 'flat':
        body = ['%s%s%s | %s' % (BULLET1, GAP1, _esc(r['etf']), _cells(r)) for r in ordered]
    else:
        groups = {}
        for r in ordered:
            groups.setdefault(_brand(r['etf'])[0], []).append(r)
        body = []
        for brand in sorted(groups, key=lambda b: -max(_amt(r) for r in groups[b])):
            if body:
                body.append('')   # 운용사 블록 사이 한 줄 띄우기 (사용자 확정 2026-08-05)
            body.append('%s%s<b>%s</b>' % (BULLET1, GAP1, _esc(brand)))
            for r in groups[brand]:
                body.append('   %s%s%s | %s'
                            % (BULLET2, GAP2, _esc(_brand(r['etf'])[1]), _cells(r)))
    return '\n'.join([_head(date, test, extra, page, pages), ''] + body)


def build_pages(date, rows, test=False, layout='tree', extra=False, limit=3500):
    """행을 페이지로 쪼개 [(그 페이지의 행들, 메시지 텍스트)] 반환.

    ★문자열을 잘라 보내면 어느 조각이 실패했는지 알 수 없어, 한 조각만 실패해도
      전체를 '발송됨' 으로 표시해 항목이 영영 유실된다. 그래서 **행 단위로 페이지를
      만들고 페이지별로 발송·기록**한다. 브랜드 헤더는 페이지마다 다시 붙는다.
    """
    ordered = sorted(rows, key=lambda x: -_amt(x))
    pages, cur = [], []
    for r in ordered:
        trial = cur + [r]
        if cur and len(build_message(date, trial, test, layout, extra)) > limit:
            pages.append(cur)
            cur = [r]
        else:
            cur = trial
    if cur:
        pages.append(cur)
    n = len(pages)
    return [(p, build_message(date, p, test, layout, extra, i + 1, n))
            for i, p in enumerate(pages)]


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
        try:
            r = requests.post(
                'https://api.telegram.org/bot%s/sendMessage' % token,
                json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML',
                      'disable_web_page_preview': True}, timeout=15)
        except Exception as e:
            logging.error('send error chat=%s: %s', chat_id, e)
            continue
        if r.status_code == 200:
            ok += 1
        else:
            logging.error('send fail chat=%s status=%s body=%s',
                          chat_id, r.status_code, r.text[:200])
    return ok


def load_changes(conn, date, unsent_only=True):
    """미발송 변경만 반환 — 늦게 올라온 운용사는 다음 실행에서 '추가'로 나간다."""
    sql = ('SELECT c.*, d.name etf_name, k.mcap_krw mcap FROM etf_changes c '
           'JOIN etf_daily d ON d.date=c.date AND d.etf_code=c.etf_code '
           'LEFT JOIN etf_constituents k ON k.date=c.date AND k.etf_code=c.etf_code '
           'AND k.stock_code=c.stock_code ')
    if unsent_only:
        sql += ('LEFT JOIN alert_sent s ON s.date=c.date AND s.etf_code=c.etf_code '
                'AND s.stock_code=c.stock_code AND s.kind=c.kind ')
    sql += 'WHERE c.date=? AND c.drift=0'
    if unsent_only:
        sql += ' AND s.date IS NULL'
    rows = []
    for r in conn.execute(sql, (date,)):
        row = {'etf': r['etf_name'], 'kind': r['kind'], 'stock': r['stock_name'],
               'w_prev': r['w_prev'], 'w_cur': r['w_cur'],
               'trade_amt': r['trade_amt'], 'mcap': r['mcap'],
               'etf_code': r['etf_code'], 'stock_code': r['stock_code']}
        if passes_filter(row):
            rows.append(row)
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
    # ★최신 날짜만 보면, 전송 장애로 못 보낸 전날 변경이 영영 방치된다.
    #   미발송 변경이 남은 날짜를 오래된 순으로 모두 처리한다(최근 MAX_BACKLOG_DAYS 일).
    dates = [r['d'] for r in conn.execute(
        'SELECT DISTINCT c.date d FROM etf_changes c '
        'LEFT JOIN alert_sent s ON s.date=c.date AND s.etf_code=c.etf_code '
        'AND s.stock_code=c.stock_code AND s.kind=c.kind '
        'WHERE c.drift=0 AND s.date IS NULL ORDER BY c.date')]
    dates = dates[-MAX_BACKLOG_DAYS:]
    if not dates:
        logging.info('신규 특이사항 없음 — 무발송')
        return 0
    for date in dates:
        rows = load_changes(conn, date)
        if not rows:
            continue
        already = conn.execute(
            'SELECT COUNT(*) c FROM alert_sent WHERE date=?', (date,)).fetchone()['c']
        sent_rows = 0
        for page_rows, text in build_pages(date, rows, extra=bool(already)):
            if not send(text):
                logging.error('%s 페이지 발송 실패 — 남은 항목은 다음 실행에서 재시도', date)
                return 0
            mark_sent(conn, date, page_rows)   # 성공한 페이지만 기록 → 유실·중복 없음
            sent_rows += len(page_rows)
        logging.info('%s 발송 %d/%d 항목%s', date, sent_rows, len(rows),
                     ' (추가분)' if already else '')
    return 0


if __name__ == '__main__':
    sys.exit(main())
