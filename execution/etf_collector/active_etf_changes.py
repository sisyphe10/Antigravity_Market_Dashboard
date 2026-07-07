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
# CU당 수량 상대변화가 이내면 '주가 드리프트'(실매매 아님)로 판정 — 급변(chg)에만 적용.
# 수량이 한쪽이라도 NULL/0이면 판별 불가 → 드리프트 아님(기본값, 실매매 놓침 방지 우선).
QTY_DRIFT_TOL = 0.005

# ── 텔레그램 전용 표시 필터 (대시보드 JSON에는 미적용 — 전체 유지) ──
AMT_MIN_TG = 3e8       # ETF별 상세줄 최소 |예상금액|(원): 3억 미만 라인 컷
PER_ETF_MAX_ITEMS = 15  # ETF당 상세 종목 상한 (블록 비대화 방지, 초과분 '외 N종목')
TOP_FLOWS = 5          # 종목별 순매수 집계 매수/매도 각 상위 개수
TOP_MOVES = 5          # '큰 변동 TOP' 개수 (금액순)

# 비-주식형 액티브(채권/단기금리/현금성/원자재/멀티에셋/TDF)는 목록·탐지 양쪽에서 제외.
# → '액티브 ETF' 탭은 순수 주식형 위주. 이름 부분일치(substring).
# ★'채' 는 채권형(국채/회사채/금융채/은행채/종합채권/채권혼합/전단채 등)만 잡는다 —
#   '밸류체인' 등 주식형의 '체'(U+CCB4)와 '채'(U+CC44)는 다른 글자라 오탈락 없음(313개 전수 검증).
MM_BOND_EXCLUDE_KEYWORDS = [
    '채', '하이일드', 'CD', 'KOFR', 'SOFR', '통안', '금리', '머니마켓', 'MMF',
    '단기자금', '파킹', 'TDF',
    '자산배분', '멀티에셋', 'TIF',
    '금액티브', '국제금', '은액티브', '골드', '원유', '귀금속', '원자재',
]

# 현금성 구성종목 — 종목 변동 탐지에서 제외 (원화현금/예수금/예금 등).
CASH_NAME_KEYWORDS = ['현금', '예수금', '예금', 'KRW', 'CASH', '단기대출']


