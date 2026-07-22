#!/usr/bin/env python3
# wrap_principle_check.py — WRAP 포트폴리오 원칙 준수 일일 점검 (v2, 변화 기반 알림).
# run_timer_job.sh (wrap-principle-check, 17:10 KST)가 repo 루트 cwd + .env 로드로 실행.
#
# 알림 설계 (2026-07-16 사용자 확정):
#   행위 룰(당일 발생시 항상): 물타기 의심(원칙17) · 약세장 신규 편입(원칙11)
#   상태 룰(변화 기반): 계좌 MDD(원칙3) · 섹터 쏠림(원칙26) · 종목 DD · 삥(원칙25) ·
#     종목 수 상한 · 지수 20일선(원칙8) — 신규 진입 🆕 / 해소 ✅ 시에만 상세,
#     지속분은 요약 1줄. 변화·행위 없으면 평일 침묵, 일요일 20:00 전체 상세 리포트.
#   종목 단위 룰(종목 DD)은 상품 중복 없이 1회만 표기("N개 상품 보유").
# 전일 상태 = logs/wrap_principle_state.json (diff 근거, 거래일마다 갱신).
# 임계값 = config/wrap_principles_config.json (없으면 DEFAULTS).
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
DOW = ['월', '화', '수', '목', '금', '토', '일']
PORTFOLIO_JSON = 'portfolio_data.json'
NAV_XLSX = 'Wrap_NAV.xlsx'
DATASET_CSV = 'dataset.csv'
CONFIG_PATH = os.path.join('config', 'wrap_principles_config.json')
STATE_PATH = os.path.join('logs', 'wrap_principle_state.json')

DEFAULTS = {
    'max_holdings': 15,             # WRAP 종목 수 상한 (개인 원칙 7은 개인 계좌용)
    'min_weight_pct': 2.0,          # 삥 금지(원칙25) — 이 미만 비중
    'max_single_weight_pct': 35.0,  # 단일 종목 쏠림
    'max_sector_weight_pct': 65.0,  # 동일 섹터 합산(원칙26) — 주도 섹터 60%는 의도된 쏠림으로 간주
    'stock_dd_warn_pct': -30.0,     # 보유 종목 고점 대비 낙폭
    'nav_mdd_warn_pct': -10.0,      # 계좌별 MDD(원칙3)
    'watering_weight_up_pp': 1.0,   # 물타기 의심(원칙17): 비중 증가 %p 하한
    'watering_day_return_pct': -3.0,  # 물타기 의심: 당일 수익률 상한
    'stale_hours': 30,              # portfolio_data.json 신선도 경고
}
LABEL = {
    'mdd': '계좌 MDD (원칙3)',
    'sector': '섹터 쏠림 (원칙26)',
    'stockdd': '종목 고점 대비 급락',
    'tiny': '삥 의심 (원칙25)',
    'count': '종목 수 상한',
    'single': '단일 종목 쏠림',
    'kospi': '지수 20일선 (원칙8)',
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding='utf-8') as f:
            user = json.load(f)
        for k in DEFAULTS:
            if k in user:
                cfg[k] = user[k]
    except (OSError, ValueError):
        pass
    return cfg


def load_portfolios():
    with open(PORTFOLIO_JSON, encoding='utf-8') as f:
        data = json.load(f)
    out = {}
    for product, holds in data.items():
        if product.startswith('_') or not isinstance(holds, list):
            continue
        out[product] = [h for h in holds if isinstance(h, dict)]
    return out


def kospi_ma20():
    rows = []
    with open(DATASET_CSV, encoding='utf-8-sig') as f:
        for r in csv.reader(f):
            if len(r) >= 4 and r[1] == 'KOSPI':
                try:
                    rows.append((r[0], float(r[2])))
                except ValueError:
                    pass
    if len(rows) < 20:
        return None
    rows.sort(key=lambda x: x[0])
    last_date, last_close = rows[-1]
    return last_date, last_close, sum(v for _, v in rows[-20:]) / 20.0


def nav_drawdowns():
    import openpyxl
    wb = openpyxl.load_workbook(NAV_XLSX, read_only=True, data_only=True)
    ws = wb['기준가']
    it = ws.iter_rows(values_only=True)
    header = next(it)
    peaks, lasts = {}, {}
    skip = {'Date', 'KOSPI', 'KOSDAQ', None}
    for row in it:
        if not row or row[0] is None:
            continue
        for i, name in enumerate(header):
            if name in skip:
                continue
            v = row[i]
            if isinstance(v, (int, float)):
                peaks[name] = max(peaks.get(name, v), v)
                lasts[name] = v
            else:
                lasts[name] = None
    wb.close()
    return {n: (v / peaks[n] - 1.0) * 100.0 for n, v in lasts.items()
            if v is not None and peaks.get(n)}


