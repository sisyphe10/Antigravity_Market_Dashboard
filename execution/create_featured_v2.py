# -*- coding: utf-8 -*-
"""
Featured v2 (테스트 페이지) — 데이터/HTML 분리 + 상단 인사이트 블록.

기존 featured.html 은 featured_data.json 165일치(60,377행)를 통째로 인라인 임베드해
12.9MB 가 됐는데 화면은 하루치(약 260행)만 쓴다. 여기서는

    featured_v2/manifest.json          거래일 목록·최신일·revision
    featured_v2/series.json            일자별 소형 집계(신고가 건수 등)
    featured_v2/daily/YYYY-MM-DD.json  그날의 표 6종 + 신고가 3종 + 요약 + 사전계산 인사이트

로 나누고 HTML 은 셸만 남긴다. 인사이트 계산(연속 등장·신규 진입 등)은 전부 생성기에서 한다.

★비거래일 데이터는 읽는 시점에 걸러낸다 — 과거 오염 정리(repair_featured_history.py)
  전에도 이 페이지는 정확하다.

생성물은 git 에 넣지 않는다(추적하면 다시 매일 수 MB 씩 히스토리에 쌓인다).
ts.net 게시는 publish_snapshot.sh 화이트리스트에 featured_v2/ 를 넣어야 한다.
"""
import hashlib
import io
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from krx_session import is_session
from nav_style import (PRETENDARD_LINK_LOCAL, PALETTE_CSS_VARS,
                       NAV_CSS as AOE_NAV_CSS, SIDEBAR_CSS, nav_html, sidebar_html)
from aoe_tokens_util import aoe_tokens_css

KST = timezone(timedelta(hours=9))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FEATURED = 'featured_data.json'
NEWHIGH = 'newhigh_20d.json'
NEWS = 'featured_news.json'
WICS = 'wics_mapping.json'
WICS_ALL = 'wics_all.json'
STOCK_MASTER = 'stock_master.json'
UNIVERSE_CSV = 'universe_tickers.csv'
WATCHLISTS = os.path.join('quoteboard', 'watchlists.json')

OUT_HTML = 'featured.html'          # Featured 자리 정본(2026-08-05 교체). 구 생성기는 featured_legacy.html
# 기본 = featured_v2/ 디렉토리(최종안). publish_snapshot.sh 화이트리스트에 디렉토리 include
# 한 쌍을 넣어야 게시된다. 아직 그 배포 승인 전이라, FEATURED_V2_FLAT=1 이면 루트 평면
# 파일명(featured_v2_*.json)으로 떨어뜨려 기존 '/*.json' 와일드카드만으로 게시되게 한다.
FLAT = os.environ.get('FEATURED_V2_FLAT') == '1'
OUT_DIR = 'featured_v2'
SHARD_DAYS = int(os.environ.get('FEATURED_V2_SHARD_DAYS', '60'))
STREAK_WINDOW = 20
TILT_MIN_SAMPLE = 5
NH_WINDOW = 20
STRONG_RANK = 20
YF_HIST = 'stock_price_history.json'
KIS_HIST = 'kis_price_history.json'

RANK_TYPES = [
    ('absolute',   '거래대금 TOP 30'),
    ('turnover',   '거래대금/시총 비율 TOP 30'),
    ('kospi_cap',  '코스피 시가총액 TOP 30'),
    ('kosdaq_cap', '코스닥 시가총액 TOP 30'),
    ('kospi_chg',  '코스피 상승률 TOP 30'),
    ('kosdaq_chg', '코스닥 상승률 TOP 30'),
]
NH_TYPES = ['newhigh_20d', 'newhigh_120d', 'newhigh_52w']
# '이례' 타입 — 시총 TOP30 은 대형주가 매일 등장해 워치리스트 교차의 변별력이 없다
NOTABLE_TYPES = set(NH_TYPES) | {'absolute', 'turnover', 'kospi_chg', 'kosdaq_chg'}


def _read(path, default=None):
    try:
        with io.open(os.path.join(REPO, path), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _write(relpath, obj):
    p = os.path.join(REPO, relpath)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, p)
    return os.path.getsize(p)


def _out(kind, name):
    """kind='daily'|'meta' 의 산출 경로. FLAT 이면 루트 평면 파일명."""
    if FLAT:
        return ('featured_v2_d_' + name) if kind == 'daily' else ('featured_v2_' + name)
    return os.path.join(OUT_DIR, 'daily', name) if kind == 'daily' else os.path.join(OUT_DIR, name)


def _rev(obj):
    blob = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return hashlib.sha256(blob).hexdigest()[:12]


