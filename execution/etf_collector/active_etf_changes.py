"""액티브 ETF 구성종목 변동 계산 — 대시보드/텔레그램 단일 출처(single source of truth).

이 모듈 하나가 etf_data.db에서 '액티브' ETF의 전일 대비 구성종목 변동
(신규 편입 / 편출 / 비중 급변)을 계산한다.

- create_dashboard.generate_etf_html() 이 compute_active_etf_changes() 결과를
  JSON으로 etf.html '액티브 ETF' 서브탭에 임베드한다 (JS는 렌더만).
- execution/etf_active_alert.py 가 같은 함수를 호출해 텔레그램 메시지를 만든다.
→ 대시보드와 텔레그램 알림의 숫자가 '설계상' 항상 일치한다.

정합성 가드: 각 ETF는 latest·prev 양일 모두 collection_log.status='ok' 일 때만
비교한다. 수집이 누락된 날이 있으면 그 ETF의 구성종목이 통째로 비어 '전부 신규'
오탐이 나므로, 그런 ETF는 비교에서 제외하고 skipped 로 표기한다.
(브라우저 JS는 collection_log 를 볼 수 없으므로 이 가드는 반드시 Python에서 수행)
"""
import os
import sys
import html as _html

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from etf_db import get_conn, get_available_dates, get_constituents_for_date  # noqa: E402

# ── 탐지 파라미터 (대시보드/텔레그램 공유 — 두 소비자가 절대 어긋날 수 없게) ──
ACTIVE_KEYWORD = '액티브'
NEW_MIN = 0.5      # 신규 편입으로 볼 최소 비중(%)
EXIT_MIN = 0.5     # 편출로 볼 최소 직전 비중(%)
CHG_MIN = 1.0      # 비중 급변으로 볼 최소 절대 변화(%p)

# 단기금리/채권형 액티브 — 매일 바스켓이 굴러 '비중 급변' 오탐이 쏟아지므로
# 변동 '탐지'에서 제외한다(목록에는 그대로 표시). 이름 부분일치(substring).
MM_BOND_EXCLUDE_KEYWORDS = [
    '머니마켓', 'MMF', 'CD금리', 'KOFR', 'SOFR', '통안',
    '단기채', '단기금융', '단기자금', '종합채권', '국고채', '회사채',
    '채권액티브', '금리액티브',
]

# 텔레그램 단일 메시지 최대 길이 (4096 한도 대비 여유)
TG_CHUNK_LIMIT = 3900
# 하트비트: 변동 0건인 날에도 '변동 없음' 1줄을 보낼지 (봇 헬스 가시성). False면 무발송.
SEND_HEARTBEAT_ON_EMPTY = True
# 텔레그램 메시지가 이 청크 수를 넘으면 이후는 '대시보드 참조'로 절단(과다발송 방지)
MAX_CHUNKS = 20

ETF_URL = 'https://sisyphe10.github.io/Antigravity_Market_Dashboard/etf.html'


def _is_mm_bond(name):
    name = name or ''
    return any(k in name for k in MM_BOND_EXCLUDE_KEYWORDS)


def _ok_codes(conn, date_str):
    rows = conn.execute(
        "SELECT etf_code FROM collection_log WHERE date=? AND status='ok'",
        (date_str,)
    ).fetchall()
    return set(r['etf_code'] for r in rows)