def build_state(cfg, ports, navs, kospi):
    """상태 룰 위반 → {key: 표시문구}. 종목 DD는 종목 단위 dedup."""
    st = {}
    stock_dd = {}   # code -> (name, dd, n_products)
    for product, holds in ports.items():
        if len(holds) > cfg['max_holdings']:
            st['count|%s' % product] = '%s 종목 %d개 > 상한 %d개' % (product, len(holds), cfg['max_holdings'])
        sectors = {}
        for h in holds:
            w = h.get('weight')
            if not isinstance(w, (int, float)):
                continue
            sec = h.get('sector') or '기타'
            sectors[sec] = sectors.get(sec, 0.0) + w
            if 0 < w < cfg['min_weight_pct']:
                st['tiny|%s|%s' % (product, h.get('code'))] = '%s %s %.1f%%' % (product, h.get('name'), w)
            if w > cfg['max_single_weight_pct']:
                st['single|%s|%s' % (product, h.get('code'))] = '%s %s %.1f%% > %.1f%%' % (product, h.get('name'), w, cfg['max_single_weight_pct'])
            dd = h.get('dd')
            if isinstance(dd, (int, float)) and dd <= cfg['stock_dd_warn_pct']:
                c = h.get('code') or h.get('name')
                if c in stock_dd:
                    stock_dd[c] = (stock_dd[c][0], min(stock_dd[c][1], dd), stock_dd[c][2] + 1)
                else:
                    stock_dd[c] = (h.get('name'), dd, 1)
        for sec, w in sectors.items():
            if w > cfg['max_sector_weight_pct']:
                st['sector|%s|%s' % (product, sec)] = '%s %s 합산 %.1f%% > %.1f%%' % (product, sec, w, cfg['max_sector_weight_pct'])
    for code, (name, dd, n) in stock_dd.items():
        st['stockdd|%s' % code] = '%s %+.1f%% (%d개 상품 보유)' % (name, dd, n)
    for prod, dd in navs.items():
        if dd <= cfg['nav_mdd_warn_pct']:
            st['mdd|%s' % prod] = '%s MDD %+.1f%%' % (prod, dd)
    if kospi:
        kdate, close, ma20 = kospi
        if close < ma20:
            st['kospi'] = 'KOSPI %.2f < 20일선 %.2f (%s 종가) → 레버리지 전량 정리 원칙' % (close, ma20, kdate)
    return st


def build_actions(cfg, ports, kospi):
    """행위 룰(당일) → {action_key: 표시문구}. 종목 단위 집계(상품 중복 제거),
    당일 이미 발송한 key 는 main()에서 걸러 재발송을 막는다."""
    water, newbuy = {}, {}
    bear = bool(kospi and kospi[1] < kospi[2])
    for product, holds in ports.items():
        for h in holds:
            code = h.get('code') or h.get('name')
            w, wp, tr = h.get('weight'), h.get('weight_prev'), h.get('today_return')
            if (isinstance(w, (int, float)) and isinstance(wp, (int, float)) and isinstance(tr, (int, float))
                    and not h.get('is_today_new')
                    and w - wp >= cfg['watering_weight_up_pp'] and tr <= cfg['watering_day_return_pct']):
                e = water.setdefault(code, {'name': h.get('name'), 'tr': tr, 'n': 0})
                e['n'] += 1
            if h.get('is_today_new') and bear:
                e = newbuy.setdefault(code, {'name': h.get('name'), 'w': h.get('weight') or 0.0, 'n': 0})
                e['n'] += 1
    acts = {}
    for code, e in water.items():
        acts['water|%s' % code] = ('물타기 의심 (원칙17): %s 당일 %+.1f%%인데 비중 확대 (%d개 상품)'
                                   % (e['name'], e['tr'], e['n']))
    for code, e in newbuy.items():
        acts['newbear|%s' % code] = ('약세장 신규 편입 (원칙11 확인): %s 비중 %.1f%% (%d개 상품)'
                                     % (e['name'], e['w'], e['n']))
    return acts


def group_summary(state):
    cnt = {}
    for k in state:
        cnt[k.split('|')[0]] = cnt.get(k.split('|')[0], 0) + 1
    order = ['mdd', 'sector', 'stockdd', 'single', 'tiny', 'count', 'kospi']
    parts = ['%s %d건' % (LABEL[g].split(' (')[0], cnt[g]) for g in order if cnt.get(g)]
    return ' · '.join(parts) if parts else '없음'