def _is_cash(name):
    name = name or ''
    return any(k in name for k in CASH_NAME_KEYWORDS)

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

        # 전일 시세 맵 (AUM/NAV 전일 대비 변동% 계산용)
        prev_daily = {}
        if prev:
            for pr in conn.execute(
                    "SELECT etf_code, aum, nav FROM etf_daily WHERE date=?", (prev,)).fetchall():
                prev_daily[pr['etf_code']] = pr

        def _pct(cur, prv):
            if cur is None or not prv:
                return None
            return (cur - prv) / prv * 100

        def base_entry(r):
            p = prev_daily.get(r['etf_code'])
            paum = p['aum'] if p else None
            pnav = p['nav'] if p else None
            return {'code': r['etf_code'], 'name': r['etf_name'], 'aum': r['aum'],
                    'nav': r['nav'], 'close': r['close_price'], 'vol': r['volume'],
                    'aum_chg': _pct(r['aum'], paum), 'nav_chg': _pct(r['nav'], pnav),
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
            aum = entry['aum'] or 0  # 예상 편입/편출 금액(원) = 비중변화(%p) × AUM / 100
            L = {s['c']: s for s in latest_const.get(code, [])
                 if s.get('c') and s.get('n') and not _is_cash(s['n'])}
            P = {s['c']: s for s in prev_const.get(code, [])
                 if s.get('c') and s.get('n') and not _is_cash(s['n'])}

            for c, s in L.items():
                w = s['w'] or 0
                if c not in P:
                    if w >= NEW_MIN:
                        entry['new'].append({'code': c, 'name': s['n'], 'w': w,
                                             'amt': w * aum / 100})
                else:
                    pw = P[c]['w'] or 0
                    d = w - pw
                    if abs(d) >= CHG_MIN:
                        # 실매매/드리프트 판별: CU당 수량이 양일 모두 존재·0이 아니고
                        # 상대변화가 허용치 이내면 주가 드리프트(수량 불변 = 매매 없음).
                        # 스왑형(수량 상시 0/NULL)·구버전 row(NULL)는 판별 불가 → False.
                        qn, qp = s.get('q'), P[c].get('q')
                        drift = bool(qn and qp
                                     and abs(qn - qp) / abs(qp) <= QTY_DRIFT_TOL)
                        entry['chg'].append({'code': c, 'name': s['n'], 'w': w,
                                             'prev_w': pw, 'd': d, 'amt': d * aum / 100,
                                             'drift': drift})
            for c, s in P.items():
                if c not in L:
                    pw = s['w'] or 0
                    if pw >= EXIT_MIN:
                        entry['exit'].append({'code': c, 'name': s['n'], 'prev_w': pw,
                                              'amt': -pw * aum / 100})

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
    return f'{v:.1f}'


def _fmt_won(v):
    """예상 편입/편출 금액(원) → 부호 붙은 억원 표기 (조 넘으면 N조 N,NNN억)."""
    if v is None:
        return ''
    a = abs(v)
    sign = '-' if v < 0 else '+'
    if a >= 1e12:
        jo = int(a // 1e12)
        eok = round((a - jo * 1e12) / 1e8)
        return f'{sign}{jo}조 {eok:,}억'
    if a >= 1e8:
        return f'{sign}{round(a / 1e8):,}억'
    return f'{sign}{a / 1e8:.1f}억'


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
        skipped_cnt = len(result.get('skipped', []))
        header = f'📌 <b>액티브 ETF 구성 변동</b>\n{latest} (전일 {prev} 대비)\n\n'
        # 수집 실패로 비교 자체가 안 된 경우를 '변동 없음'과 구분 (2026-07-08 etfcheck 403 사고)
        if comparable_cnt == 0 and skipped_cnt:
            return (header + f'⚠️ 구성종목 수집 실패로 비교 불가 (수집누락 {skipped_cnt}개)\n'
                    f'데이터 소스(etfcheck) 점검 필요')
        msg = header + f'오늘 변동 없음 (탐지 대상 {comparable_cnt}개 ETF 비교)'
        if skipped_cnt:
            msg += f'\n⚠️ 비교불가(수집누락) {skipped_cnt}개'
        return msg

    lines = []
    lines.append('📌 <b>액티브 ETF 구성 변동</b>')
    lines.append(f'{latest} (전일 {prev} 대비)')
    lines.append(f"편입 {t.get('new',0)} · 편출 {t.get('exit',0)} · 급변 {t.get('chg',0)}"
                 f" · 변동 ETF {t.get('etfs_changed',0)}개")

    for e in changed:
        lines.append('')
        lines.append(f"<b>{_esc(e['name'])}</b>")
        if e['new']:
            items = ', '.join(f"{_esc(s['name'])}({_fmt_pct(s['w'])}%, {_fmt_won(s.get('amt'))})" for s in e['new'])
            lines.append(f'편입: {items}')
        if e['exit']:
            items = ', '.join(f"{_esc(s['name'])}({_fmt_pct(s['prev_w'])}%, {_fmt_won(s.get('amt'))})" for s in e['exit'])
            lines.append(f'편출: {items}')
        if e['chg']:
            items = ', '.join(
                f"{_esc(s['name'])} {_fmt_pct(s['prev_w'])}→{_fmt_pct(s['w'])}"
                f"({'+' if s['d'] >= 0 else ''}{_fmt_pct(s['d'])}%p, {_fmt_won(s.get('amt'))})"
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


# ── 3단 구조 텔레그램 포맷 (2026-07-08 개편) ──────────────────────────────
# ① 헤더 요약 ② 종목별 순매수 집계 + 큰 변동 TOP ③ ETF별 상세(접힌 인용구).
# 표시 필터(텔레그램 전용): 드리프트 chg 제외 + |예상금액| ≥ AMT_MIN_TG.
# 대시보드 JSON은 전량 유지(drift 플래그만 추가) — 숫자 자체는 동일한 단일 출처.

def _tg_view(result):
    """ETF별 텔레그램 표시용 필터링 뷰: [(entry, tg_new, tg_exit, tg_chg)] (변동 있는 것만)"""
    view = []
    for e in result['etfs']:
        if not (e.get('detect') and e.get('comparable')):
            continue
        tg_new = [s for s in e['new'] if abs(s.get('amt') or 0) >= AMT_MIN_TG]
        tg_exit = [s for s in e['exit'] if abs(s.get('amt') or 0) >= AMT_MIN_TG]
        tg_chg = [s for s in e['chg'] if not s.get('drift')
                  and abs(s.get('amt') or 0) >= AMT_MIN_TG]
        if tg_new or tg_exit or tg_chg:
            view.append((e, tg_new, tg_exit, tg_chg))
    return view


def aggregate_stock_flows(result):
    """종목별 순매수 집계 (ETF 경계 합산, 실매매만 — 드리프트 chg 제외).

    3억 컷 '이전' 원본 항목으로 합산한다: ETF 14개에 각 2억씩 팔린 종목의
    -28억 신호를 상세줄 컷이 죽이면 안 되므로 (집계는 무필터, 표시는 상위 N).
    반환: [{'code','name','amt','n_etfs'}] |amt| 내림차순.
    """
    flows = {}
    for e in result['etfs']:
        if not (e.get('detect') and e.get('comparable')):
            continue
        items = (e['new'] + e['exit']
                 + [s for s in e['chg'] if not s.get('drift')])
        for s in items:
            key = s.get('code') or s.get('name')
            if not key:
                continue
            f = flows.setdefault(key, {'name': s.get('name'), 'amt': 0.0, 'etfs': set()})
            f['amt'] += s.get('amt') or 0
            f['etfs'].add(e['code'])
    out = [{'code': k, 'name': v['name'], 'amt': v['amt'], 'n_etfs': len(v['etfs'])}
           for k, v in flows.items()]
    out.sort(key=lambda x: -abs(x['amt']))
    return out


def _flow_line(items):
    """종목별 집계 한 줄: '삼성전자 +14억 (3개 ETF), …' (단일 ETF면 카운트 생략)"""
    parts = []
    for f in items:
        cnt = f' ({f["n_etfs"]}개 ETF)' if f['n_etfs'] >= 2 else ''
        parts.append(f'{_esc(f["name"])} {_fmt_won(f["amt"])}{cnt}')
    return ', '.join(parts)


def _move_line(etf_name, kind, s):
    """큰 변동 TOP 한 줄"""
    if kind == 'new':
        body = f'{_esc(s["name"])} 신규 {_fmt_pct(s["w"])}%'
    elif kind == 'exit':
        body = f'{_esc(s["name"])} 편출({_fmt_pct(s["prev_w"])}%)'
    else:
        body = (f'{_esc(s["name"])} {_fmt_pct(s["prev_w"])}→{_fmt_pct(s["w"])}%')
    return f'{_esc(etf_name)}: {body} ({_fmt_won(s.get("amt"))})'


def format_telegram_blocks(result):
    """3단 구조 텔레그램 메시지 — '원자 블록' 문자열 리스트 반환 (None=미발송).

    blocks[0] = 헤더(요약+종목별 순매수+큰 변동 TOP), blocks[1:] = ETF별
    <blockquote expandable> 상세. 블록 내부는 pack_blocks 가 절대 자르지 않으므로
    HTML 태그가 청크 경계에서 절단되지 않는다.
    """
    latest = result.get('latest')
    prev = result.get('prev')

    if result.get('first_run') or not prev:
        return None  # 전일 데이터 없음 → 미발송

    view = _tg_view(result)
    header_meta = f'{latest} (전일 {prev} 대비) · 실매매·3억↑ 기준'

    if not view:
        if not SEND_HEARTBEAT_ON_EMPTY:
            return None
        comparable_cnt = sum(1 for e in result['etfs'] if e.get('detect') and e.get('comparable'))
        skipped_cnt = len(result.get('skipped', []))
        head = f'📌 <b>액티브 ETF 구성 변동</b>\n{header_meta}\n\n'
        # 수집 실패로 비교 자체가 안 된 경우를 '변동 없음'과 구분 (2026-07-08 etfcheck 403 사고)
        if comparable_cnt == 0 and skipped_cnt:
            return [head + f'⚠️ 구성종목 수집 실패로 비교 불가 (수집누락 {skipped_cnt}개)\n'
                    f'데이터 소스(etfcheck) 점검 필요']
        msg = head + f'오늘 변동 없음 (탐지 대상 {comparable_cnt}개 ETF 비교)'
        if skipped_cnt:
            msg += f'\n⚠️ 비교불가(수집누락) {skipped_cnt}개'
        return [msg]

    n_new = sum(len(v[1]) for v in view)
    n_exit = sum(len(v[2]) for v in view)
    n_chg = sum(len(v[3]) for v in view)

    lines = ['📌 <b>액티브 ETF 구성 변동</b>', header_meta,
             f'편입 {n_new} · 편출 {n_exit} · 급변 {n_chg} · 변동 ETF {len(view)}개', '']

    # ② 종목별 순매수 집계 (집계 자체는 컷 없이, 표시만 상위 N)
    flows = aggregate_stock_flows(result)
    buys = [f for f in flows if f['amt'] > 0][:TOP_FLOWS]
    sells = [f for f in flows if f['amt'] < 0][:TOP_FLOWS]
    if buys or sells:
        lines.append('■ <b>종목별 순매수</b>')
        if buys:
            lines.append(f'매수: {_flow_line(buys)}')
        if sells:
            lines.append(f'매도: {_flow_line(sells)}')
        lines.append('')

    # ② 큰 변동 TOP (개별 ETF-종목 라인, 금액순 — 표시 필터 통과분에서)
    moves = []
    for e, tg_new, tg_exit, tg_chg in view:
        moves += [(e['name'], 'new', s) for s in tg_new]
        moves += [(e['name'], 'exit', s) for s in tg_exit]
        moves += [(e['name'], 'chg', s) for s in tg_chg]
    moves.sort(key=lambda m: -abs(m[2].get('amt') or 0))
    if moves:
        lines.append(f'■ <b>큰 변동 TOP {min(TOP_MOVES, len(moves))}</b> (금액순)')
        for i, (nm, kind, s) in enumerate(moves[:TOP_MOVES], 1):
            lines.append(f'{i}. {_move_line(nm, kind, s)}')
        lines.append('')

    skipped = result.get('skipped', [])
    if skipped:
        lines.append(f'⚠️ 비교불가(수집누락) {len(skipped)}개')
    lines.append(f'전체: <a href="{ETF_URL}">대시보드</a>')
    lines.append(f'▼ ETF별 상세 {len(view)}개 (탭하여 펼치기)')
    blocks = ['\n'.join(lines)]

    # ③ ETF별 상세 — 각 ETF가 완결된 expandable blockquote 1개 (원자 블록)
    for e, tg_new, tg_exit, tg_chg in view:
        tg_chg = sorted(tg_chg, key=lambda s: -abs(s.get('amt') or 0))
        # ETF당 종목 수 상한 (new→exit→chg 순 우선)
        budget = PER_ETF_MAX_ITEMS
        cut_new, cut_exit, cut_chg = tg_new[:budget], [], []
        budget -= len(cut_new)
        cut_exit = tg_exit[:budget]
        budget -= len(cut_exit)
        cut_chg = tg_chg[:budget]
        omitted = (len(tg_new) + len(tg_exit) + len(tg_chg)
                   - len(cut_new) - len(cut_exit) - len(cut_chg))

        b = [f'<blockquote expandable><b>{_esc(e["name"])}</b>']
        if cut_new:
            items = ', '.join(f'{_esc(s["name"])}({_fmt_pct(s["w"])}%, {_fmt_won(s.get("amt"))})'
                              for s in cut_new)
            b.append(f'편입: {items}')
        if cut_exit:
            items = ', '.join(f'{_esc(s["name"])}({_fmt_pct(s["prev_w"])}%, {_fmt_won(s.get("amt"))})'
                              for s in cut_exit)
            b.append(f'편출: {items}')
        if cut_chg:
            items = ', '.join(
                f'{_esc(s["name"])} {_fmt_pct(s["prev_w"])}→{_fmt_pct(s["w"])}'
                f'({"+" if s["d"] >= 0 else ""}{_fmt_pct(s["d"])}%p, {_fmt_won(s.get("amt"))})'
                for s in cut_chg)
            b.append(f'급변: {items}')
        if omitted > 0:
            b.append(f'…외 {omitted}종목')
        b.append('</blockquote>')
        blocks.append('\n'.join(b))

    return blocks


def _split_oversize_block(block, limit):
    """limit을 넘는 단일 블록의 최후수단 분할 — blockquote면 태그를 재개폐해
    각 조각이 독립적으로 유효한 HTML이 되게 한다."""
    OPEN, CLOSE = '<blockquote expandable>', '</blockquote>'
    is_quote = block.startswith(OPEN) and block.endswith(CLOSE)
    inner = block[len(OPEN):-len(CLOSE)] if is_quote else block
    inner_limit = max(200, limit - len(OPEN) - len(CLOSE))
    pieces = chunk_by_lines(inner, inner_limit)
    if is_quote:
        return [f'{OPEN}{p}{CLOSE}' for p in pieces]
    return pieces


def pack_blocks(blocks, limit=TG_CHUNK_LIMIT):
    """블록(완결 HTML 문자열)을 순서 유지 그리디 패킹 — 블록 내부는 자르지 않음.

    단일 블록이 limit 초과 시에만 _split_oversize_block 으로 최후수단 분할.
    chunk_by_lines 와 동일한 MAX_CHUNKS 절단 정책 적용.
    """
    if not blocks:
        return []
    msgs, cur = [], ''
    for b in blocks:
        parts = _split_oversize_block(b, limit) if len(b) > limit else [b]
        for p in parts:
            if not cur:
                cur = p
            elif len(cur) + 1 + len(p) <= limit:
                cur += '\n' + p
            else:
                msgs.append(cur)
                cur = p
    if cur:
        msgs.append(cur)
    if len(msgs) > MAX_CHUNKS:
        msgs = msgs[:MAX_CHUNKS - 1]
        msgs.append(f'… 이하 생략 — 전체는 대시보드 참조: {ETF_URL}')
    return msgs
