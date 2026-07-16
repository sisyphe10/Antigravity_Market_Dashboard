#!/usr/bin/env python3
# wrap_principle_check.py — WRAP 포트폴리오 원칙 준수 일일 점검 → 위반 시에만 텔레그램.
# run_timer_job.sh (wrap-principle-check, 17:10 KST)가 repo 루트 cwd + .env 로드로 실행.
# 근거 원칙 = Memento 원칙 서브탭(principles_web.json)의 정량 룰:
#   계좌별 MDD -10% / 지수 20일선(레버리지 정리) / 물타기 금지 / 삥 금지(최소 비중) /
#   섹터 쏠림 / 종목 수 상한 / 보유 종목 고점 대비 급락.
# 임계값은 config/wrap_principles_config.json 수정만으로 반영(코드 수정 불요).
# 개인 원칙 '종목 ≤7'은 개인 계좌 기준 — WRAP 분산 요건을 고려해 별도 상한을 쓴다.
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

DEFAULTS = {
    'max_holdings': 15,             # WRAP 종목 수 상한 (개인 원칙 7은 개인 계좌용)
    'min_weight_pct': 2.0,          # 삥 금지 — 이 미만 비중 경고
    'max_single_weight_pct': 35.0,  # 단일 종목 쏠림
    'max_sector_weight_pct': 55.0,  # 동일 섹터 합산 쏠림
    'stock_dd_warn_pct': -30.0,     # 보유 종목 고점 대비 낙폭 경고
    'nav_mdd_warn_pct': -10.0,      # 계좌(상품)별 MDD 원칙
    'watering_weight_up_pp': 1.0,   # 물타기 의심: 비중 증가(%p) 하한
    'watering_day_return_pct': -3.0,  # 물타기 의심: 당일 수익률 상한
    'stale_hours': 30,              # portfolio_data.json 신선도 경고 기준
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


def pct(v):
    return '%+.1f%%' % v


def kospi_ma20():
    """dataset.csv에서 KOSPI 종가 최근 20개 → (최종일, 종가, MA20). 데이터 부족 시 None."""
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
    ma20 = sum(v for _, v in rows[-20:]) / 20.0
    return last_date, last_close, ma20


def nav_drawdowns():
    """Wrap_NAV.xlsx '기준가' — 최종행에 값이 있는 상품 컬럼별 (고점 대비 낙폭%, 최종일)."""
    import openpyxl
    wb = openpyxl.load_workbook(NAV_XLSX, read_only=True, data_only=True)
    ws = wb['기준가']
    it = ws.iter_rows(values_only=True)
    header = next(it)
    peaks, lasts, last_date = {}, {}, None
    skip = {'Date', 'KOSPI', 'KOSDAQ', None}
    for row in it:
        if not row or row[0] is None:
            continue
        last_date = row[0]
        for i, name in enumerate(header):
            if name in skip:
                continue
            v = row[i]
            if isinstance(v, (int, float)):
                peaks[name] = max(peaks.get(name, v), v)
                lasts[name] = v
            else:
                lasts[name] = None  # 최종행 기준으로 활성 여부 판정
    wb.close()
    out = {}
    for name, last in lasts.items():
        if last is None or name not in peaks or not peaks[name]:
            continue
        out[name] = (last / peaks[name] - 1.0) * 100.0
    if hasattr(last_date, 'strftime'):
        last_date = last_date.strftime('%Y-%m-%d')
    return out, str(last_date)


def check_portfolios(cfg):
    lines = []
    mtime = os.path.getmtime(PORTFOLIO_JSON)
    age_h = (datetime.now().timestamp() - mtime) / 3600.0
    with open(PORTFOLIO_JSON, encoding='utf-8') as f:
        data = json.load(f)
    for product, holds in data.items():
        v = []
        n = len(holds)
        if n > cfg['max_holdings']:
            v.append('종목 수 %d개 > 상한 %d개' % (n, cfg['max_holdings']))
        tiny = [h for h in holds if isinstance(h.get('weight'), (int, float)) and 0 < h['weight'] < cfg['min_weight_pct']]
        if tiny:
            v.append('삥 의심(비중 %.1f%% 미만): ' % cfg['min_weight_pct']
                     + ', '.join('%s %.1f%%' % (h['name'], h['weight']) for h in tiny))
        big = [h for h in holds if isinstance(h.get('weight'), (int, float)) and h['weight'] > cfg['max_single_weight_pct']]
        for h in big:
            v.append('단일 종목 쏠림: %s %.1f%% > %.1f%%' % (h['name'], h['weight'], cfg['max_single_weight_pct']))
        sectors = {}
        for h in holds:
            if isinstance(h.get('weight'), (int, float)):
                sectors[h.get('sector') or '기타'] = sectors.get(h.get('sector') or '기타', 0.0) + h['weight']
        for sec, w in sectors.items():
            if w > cfg['max_sector_weight_pct']:
                v.append('섹터 쏠림: %s 합산 %.1f%% > %.1f%%' % (sec, w, cfg['max_sector_weight_pct']))
        deep = [h for h in holds if isinstance(h.get('dd'), (int, float)) and h['dd'] <= cfg['stock_dd_warn_pct']]
        for h in deep:
            v.append('종목 고점 대비 급락: %s %s' % (h['name'], pct(h['dd'])))
        water = [h for h in holds
                 if isinstance(h.get('weight'), (int, float)) and isinstance(h.get('weight_prev'), (int, float))
                 and isinstance(h.get('today_return'), (int, float)) and not h.get('is_today_new')
                 and h['weight'] - h['weight_prev'] >= cfg['watering_weight_up_pp']
                 and h['today_return'] <= cfg['watering_day_return_pct']]
        for h in water:
            v.append('물타기 의심: %s 당일 %s인데 비중 %.1f%%→%.1f%%'
                     % (h['name'], pct(h['today_return']), h['weight_prev'], h['weight']))
        if v:
            lines.append('■ ' + product)
            lines.extend('- ' + x for x in v)
    if age_h > cfg['stale_hours']:
        lines.append('- ⚠ portfolio_data.json이 %.0f시간 전 데이터 (갱신 지연 의심)' % age_h)
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
    today = now.strftime('%Y-%m-%d')
    cfg = load_config()

    if now.weekday() >= 5:
        print('wrap_principle_check: weekend — skip')
        return 0
    # KOSPI 는 dataset.csv 최신 가용일 기준(17:10 시점엔 통상 D-1) — 20일선 레짐 판정엔 충분,
    # 메시지에 기준일을 명기한다. portfolio_data.json 은 30분 주기 갱신이라 당일 데이터.
    k = kospi_ma20()

    lines = check_portfolios(cfg)

    navs, nav_date = nav_drawdowns()
    nav_lines = ['- %s MDD %s (고점 대비, %s 기준)' % (name, pct(dd), nav_date)
                 for name, dd in sorted(navs.items()) if dd <= cfg['nav_mdd_warn_pct']]
    if nav_lines:
        lines.append('■ 계좌별 MDD (원칙: -10%에서 리스크 관리)')
        lines.extend(nav_lines)

    if k:
        kdate, close, ma20 = k
        if close < ma20:
            lines.append('■ 시장')
            lines.append('- KOSPI %.2f < 20일선 %.2f (%s 종가 기준) → 레버리지 전량 정리 원칙 확인' % (close, ma20, kdate))

    if not lines:
        print('wrap_principle_check: no violations — silent')
        return 0

    msg = '\U0001F9ED WRAP 원칙 점검 — %s (%s)\n\n' % (today, DOW[now.weekday()]) + '\n'.join(lines)
    ok = send_telegram(msg)
    print('wrap_principle_check: %d line(s), telegram %s' % (len(lines), 'sent' if ok else 'FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