def full_detail(state):
    lines = []
    order = ['mdd', 'sector', 'single', 'stockdd', 'tiny', 'count', 'kospi']
    for g in order:
        items = sorted(v for k, v in state.items() if k.split('|')[0] == g)
        if not items:
            continue
        lines.append('■ ' + LABEL[g])
        lines.extend('- ' + x for x in items)
    return lines


def send_telegram(text):
    token = os.environ.get('TELEGRAM_SISYPHE_BOT_TOKEN', '')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
    if not token or not chat_id:
        sys.stderr.write('wrap_principle_check: missing telegram env\n')
        return False
    body = urllib.parse.urlencode({'chat_id': chat_id, 'text': text,
                                   'disable_web_page_preview': 'true'}).encode('utf-8')
    req = urllib.request.Request('https://api.telegram.org/bot%s/sendMessage' % token, data=body)
    with urllib.request.urlopen(req, timeout=30) as res:
        return bool(json.load(res).get('ok'))


def main():
    now = datetime.now(KST)
    # 토요일 skip. 일요일은 20:00 전체 점검 틱만 통과(17:10 일일 틱은 skip).
    if now.weekday() == 5 or (now.weekday() == 6 and now.hour < 19):
        print('wrap_principle_check: weekend — skip')
        return 0
    cfg = load_config()
    ports = load_portfolios()
    navs = nav_drawdowns()
    kospi = kospi_ma20()  # 17:10 시점엔 통상 D-1 종가 — 20일선 레짐 판정용, 기준일 명기

    state = build_state(cfg, ports, navs, kospi)
    actions = build_actions(cfg, ports, kospi)

    baseline = not os.path.exists(STATE_PATH)  # 첫 실행: 스냅숏만 저장, 🆕 도배 방지
    seed = bool(os.environ.get('WPC_SEED'))    # 무발송 시드 모드(배포 직후 상태 동기화용)
    prev, prev_doc = {}, {}
    try:
        with open(STATE_PATH, encoding='utf-8') as f:
            prev_doc = json.load(f)
        prev = prev_doc.get('state', {})
    except (OSError, ValueError):
        pass
    new_keys = [] if baseline else [k for k in state if k not in prev]
    resolved = [] if baseline else [k for k in prev if k not in state]
    # 행위 룰 당일 재발송 차단: 같은 날짜에 이미 보낸 action key 제외
    today_str = now.strftime('%Y-%m-%d')
    sent_before = set(prev_doc.get('actions_sent', [])) if prev_doc.get('date') == today_str else set()
    actions_new = {k: v for k, v in actions.items() if k not in sent_before}

    age_h = (datetime.now().timestamp() - os.path.getmtime(PORTFOLIO_JSON)) / 3600.0
    stale = age_h > cfg['stale_hours']

    sunday_full = now.weekday() == 6 and not baseline
    must_send = (not seed) and (bool(actions_new or new_keys or resolved or stale) or (sunday_full and state))

    if must_send:
        head = '\U0001F9ED WRAP 원칙 점검 — %s (%s)' % (today_str, DOW[now.weekday()])
        parts = [head + (' — 주간 전체 상세' if sunday_full else '')]
        if actions_new:
            parts.append('[오늘 행동]\n' + '\n'.join('- ' + actions_new[k] for k in sorted(actions_new)))
        if new_keys:
            parts.append('[신규 위반] \U0001F195\n' + '\n'.join('- %s: %s' % (LABEL[k.split('|')[0]], state[k]) for k in sorted(new_keys)))
        if resolved:
            parts.append('[해소] ✅\n' + '\n'.join('- %s: %s' % (LABEL[k.split('|')[0]], prev[k]) for k in sorted(resolved)))
        if sunday_full and state:
            parts.append('\n'.join(full_detail(state)))
        else:
            parts.append('지속 중: ' + group_summary({k: v for k, v in state.items() if k not in new_keys}))
        if stale:
            parts.append('⚠ portfolio_data.json이 %.0f시간 전 데이터 (갱신 지연 의심)' % age_h)
        ok = send_telegram('\n\n'.join(parts))
        print('wrap_principle_check: sent=%s actions=%d new=%d resolved=%d persist=%d'
              % (ok, len(actions_new), len(new_keys), len(resolved), len(state)))
        if not ok:
            return 1
    else:
        print('wrap_principle_check: silent (seed=%s, persist=%d, actions_already_sent=%d)'
              % (seed, len(state), len(sent_before & set(actions))))

    os.makedirs('logs', exist_ok=True)
    tmp = STATE_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'date': today_str, 'state': state,
                   'actions_sent': sorted(sent_before | set(actions))},
                  f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_PATH)
    return 0


if __name__ == '__main__':
    sys.exit(main())