def load_sector_map():
    """code -> 업종. 앞 소스가 이기고, 빈 곳만 뒤 소스로 메운다."""
    smap = {}
    smap.update((_read(WICS, {}) or {}).get('mapping', {}) or {})
    for e in (_read(WICS_ALL, []) or []):
        c = e.get('code')
        v = e.get('sub_sector') or e.get('sector')
        if c and v and not smap.get(c):
            smap[c] = v
    try:
        import csv
        with io.open(os.path.join(REPO, UNIVERSE_CSV), encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                tk = (r.get('티커') or '').strip()
                v = (r.get('섹터') or '').strip()
                if ':' in tk and v:
                    c = tk.split(':')[1]
                    if c.isdigit() and not smap.get(c):
                        smap[c] = v
    except Exception:
        pass
    for e in (_read(STOCK_MASTER, []) or []):
        if isinstance(e, dict):
            c, v = e.get('code'), e.get('sector')
            if c and v and not smap.get(c):
                smap[c] = v
    return smap


def load_price_history():
    """code -> {name, highs{d:v}, closes{d:v}} — 거래일만. KIS 가 yfinance 를 덮어쓴다."""
    merged = {}
    for path in (YF_HIST, KIS_HIST):
        h = _read(path, {}) or {}
        for code, st in (h.get('stocks') or {}).items():
            m = merged.setdefault(code, {'name': '', 'highs': {}, 'closes': {}})
            if st.get('name'):
                m['name'] = st['name']
            for key in ('highs', 'closes'):
                for dt, v in (st.get(key) or {}).items():
                    if v and is_session(dt):
                        m[key][dt] = v
    return merged


def load_records():
    """거래일 레코드만, 날짜->타입->순위정렬 리스트로."""
    recs = _read(FEATURED, []) or []
    by = defaultdict(lambda: defaultdict(list))
    for r in recs:
        d = r.get('d', '')
        if not is_session(d):
            continue
        by[d][r.get('type')].append(r)
    for d in by:
        for t in by[d]:
            by[d][t].sort(key=lambda x: (x.get('rank', 0), -x.get('mktcap', 0)))
    return by


def ranked_codes(by, d, t, n=30):
    if not d:
        return []
    return [r['code'] for r in by.get(d, {}).get(t, [])[:n]]


def build_insights(by, dates, i, wics, watch_codes, hist, hist_dates):
    """dates[i] 기준 인사이트. 과거 참조는 dates[:i] 만 쓴다."""
    d = dates[i]
    prev = dates[i - 1] if i > 0 else None
    day = by[d]
    out = {}
    name = {}
    for t in day:
        for r in day[t]:
            name[r['code']] = r['name']

    # (1) 신고가 온도 — 오늘 건수와 최근 20거래일 중앙값
    counts = [len(by[dd].get('newhigh_20d', [])) for dd in dates[max(0, i - STREAK_WINDOW):i]]
    hist_sorted = sorted(counts)
    median = hist_sorted[len(hist_sorted) // 2] if hist_sorted else 0
    nh20 = day.get('newhigh_20d', [])
    # lookback 필드는 2026-08-04 패치 이후 레코드에만 있다. 없는 것을 '완전'으로 세면
    # 이력이 짧은 종목까지 100%로 보고하게 된다 - 모집단을 필드 있는 것으로 한정한다.
    known = [r for r in nh20 if r.get('history_complete') is not None]
    complete = sum(1 for r in known if r.get('history_complete'))
    # 종가 안착 — 종가가 직전 20거래일 고가 최댓값을 넘었는가(장중 터치와 구분)
    prior = [x for x in hist_dates if x < d][-NH_WINDOW:]
    anchored = evaluated = 0
    if len(prior) >= NH_WINDOW:
        for r in nh20:
            st = hist.get(r['code'])
            px = r.get('price')
            if not st or not px:
                continue
            win = [st['highs'][x] for x in prior if x in st['highs']]
            if len(win) < NH_WINDOW:
                continue
            evaluated += 1
            if px > max(win):
                anchored += 1
    out['temp'] = {
        'nh20': len(nh20),
        'nh120': len(day.get('newhigh_120d', [])),
        'nh52': len(day.get('newhigh_52w', [])),
        'median20': median,
        'ratio': round(len(nh20) / float(median), 1) if median else None,
        'complete_ratio': round(100.0 * complete / len(known), 1) if known else None,
        'anchored': anchored, 'evaluated': evaluated,
        'anchor_rate': round(100.0 * anchored / evaluated, 1) if evaluated else None,
    }

    # (2) 거래대금 TOP30 신규 진입·이탈 + 순위 변화
    cur = ranked_codes(by, d, 'absolute')
    pre = ranked_codes(by, prev, 'absolute')
    pre_rank = {c: n + 1 for n, c in enumerate(pre)}
    entered, moved = [], []
    for n, c in enumerate(cur):
        if c not in pre_rank:
            entered.append({'code': c, 'name': name.get(c, c), 'rank': n + 1})
        else:
            delta = pre_rank[c] - (n + 1)
            if abs(delta) >= 5:
                moved.append({'code': c, 'name': name.get(c, c), 'rank': n + 1, 'delta': delta})
    pre_name = {r['code']: r['name'] for r in by.get(prev, {}).get('absolute', [])} if prev else {}
    cur_set = set(cur)
    exited = [{'code': c, 'name': pre_name.get(c, c), 'prev_rank': pre_rank[c]}
              for c in pre if c not in cur_set]
    moved.sort(key=lambda x: -abs(x['delta']))
    # TOP30 경계 완충 — 전일 30위/오늘 29위를 오가는 잡음을 헤드라인에서 뺀다
    cur_top = ranked_codes(by, d, 'absolute', STRONG_RANK)
    pre_top = set(ranked_codes(by, prev, 'absolute', STRONG_RANK))
    pre_set, cur_set2 = set(pre), set(cur)
    strong_in = [{'code': c, 'name': name.get(c, c), 'rank': cur.index(c) + 1}
                 for c in cur_top if c not in pre_set]
    strong_out = [{'code': c, 'name': pre_name.get(c, c), 'prev_rank': pre_rank[c]}
                  for c in pre if c in pre_top and c not in cur_set2]
    out['flow'] = {'prev': prev, 'entered': entered, 'exited': exited, 'moved': moved[:6],
                   'strong_in': strong_in, 'strong_out': strong_out, 'strong_rank': STRONG_RANK}

    # (3) 회전율 TOP30 연속 등장 — 거래대금 기준은 대형주가 상시 등장해 변별력이 없다
    window = dates[max(0, i - STREAK_WINDOW + 1):i + 1]
    member = {dd: set(ranked_codes(by, dd, 'turnover')) for dd in window}
    streak = []
    for c in ranked_codes(by, d, 'turnover'):
        n = 0
        for dd in reversed(window):
            if c in member[dd]:
                n += 1
            else:
                break
        if n >= 3:
            streak.append({'code': c, 'name': name.get(c, c), 'days': n,
                           'capped': n == len(window)})
    streak.sort(key=lambda x: -x['days'])
    out['streak'] = {'window': len(window), 'items': streak[:10]}

    # (4) 업종 쏠림 — 오늘 20일 신고가 업종 분포 vs 직전 5거래일 평균
    today_sec = Counter(wics.get(r['code'], '기타') for r in nh20)
    sec_members = defaultdict(list)
    for r in nh20:
        sec_members[wics.get(r['code'], '기타')].append(r)
    for v in sec_members.values():
        v.sort(key=lambda x: -(x.get('mktcap') or 0))
    base = Counter()
    base_days = dates[max(0, i - 5):i]
    for dd in base_days:
        for r in by[dd].get('newhigh_20d', []):
            base[wics.get(r['code'], '기타')] += 1
    base_total = sum(base.values())
    today_total = len(nh20) or 1
    tilt = []
    for sec_name, cnt in today_sec.items():
        avg = round(base[sec_name] / len(base_days), 1) if base_days else 0.0
        # 전체 건수가 통째로 늘어난 날에도 신호가 남도록 '비중'으로 본다
        share = 100.0 * cnt / today_total
        share_base = (100.0 * base[sec_name] / base_total) if base_total else 0.0
        ratio = (share / share_base) if share_base else None
        mem = sec_members.get(sec_name, [])
        tilt.append({'sector': sec_name, 'today': cnt, 'base': avg,
                     'share': round(share, 1), 'share_base': round(share_base, 1),
                     'ratio': round(ratio, 2) if ratio is not None else None,
                     'names': [x['name'] for x in mem[:3]],
                     'more': max(0, len(mem) - 3)})
    tilt.sort(key=lambda x: -x['share'])
    out['tilt'] = {'reliable': len(nh20) >= TILT_MIN_SAMPLE, 'total': len(nh20),
                   'sectors': len(today_sec), 'items': tilt}

    # (5) 보유·관심 레이더 — 이례 타입에 걸린 것만
    radar = []
    for c in watch_codes:
        types = sorted(t for t in day if t in NOTABLE_TYPES
                       and any(r['code'] == c for r in day[t]))
        if types:
            radar.append({'code': c, 'name': name.get(c, c), 'types': types})
    # 하방 예외 — 보유·관심 종목의 20거래일 종가 신저가(상방 이벤트만 보던 편향 보정)
    low20 = []
    if len(prior) >= NH_WINDOW:
        for c in watch_codes:
            st = hist.get(c)
            if not st:
                continue
            px = st['closes'].get(d)
            win = [st['closes'][x] for x in prior if x in st['closes']]
            if px is None or len(win) < NH_WINDOW:
                continue
            if px < min(win):
                low20.append(c)
    seen_codes = {x['code'] for x in radar}
    for c in low20:
        hit = next((x for x in radar if x['code'] == c), None)
        if hit:
            hit['types'] = hit['types'] + ['low20']
        else:
            radar.append({'code': c, 'name': (hist.get(c) or {}).get('name') or c,
                          'types': ['low20']})
    radar.sort(key=lambda x: (0 if 'low20' in x['types'] else 1, -len(x['types'])))
    out['radar'] = {'watch_total': len(watch_codes), 'items': radar, 'low20': len(low20)}
    return out


def main():
    os.chdir(REPO)
    by = load_records()
    dates = sorted(by)
    if not dates:
        print('featured_data.json 에 거래일 레코드가 없다')
        return 1
    wics = load_sector_map()
    hist = load_price_history()
    hist_dates = sorted({x for st in hist.values() for x in st['highs']})
    news = _read(NEWS, {}) or {}
    nh_detail = _read(NEWHIGH, {}) or {}
    themes = {}
    if nh_detail.get('date'):
        themes = {s.get('code'): s.get('theme')
                  for s in nh_detail.get('stocks', []) if s.get('theme')}
    wl = _read(WATCHLISTS, []) or []
    watch_codes, watch_groups = [], []
    for g in wl:
        codes = list(g.get('codes') or [])
        watch_groups.append({'name': g.get('name', ''), 'n': len(codes)})
        for c in codes:
            if c not in watch_codes:
                watch_codes.append(c)

    shard_set = set(dates[-SHARD_DAYS:])
    manifest_dates = []
    for i, d in enumerate(dates):
        if d not in shard_set:
            continue
        day = by[d]
        tables = {}
        for t, _title in RANK_TYPES:
            tables[t] = [{'rank': r.get('rank'), 'code': r['code'], 'name': r['name'],
                          'market': r.get('market'), 'sector': wics.get(r['code'], ''),
                          'trdval': r.get('trdval'), 'mktcap': r.get('mktcap'),
                          'turnover': r.get('turnover'), 'chg': r.get('chg')}
                         for r in day.get(t, [])[:30]]
        newhigh = {}
        for t in NH_TYPES:
            rows = sorted(day.get(t, []), key=lambda x: -(x.get('mktcap') or 0))
            newhigh[t] = [{'code': r['code'], 'name': r['name'], 'market': r.get('market'),
                           'sector': wics.get(r['code'], ''), 'mktcap': r.get('mktcap'),
                           'chg': r.get('chg'),
                           'theme': themes.get(r['code'], '') if d == nh_detail.get('date') else '',
                           'lookback_used': r.get('lookback_used'),
                           'lookback_target': r.get('lookback_target'),
                           'history_complete': r.get('history_complete')}
                          for r in rows]
        payload = {'schema': 2, 'date': d, 'tables': tables, 'newhigh': newhigh,
                   'insights': build_insights(by, dates, i, wics, watch_codes, hist, hist_dates)}
        if news.get('date') == d:
            payload['summaries'] = news.get('summaries', {})
            payload['summary_scope'] = news.get('summary_scope')
        payload['revision'] = _rev(payload)
        size = _write(_out('daily', d + '.json'), payload)
        manifest_dates.append({'d': d, 'revision': payload['revision'], 'bytes': size})

    series = [{'d': d,
               'nh20': len(by[d].get('newhigh_20d', [])),
               'nh120': len(by[d].get('newhigh_120d', [])),
               'nh52': len(by[d].get('newhigh_52w', [])),
               'top10': sum(r.get('trdval') or 0 for r in by[d].get('absolute', [])[:10])}
              for d in dates]
    _write(_out('meta', 'series.json'), {'schema': 2, 'points': series})

    now = datetime.now(tz=KST)
    manifest = {'schema': 2, 'generated_at': now.isoformat(), 'latest': dates[-1],
                'sessions': len(dates), 'shards': manifest_dates,
                'watch_groups': watch_groups,
                'newhigh_detail_date': nh_detail.get('date'),
                'themes_enriched_at': nh_detail.get('themes_enriched_at')}
    # 샤드를 먼저 쓰고 manifest 를 마지막에 — 브라우저가 없는 샤드를 가리키지 않게
    _write(_out('meta', 'manifest.json'), manifest)

    base_js = "{base: '', daily: 'featured_v2_d_', meta: 'featured_v2_'}" if FLAT         else "{base: 'featured_v2/', daily: 'featured_v2/daily/', meta: 'featured_v2/'}"
    html = (HTML.replace('__NAV__', nav_html('market', 'featured') + sidebar_html('featured'))
                .replace('__NAVCSS__', AOE_NAV_CSS + SIDEBAR_CSS)
                .replace('__PALETTE__', PALETTE_CSS_VARS)
                .replace('__PATHS__', base_js)
                .replace('__TOKENS__', aoe_tokens_css())
                .replace('__PRETENDARD__', PRETENDARD_LINK_LOCAL)
                .replace('__UPDATED__', now.strftime('%Y-%m-%d %H:%M:%S KST')))
    with io.open(os.path.join(REPO, OUT_HTML), 'w', encoding='utf-8') as f:
        f.write(html)
    total = sum(m['bytes'] for m in manifest_dates)
    print('생성 완료: %s (%.0fKB)' % (OUT_HTML, os.path.getsize(os.path.join(REPO, OUT_HTML)) / 1024.0))
    print('  샤드 %d일 / 합계 %.1fMB / 최신 %s = %.0fKB'
          % (len(manifest_dates), total / 1048576.0, dates[-1], manifest_dates[-1]['bytes'] / 1024.0))
    print('  series.json %d포인트 (%d거래일)' % (len(series), len(dates)))
    return 0


HTML = r'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Featured</title>
__PRETENDARD__
<style>
__PALETTE__
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif; font-size: 1.05rem; background: var(--aoe-bg); color: #fff; }
header { padding: 20px 24px; margin: 0 0 24px; text-align: center; }
header h1 { margin: 0; font-size: 33px; color: #fff; font-weight: 700; }
.last-updated { margin-top: 10px; color: var(--aoe-muted); font-size: 15px; font-style: italic; }
.content { padding: 0 24px 24px; max-width: 1800px; margin: 0 auto; }
.section { background: var(--aoe-card); border: 1px solid var(--aoe-border); border-radius: 12px; padding: 24px; margin-bottom: 20px; }
.section h2 { color: #fff; padding: 8px 0; font-size: 0.95rem; text-align: center; }
.bar { display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 20px; font-size: 13px; }
.bar select { font-family: inherit; font-size: 14px; padding: 5px 10px; border: 1px solid var(--aoe-input-border); border-radius: 6px; background: var(--aoe-input-bg); color: #fff; }
.tables { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; }
@media (max-width: 1100px) { .tables { grid-template-columns: 1fr; } }
.tables > div { min-width: 0; }
.tables table { width: 100%; }
#newhighWrap { overflow-x: auto; }
#newhighWrap table { width: 100%; min-width: 1100px; }
__TOKENS__
table { width: auto; border-collapse: collapse; font-size: var(--aoe-t-font); font-variant-numeric: var(--aoe-t-num); --aoe-t-font: 16px; --aoe-t-head-font: 0.78rem; --aoe-t-pad-y: 6px; --aoe-t-pad-x: 6px; --aoe-t-head-weight: 600; margin: 0 auto; }
thead { background: var(--aoe-th-bg); }
th { padding: 8px var(--aoe-t-pad-x); text-align: center; vertical-align: middle; font-weight: var(--aoe-t-head-weight); color: var(--aoe-amber); font-size: var(--aoe-t-head-font); background: var(--aoe-th-bg); box-shadow: inset 0 calc(-1 * var(--aoe-t-head-underline)) 0 #000; }
td { padding: var(--aoe-t-pad-y) var(--aoe-t-pad-x); text-align: center; vertical-align: middle; color: #fff; }
th, td { border: 1px solid var(--aoe-muted); }
td.l { text-align: left; padding-left: calc(var(--aoe-t-pad-x) + 1ch); }
tbody tr:hover { background: var(--aoe-hover); }
.pos { color: var(--aoe-up); }
.neg { color: var(--aoe-down); }
.tabs { display: flex; justify-content: center; gap: 8px; margin: 0 auto 24px; }
.tab { padding: 9px 26px; cursor: pointer; font-weight: 600; font-size: 0.95rem; color: var(--aoe-muted); border: 1.5px solid var(--aoe-input-border); border-radius: 2px; background: var(--aoe-input-bg); }
.tab:hover { color: #fff; }
.tab.active { color: var(--aoe-nav-bg); background: var(--aoe-amber); border-color: var(--aoe-amber); font-weight: 700; }
.subtabs { display: flex; justify-content: center; gap: 8px; margin: 0 auto 20px; flex-wrap: wrap; }
.subtab { padding: 9px 26px; border: 1.5px solid var(--aoe-input-border); background: var(--aoe-input-bg); border-radius: 2px; font-size: 0.95rem; font-weight: 600; color: var(--aoe-muted); cursor: pointer; font-family: inherit; white-space: nowrap; }
.subtab:hover { color: #fff; }
.subtab.active { background: var(--aoe-amber); color: var(--aoe-nav-bg); border-color: var(--aoe-amber); font-weight: 700; }
.grp { display: none; }
.grp.active { display: block; }
.cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; align-items: stretch; }
@media (max-width: 900px) { .cards { grid-template-columns: 1fr; } }
.card { height: 100%; background: var(--aoe-card2); border: 1px solid var(--aoe-border); border-radius: 10px; padding: 16px; }
.card table { width: 100%; margin: 0 auto; }
.card h3 { font-size: 0.9rem; text-align: center; margin-bottom: 10px; color: var(--aoe-amber); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; max-width: 560px; margin: 0 auto; }
.chip { border: 1px solid var(--aoe-border); border-radius: 999px; padding: 3px 10px; font-size: 13px; background: var(--aoe-input-bg); color: #fff; }
.chip.out { background: transparent; color: var(--aoe-muted); }
.kpis { display: flex; gap: 18px; justify-content: center; align-items: flex-end; height: 56px; margin-bottom: 12px; }
.kpi { display: flex; flex-direction: column; align-items: center; }
.kv { font-size: 1.8rem; font-weight: 700; line-height: 1.1; color: #fff; }
.kl { font-size: 0.72rem; color: var(--aoe-muted); margin-top: 2px; }
.on { color: var(--aoe-hl2-fg); font-weight: 700; }
td.miss { color: var(--aoe-muted); }
th.split, td.split { border-left: 3px solid var(--aoe-muted); }
.notable-news { font-size: 13px; color: var(--aoe-text); line-height: 1.8; text-align: left; padding-left: calc(var(--aoe-t-pad-x) + 1ch); max-width: 720px; }
footer { text-align: center; padding: 24px; color: var(--aoe-muted); font-size: 14px; }
__NAVCSS__
</style>
</head>
<body class="has-sidebar">
__NAV__
<header>
  <h1>Featured</h1>
  <div class="last-updated">Built: __UPDATED__</div>
</header>
<div class="content">
  <div class="subtabs">
    <button class="subtab active" id="grpBtn0" onclick="switchGroup(0)">인사이트</button>
    <button class="subtab" id="grpBtn1" onclick="switchGroup(1)">시가총액</button>
    <button class="subtab" id="grpBtn2" onclick="switchGroup(2)">거래대금</button>
    <button class="subtab" id="grpBtn3" onclick="switchGroup(3)">상승률</button>
    <button class="subtab" id="grpBtn4" onclick="switchGroup(4)">신고가</button>
  </div>
  <div class="bar"><select id="dateSel" onchange="loadDate(this.value)"></select></div>

  <div id="grp0" class="grp active"><div class="section"><div class="cards" id="insightCards"></div></div></div>
  <div id="grp1" class="grp"><div class="section"><div class="tables" id="pair1"></div></div></div>
  <div id="grp2" class="grp"><div class="section"><div class="tables" id="pair0"></div></div></div>
  <div id="grp3" class="grp"><div class="section"><div class="tables" id="pair2"></div></div></div>
  <div id="grp4" class="grp"><div class="section"><div id="newhighWrap"></div></div></div>
</div>
<footer>Data source: KIS</footer>
<script>
var P = __PATHS__;
var RANKS = {absolute:'거래대금 TOP 30', turnover:'거래대금/시총 비율 TOP 30',
             kospi_cap:'코스피 시가총액 TOP 30', kosdaq_cap:'코스닥 시가총액 TOP 30',
             kospi_chg:'코스피 상승률 TOP 30', kosdaq_chg:'코스닥 상승률 TOP 30'};
var PAIRS = [['absolute','turnover'],['kospi_cap','kosdaq_cap'],['kospi_chg','kosdaq_chg']];
var NH = [['newhigh_20d','20일'],['newhigh_120d','120일'],['newhigh_52w','52주']];
var LABEL = {absolute:'거래대금', turnover:'회전율', kospi_chg:'상승률', kosdaq_chg:'상승률',
             newhigh_20d:'20일 신고가', newhigh_120d:'120일 신고가', newhigh_52w:'52주 신고가',
             low20:'20일 종가 신저가'};

function esc(s){ var d = document.createElement('div'); d.textContent = (s == null ? '' : s); return d.innerHTML; }
function fmtVal(v){
  v = v || 0;
  if (v >= 1e12){ var jo = Math.floor(v / 1e12), eok = Math.round((v % 1e12) / 1e8); return jo.toLocaleString() + '조 ' + eok.toLocaleString() + '억원'; }
  if (v >= 1e8) return Math.round(v / 1e8).toLocaleString() + '억원';
  return Math.round(v).toLocaleString();
}
function chg(v){
  v = (v == null ? 0 : v);
  var c = v > 0 ? 'pos' : (v < 0 ? 'neg' : '');
  return '<span class="' + c + '">' + (v > 0 ? '+' : '') + v.toFixed(1) + '%</span>';
}

function rankTable(t, rows){
  var isTurn = (t === 'turnover');
  var h = '<div><h2>' + esc(RANKS[t]) + '</h2><table><thead><tr><th>#</th><th>업종</th><th>종목</th><th>시장</th><th>거래대금</th>';
  if (isTurn) h += '<th>회전율</th>';
  h += '<th>시총</th><th>등락률</th></tr></thead><tbody>';
  rows.forEach(function(r, i){
    h += '<tr><td>' + (i + 1) + '</td><td>' + esc(r.sector) + '</td><td>' + esc(r.name) + '</td><td>' + esc(r.market) + '</td>';
    h += '<td>' + fmtVal(r.trdval) + '</td>';
    if (isTurn) h += '<td>' + (r.turnover || 0).toFixed(1) + '%</td>';
    h += '<td>' + fmtVal(r.mktcap) + '</td><td>' + chg(r.chg) + '</td></tr>';
  });
  return h + '</tbody></table></div>';
}

function card(title, body){
  return '<div class="card"><h3>' + esc(title) + '</h3>' + body + '</div>';
}
function kpi(v, label, on){
  return '<div class="kpi"><span class="kv' + (on ? ' on' : '') + '">' + v + '</span><span class="kl">' + esc(label) + '</span></div>';
}

function renderInsights(ins){
  var out = '';

  // 강조는 '평소와 다를 때'만 - 오늘 20일 신고가가 최근 중앙값의 1.5배 이상
  var t = ins.temp;
  var hot = (t.median20 > 0 && t.nh20 >= t.median20 * 1.5);
  out += card('신고가',
    '<div class="kpis">' + kpi(t.nh20, '20일 장중', hot)
      + kpi(t.evaluated ? t.anchored : '-', '20일 종가', false)
      + kpi(t.anchor_rate == null ? '-' : t.anchor_rate.toFixed(1) + '%', '안착률', false) + '</div>'
    + '<table><thead><tr><th>120일</th><th>52주</th><th>최근20일 중앙값</th><th>중앙값 대비</th><th>안착</th></tr></thead><tbody><tr>'
    + '<td>' + t.nh120 + '</td><td>' + t.nh52 + '</td><td>' + t.median20 + '</td>'
    + '<td>' + (t.ratio == null ? '-' : t.ratio.toFixed(1) + '배') + '</td>'
    + '<td>' + (t.evaluated ? t.anchored + '/' + t.evaluated : '-') + '</td>'
    + '</tr></tbody></table>');

  var f = ins.flow, si = f.strong_in || [], so = f.strong_out || [];
  var fh = '<table><thead><tr><th>진입</th><th>순위</th><th class="split">이탈</th><th>직전 순위</th></tr></thead><tbody>';
  var fn = Math.max(si.length, so.length);
  if (!fn) fh += '<tr><td colspan="4">없음</td></tr>';
  for (var fi = 0; fi < fn; fi++){
    var a = si[fi], b = so[fi];
    fh += '<tr>'
       + '<td>' + (a ? esc(a.name) : '') + '</td><td>' + (a ? a.rank + '위' : '') + '</td>'
       + '<td class="split">' + (b ? esc(b.name) : '') + '</td><td>' + (b ? b.prev_rank + '위' : '') + '</td>'
       + '</tr>';
  }
  out += card('거래대금 TOP' + (f.strong_rank || 20) + ' 강한 진입·이탈',
    '<div class="kpis">' + kpi(si.length, '진입', false) + kpi(so.length, '이탈', false) + '</div>'
    + fh + '</tbody></table>');

  var ti = ins.tilt;
  // 비중이 크게 뛴 업종만 강조 - 최대 2개
  var hi = {};
  ti.items.filter(function(x){ return x.today >= 5 && x.ratio != null && x.ratio >= 2; })
          .sort(function(a, b){ return b.ratio - a.ratio; })
          .slice(0, 2).forEach(function(x){ hi[x.sector] = 1; });
  var th = '<table><thead><tr><th>업종</th><th>종목</th><th>오늘</th><th>비중</th><th>직전5일 비중</th></tr></thead><tbody>';
  if (!ti.items.length) th += '<tr><td colspan="5">신고가 없음</td></tr>';
  ti.items.forEach(function(x){
    var on = hi[x.sector] ? ' class="on"' : '';
    var nm = (x.names || []).join(', ');
    if (x.more) nm += ' 외 ' + x.more;
    th += '<tr><td class="' + (hi[x.sector] ? 'on' : '') + '">' + esc(x.sector) + '</td>'
        + '<td class="l">' + esc(nm) + '</td>'
        + '<td>' + x.today + '</td>'
        + '<td' + on + '>' + x.share.toFixed(1) + '%</td>'
        + '<td>' + x.share_base.toFixed(1) + '%</td></tr>';
  });
  out += card(ti.reliable ? '업종 쏠림' : '업종 분포',
    '<div class="kpis">' + kpi(ti.total, '신고가', false) + kpi(ti.sectors, '업종', false) + '</div>'
    + th + '</tbody></table>');

  var r = ins.radar;
  var COLS = [['absolute', '거래대금'], ['turnover', '회전율'], ['chg', '상승률'],
              ['newhigh_20d', '20일'], ['newhigh_120d', '120일'], ['newhigh_52w', '52주'],
              ['low20', '신저가']];
  var rh = '<table><thead><tr><th>종목</th>';
  COLS.forEach(function(c){ rh += '<th>' + c[1] + '</th>'; });
  rh += '</tr></thead><tbody>';
  if (!r.items.length) rh += '<tr><td colspan="' + (COLS.length + 1) + '">해당 없음</td></tr>';
  r.items.forEach(function(x){
    var has = {};
    x.types.forEach(function(y){ has[y] = 1; if (y.indexOf('chg') >= 0) has['chg'] = 1; });
    var low = !!has['low20'];
    rh += '<tr><td class="' + (low ? 'on' : '') + '">' + esc(x.name) + '</td>';
    COLS.forEach(function(c){
      var hit = !!has[c[0]];
      rh += '<td class="' + (hit ? (c[0] === 'low20' ? 'on' : '') : 'miss') + '">' + (hit ? 'O' : 'X') + '</td>';
    });
    rh += '</tr>';
  });
  out += card('보유·관심 레이더',
    '<div class="kpis">' + kpi(r.items.length, '등장', false)
      + kpi(r.low20 || 0, '종가 신저가', (r.low20 || 0) > 0)
      + kpi(r.watch_total, '보유·관심', false) + '</div>'
    + rh + '</tbody></table>');

  document.getElementById('insightCards').innerHTML = out;
}

function renderNewhigh(d){
  var h = '<table><thead><tr><th>#</th>';
  NH.forEach(function(p){ h += '<th>업종</th><th>' + p[1] + '</th><th>시총</th><th>이력</th>'; });
  h += '</tr></thead><tbody>';
  var lens = NH.map(function(p){ return (d.newhigh[p[0]] || []).length; });
  var max = Math.max.apply(null, lens.concat([0]));
  for (var i = 0; i < max; i++){
    h += '<tr><td>' + (i + 1) + '</td>';
    NH.forEach(function(p){
      var r = (d.newhigh[p[0]] || [])[i];
      if (!r){ h += '<td></td><td></td><td></td><td></td>'; return; }
      var lb = (r.lookback_used == null) ? '-' : (r.lookback_used + '/' + r.lookback_target);
      h += '<td>' + esc(r.sector) + '</td><td>' + esc(r.name) + '</td><td>' + fmtVal(r.mktcap) + '</td><td>' + lb + '</td>';
    });
    h += '</tr>';
  }
  if (!max) h += '<tr><td colspan="13">신고가 없음</td></tr>';
  document.getElementById('newhighWrap').innerHTML = h + '</tbody></table>';
}

function render(d){
  renderInsights(d.insights);
  PAIRS.forEach(function(pr, i){
    document.getElementById('pair' + i).innerHTML = rankTable(pr[0], d.tables[pr[0]] || []) + rankTable(pr[1], d.tables[pr[1]] || []);
  });
  renderNewhigh(d);
}

function switchGroup(i){
  for (var k = 0; k < 5; k++){
    document.getElementById('grpBtn' + k).classList.toggle('active', k === i);
    document.getElementById('grp' + k).classList.toggle('active', k === i);
  }
}

function loadDate(d){
  fetch(P.daily + d + '.json', {cache: 'no-cache'})
    .then(function(r){ return r.json(); })
    .then(render);
}

fetch(P.meta + 'manifest.json', {cache: 'no-cache'})
  .then(function(r){ return r.json(); })
  .then(function(m){
    var sel = document.getElementById('dateSel');
    m.shards.slice().reverse().forEach(function(s){
      var o = document.createElement('option');
      o.value = s.d; o.textContent = s.d; sel.appendChild(o);
    });
    sel.value = m.latest;
    loadDate(m.latest);
  });
</script>
</body>
</html>
'''

if __name__ == '__main__':
    sys.exit(main())