def compute_active_etf_changes(conn=None):
    """액티브 ETF 목록 + 전일 대비 구성종목 변동 payload 반환.

    반환 dict:
      latest, prev, first_run,
      etfs: [ {code,name,aum,nav,close, detect(bool), comparable(bool),
               new:[{code,name,w}], exit:[{code,name,prev_w}],
               chg:[{code,name,w,prev_w,d}]} ]  # 목록: 전 액티브(AUM desc)
      skipped: [{code,name,reason}]              # 수집 누락으로 비교 불가
      totals: {new,exit,chg,etfs_changed}
    """
    own = False
    if conn is None:
        conn = get_conn()
        own = True
    try:
        dates = get_available_dates()  # 실재 거래일만, DESC
        if not dates:
            return {'latest': None, 'prev': None, 'first_run': True,
                    'etfs': [], 'skipped': [],
                    'totals': {'new': 0, 'exit': 0, 'chg': 0, 'etfs_changed': 0}}

        latest = dates[0]
        prev = dates[1] if len(dates) > 1 else None
        first_run = prev is None

        # 액티브 ETF 목록(latest, AUM 내림차순) — 목록에는 전 액티브 포함
        active_rows = conn.execute(
            "SELECT etf_code, etf_name, aum, nav, close_price, volume FROM etf_daily "
            "WHERE date=? AND etf_name LIKE ? ORDER BY aum DESC",
            (latest, f'%{ACTIVE_KEYWORD}%')
        ).fetchall()

        def base_entry(r):
            return {'code': r['etf_code'], 'name': r['etf_name'], 'aum': r['aum'],
                    'nav': r['nav'], 'close': r['close_price'], 'vol': r['volume'],
                    'detect': not _is_mm_bond(r['etf_name']),
                    'comparable': False, 'new': [], 'exit': [], 'chg': []}

        if first_run:
            return {'latest': latest, 'prev': None, 'first_run': True,
                    'etfs': [base_entry(r) for r in active_rows], 'skipped': [],
                    'totals': {'new': 0, 'exit': 0, 'chg': 0, 'etfs_changed': 0}}

        ok_latest = _ok_codes(conn, latest)
        ok_prev = _ok_codes(conn, prev)
        latest_const = get_constituents_for_date(latest)
        prev_const = get_constituents_for_date(prev)

        etfs, skipped = [], []
        tot_new = tot_exit = tot_chg = etfs_changed = 0

        for r in active_rows:
            entry = base_entry(r)
            code, name = entry['code'], entry['name']

            if not entry['detect']:
                etfs.append(entry)  # 목록엔 표시, 탐지는 스킵(MMF/채권형)
                continue

            if code not in ok_latest or code not in ok_prev:
                skipped.append({'code': code, 'name': name, 'reason': '수집 누락(비교불가)'})
                etfs.append(entry)  # comparable=False
                continue

            entry['comparable'] = True
            L = {s['c']: s for s in latest_const.get(code, []) if s.get('c') and s.get('n')}
            P = {s['c']: s for s in prev_const.get(code, []) if s.get('c') and s.get('n')}

            for c, s in L.items():
                w = s['w'] or 0
                if c not in P:
                    if w >= NEW_MIN:
                        entry['new'].append({'code': c, 'name': s['n'], 'w': w})
                else:
                    pw = P[c]['w'] or 0
                    d = w - pw
                    if abs(d) >= CHG_MIN:
                        entry['chg'].append({'code': c, 'name': s['n'], 'w': w,
                                             'prev_w': pw, 'd': d})
            for c, s in P.items():
                if c not in L:
                    pw = s['w'] or 0
                    if pw >= EXIT_MIN:
                        entry['exit'].append({'code': c, 'name': s['n'], 'prev_w': pw})

            entry['new'].sort(key=lambda x: -x['w'])
            entry['exit'].sort(key=lambda x: -x['prev_w'])
            entry['chg'].sort(key=lambda x: -abs(x['d']))

            n, e, c_ = len(entry['new']), len(entry['exit']), len(entry['chg'])
            tot_new += n
            tot_exit += e
            tot_chg += c_
            if n or e or c_:
                etfs_changed += 1
            etfs.append(entry)

        return {'latest': latest, 'prev': prev, 'first_run': False,
                'etfs': etfs, 'skipped': skipped,
                'totals': {'new': tot_new, 'exit': tot_exit, 'chg': tot_chg,
                           'etfs_changed': etfs_changed}}
    finally:
        if own:
            conn.close()


# ── 텔레그램 포맷 ──

def _esc(s):
    return _html.escape(str(s if s is not None else ''))


def _fmt_pct(v):
    return f'{v:.2f}'


def format_telegram_message(result):
    """compute_active_etf_changes 결과 → 텔레그램 HTML 메시지(전체 문자열).

    변동이 있는 ETF만 AUM 내림차순으로 ETF별 섹션 구성.
    변동이 하나도 없으면 하트비트 1줄(SEND_HEARTBEAT_ON_EMPTY=False면 None)."""
    latest = result.get('latest')
    prev = result.get('prev')
    t = result.get('totals', {})

    if result.get('first_run') or not prev:
        return None  # 전일 데이터 없음 → 미발송

    changed = [e for e in result['etfs'] if e.get('detect') and e.get('comparable')
               and (e['new'] or e['exit'] or e['chg'])]

    if not changed:
        if not SEND_HEARTBEAT_ON_EMPTY:
            return None
        comparable_cnt = sum(1 for e in result['etfs'] if e.get('detect') and e.get('comparable'))
        return (f'📌 <b>액티브 ETF 구성 변동</b>\n{latest} (전일 {prev} 대비)\n\n'
                f'오늘 변동 없음 (탐지 대상 {comparable_cnt}개 ETF 비교)')

    lines = []
    lines.append('📌 <b>액티브 ETF 구성 변동</b>')
    lines.append(f'{latest} (전일 {prev} 대비)')
    lines.append(f"신규 {t.get('new',0)} · 편출 {t.get('exit',0)} · 급변 {t.get('chg',0)}"
                 f" · 변동 ETF {t.get('etfs_changed',0)}개")

    for e in changed:
        lines.append('')
        lines.append(f"<b>{_esc(e['name'])}</b>")
        if e['new']:
            items = ', '.join(f"{_esc(s['name'])}({_fmt_pct(s['w'])}%)" for s in e['new'])
            lines.append(f'편입: {items}')
        if e['exit']:
            items = ', '.join(f"{_esc(s['name'])}({_fmt_pct(s['prev_w'])}%)" for s in e['exit'])
            lines.append(f'편출: {items}')
        if e['chg']:
            items = ', '.join(
                f"{_esc(s['name'])} {_fmt_pct(s['prev_w'])}→{_fmt_pct(s['w'])}"
                f"({'+' if s['d'] >= 0 else ''}{_fmt_pct(s['d'])}%p)"
                for s in e['chg'])
            lines.append(f'급변: {items}')

    skipped = result.get('skipped', [])
    if skipped:
        lines.append('')
        lines.append(f'⚠️ 비교불가(수집누락) {len(skipped)}개')
    lines.append('')
    lines.append(f'전체: <a href="{ETF_URL}">대시보드</a>')

    return '\n'.join(lines)


def chunk_by_lines(text, limit=TG_CHUNK_LIMIT):
    """라인 경계로만 분할(HTML 태그가 중간에 잘리지 않게). 한 줄이 limit보다 길면
    그 줄만 하드 슬라이스."""
    if text is None:
        return []
    chunks, cur = [], ''
    for line in text.split('\n'):
        piece = (line + '\n')
        if len(piece) > limit:
            if cur:
                chunks.append(cur.rstrip('\n'))
                cur = ''
            for i in range(0, len(line), limit):
                chunks.append(line[i:i + limit])
            continue
        if len(cur) + len(piece) > limit:
            chunks.append(cur.rstrip('\n'))
            cur = piece
        else:
            cur += piece
    if cur.strip():
        chunks.append(cur.rstrip('\n'))
    # 과다 발송 방지
    if len(chunks) > MAX_CHUNKS:
        chunks = chunks[:MAX_CHUNKS - 1]
        chunks.append(f'… 이하 생략 — 전체는 대시보드 참조: {ETF_URL}')
    return chunks
