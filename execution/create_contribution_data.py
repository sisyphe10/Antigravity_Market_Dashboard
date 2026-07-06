"""
WRAP 종목별/업종별 일별 기여도(attribution) 데이터 생성 → contribution_data.json

기여도 정의 (calculate_wrap_nav.py 의 NAV 산식과 동일하게 재현):
  - 일별 종목 기여도(fraction) = 비중(직전 NEW 스냅샷, 날짜 '<' 엄격) × 일별등락 / 100
  - 종목 합 = 일별 포트폴리오 수익률 port_return(d)  → NAV 와 정합
  - 비중: NEW 시트 = '리밸런스일 완전 스냅샷'(미기재=0), ffill 금지
  - 일별등락: FinanceDataReader 종가 pct_change (종목 종가는 KIS==FDR, NAV와 동일)

출력 contribution_data.json (단위 bp):
  {
    "generated": "...", "unit": "bp",
    "portfolios": {
      "<상품명>": {
        "dates": ["YYYY-MM-DD", ...],
        "port_return": [fraction, ...],          # 일별 포트 수익률(검증/Cariño 연결용)
        "stocks": {
          "<코드>": {"name","sector","dh": bool,
                     "contrib": [bp,...], "weight": [%,...],   # dates 와 정렬
                     "runs": [{"start","end"|null,"i0","i1","owner"|null}, ...]}
        }
      }
    }
  }

runs = 보유 라운드(완전 청산 후 재진입 구분). NEW 스냅샷 비중>0 연속 구간에서 자동 감지.
  - start/end: 매수 스냅샷일 / 청산(비중 0) 스냅샷일 (진행 중이면 end=null)
  - i0/i1: dates 배열 내 이 라운드의 일별 기여 구간 (비중 적용 규칙 '직전 스냅샷 <'과 정합: buy < d <= sell)
  - owner: dh_codes.json tags 중 코드 일치 + 기간 겹침 첫 태그의 owner (레거시 codes = 전기간 DH)

검증: 누적 Π(1+port_return) 이 기준가 시트 NAV 비율과 일치하는지 포트·기간별 대조.
"""
import json
import os
import sys
from datetime import timezone, timedelta

import pandas as pd
import FinanceDataReader as fdr

sys.stdout.reconfigure(encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAV_FILE = os.path.join(BASE, 'Wrap_NAV.xlsx')
DH_FILE = os.path.join(BASE, 'dh_codes.json')
OUT_FILE = os.path.join(BASE, 'contribution_data.json')

# 단일 출처: execution/wrap_config.py (활성 상품만; 청산분 자동 제외)
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wrap_config
portfolio_config = wrap_config.contribution_portfolio_config()


def load_dh():
    """returns (tags: [{code, owner, start, end}], {code: name}).
    tags 항목의 start/end 는 Timestamp 또는 None(무제한). 레거시 codes 배열은 전기간 DH 태그로 변환."""
    if not os.path.exists(DH_FILE):
        return [], {}
    with open(DH_FILE, encoding='utf-8') as f:
        j = json.load(f)
    tags = []
    for t in j.get('tags', []):
        tags.append({
            'code': str(t['code']).zfill(6),
            'owner': t.get('owner', 'DH'),
            'scope': t.get('scope'),  # None=전 포트, 'GENERAL_OPEN' 등 wrap_config group id 또는 개별 nav_key
            'start': pd.Timestamp(t['start']) if t.get('start') else None,
            'end': pd.Timestamp(t['end']) if t.get('end') else None,
            '_hit': False,
        })
    for c in j.get('codes', []):
        tags.append({'code': str(c).zfill(6), 'owner': 'DH', 'scope': None, 'start': None, 'end': None, '_hit': False})
    names = {str(k).zfill(6): v for k, v in j.get('names', {}).items()}
    return tags, names


def snapshot_runs(s):
    """스냅샷 비중 시리즈(날짜 오름차순 index) → [{'buy': Ts, 'sell': Ts|None}].
    buy = 비중>0 첫 스냅샷일(매수 리밸런스), sell = 이후 비중 0 스냅샷일(청산 리밸런스), 진행 중이면 None."""
    runs, cur = [], None
    for d, v in s.items():
        if v > 0 and cur is None:
            cur = {'buy': d, 'sell': None}
        elif v == 0 and cur is not None:
            cur['sell'] = d
            runs.append(cur)
            cur = None
    if cur is not None:
        runs.append(cur)
    return runs


def tag_owner(tags, code, buy, sell, pf_scopes, pf_name=''):
    """코드 일치 + scope 일치(None=전 포트) + 기간 겹침(양끝 포함)인 태그의 owner.
    복수 적중 시 첫 태그 사용 + 경고 (모호한 태그 입력 감지). sell=None → 진행 중."""
    a1 = sell if sell is not None else pd.Timestamp.max
    hits = []
    for t in tags:
        if t['code'] != code:
            continue
        if t['scope'] is not None and t['scope'] not in pf_scopes:
            continue
        b0 = t['start'] if t['start'] is not None else pd.Timestamp.min
        b1 = t['end'] if t['end'] is not None else pd.Timestamp.max
        if buy <= b1 and b0 <= a1:
            t['_hit'] = True
            hits.append(t)
    if len(hits) > 1:
        print(f"   ! 경고: 태그 복수 적중 — {pf_name}/{code} 런({buy.date()}~{sell.date() if sell is not None else '진행중'})에 "
              f"owner {[h['owner'] for h in hits]} 겹침 → 첫 태그({hits[0]['owner']}) 사용")
    return hits[0]['owner'] if hits else None


def main():
    print("1. Wrap_NAV.xlsx 로드")
    xl = pd.read_excel(NAV_FILE, sheet_name=None)

    # --- NEW(비중) 전처리: calculate_wrap_nav.py 와 동일 ---
    df_w = xl['NEW'].copy()
    df_w = df_w.dropna(subset=['코드'])
    df_w['코드'] = df_w['코드'].astype(str).str.strip().str.split('.').str[0]
    df_w = df_w[df_w['코드'].str.lower() != 'nan']
    df_w['코드'] = df_w['코드'].str.zfill(6)
    df_w['날짜'] = pd.to_datetime(df_w['날짜'])

    # --- 종목명/업종 매핑 (Code 시트 우선, NEW 보완) ---
    code_df = xl['Code'].copy()
    code_df.columns = ['종목명', '종목코드', '시장', '업종'][:len(code_df.columns)]
    code_df['종목코드'] = code_df['종목코드'].astype(str).str.split('.').str[0].str.zfill(6)
    name_map = dict(zip(code_df['종목코드'], code_df['종목명']))
    sector_map = {k: (v if pd.notna(v) else None) for k, v in zip(code_df['종목코드'], code_df['업종'])}
    for _, r in df_w.iterrows():
        name_map.setdefault(r['코드'], str(r['종목']))
        if not sector_map.get(r['코드']) and pd.notna(r.get('업종')):
            sector_map[r['코드']] = str(r['업종'])

    dh_tags, dh_names = load_dh()
    # 태그 종목은 사용자 표기(dh_codes.json names) 우선 — Code 시트 옛이름(예 HSD엔진) 회피
    for c, nm in dh_names.items():
        name_map[c] = nm
    print(f"   - 라운드 태그: {[(t['code'], t['owner'], str(t['start'].date()) if t['start'] is not None else None, str(t['end'].date()) if t['end'] is not None else None) for t in dh_tags]}")

    # --- 종료일 컷오프 (KST 17시) : calculate_wrap_nav.py 와 동일 ---
    kst = timezone(timedelta(hours=9))
    now_kst = pd.Timestamp.now(tz=kst)
    today_kst = now_kst.normalize().tz_localize(None)
    end_date = today_kst if now_kst.hour >= 17 else today_kst - pd.Timedelta(days=1)

    # --- 가격(FDR) 수집 → 일별 등락(fraction) ---
    all_codes = sorted(df_w['코드'].unique())
    data_start = pd.Timestamp(min(c['start_date'] for c in portfolio_config.values())) - pd.Timedelta(days=10)
    print(f"2. FDR 종가 수집: {len(all_codes)}종목 (since {data_start.date()})")
    closes = {}
    miss = []
    for code in all_codes:
        try:
            d = fdr.DataReader(code, start=data_start)
            if not d.empty and 'Close' in d.columns:
                closes[code] = d['Close']
            else:
                miss.append(code)
        except Exception as e:
            miss.append(code)
            print(f"   ! {code} 실패: {e}")
    if miss:
        print(f"   - 가격 누락 {len(miss)}종목: {miss}")
    df_close = pd.DataFrame(closes).sort_index()
    df_close = df_close[~df_close.index.duplicated(keep='last')]
    df_change = df_close.pct_change()  # fraction

    # --- 검증용 기준가 ---
    nav = xl['기준가'].copy()
    nav['Date'] = pd.to_datetime(nav['Date'])
    nav = nav.set_index('Date')

    result = {'generated': now_kst.strftime('%Y-%m-%d %H:%M:%S KST'), 'unit': 'bp', 'portfolios': {}}
    validation = []

    print("3. 포트폴리오별 일별 기여도 계산")
    for pf_name, cfg in portfolio_config.items():
        sub = df_w[df_w['상품명'] == pf_name]
        if sub.empty:
            print(f"   - {pf_name}: NEW 데이터 없음, skip")
            continue
        start = pd.Timestamp(cfg['start_date'])
        w_table = sub.pivot_table(index='날짜', columns='코드', values='비중', aggfunc='last').fillna(0)
        calc_dates = df_change.index[(df_change.index > start) & (df_change.index <= end_date)]
        codes_pf = [c for c in w_table.columns if c in df_change.columns]

        contrib = {c: [] for c in codes_pf}   # bp
        weight = {c: [] for c in codes_pf}    # %
        port_return = []
        dates_out = []
        for d in calc_dates:
            past = w_table.index[w_table.index < d]
            wv = w_table.loc[past[-1]] if len(past) else None
            pr = 0.0
            for c in codes_pf:
                w = float(wv[c]) if (wv is not None and c in wv.index) else 0.0
                chg = df_change.loc[d, c]
                ctr = 0.0 if pd.isna(chg) else (w * chg / 100.0)  # fraction
                pr += ctr
                contrib[c].append(round(ctr * 10000.0, 4))  # bp
                weight[c].append(round(w, 4))
            port_return.append(round(pr, 10))
            dates_out.append(d.strftime('%Y-%m-%d'))

        # 이 포트가 속한 태그 scope 집합: 포트명(nav_key) + wrap_config group id
        pf_scopes = {pf_name}
        for p in wrap_config.PRODUCTS:
            if p.nav_key == pf_name and p.group:
                pf_scopes.add(p.group)

        # 기간 내 한 번도 비중이 없던 종목 제외
        cd = list(calc_dates)
        stocks = {}
        for c in codes_pf:
            if all(w == 0 for w in weight[c]):
                continue
            # 라운드(보유구간): 스냅샷 전체 이력에서 감지 → 기여도 창과 겹치는 것만 bake
            runs_snap = snapshot_runs(w_table[c])
            # 가짜 분리 방어: 런 사이 갭이 스냅샷 1개 이하면 경고 (순간 blip = 실수 기록 의심)
            for a, b in zip(runs_snap, runs_snap[1:]):
                gap = w_table.index[(w_table.index >= a['sell']) & (w_table.index < b['buy'])]
                if len(gap) <= 1:
                    print(f"   ! 경고: {pf_name}/{c} 런 갭이 스냅샷 {len(gap)}개 ({a['sell'].date()}→{b['buy'].date()}) — 실수 기록 의심")
            runs_out = []
            for r in runs_snap:
                i0 = next((i for i, d in enumerate(cd) if d > r['buy']), None)
                if r['sell'] is not None:
                    i1 = next((i for i in range(len(cd) - 1, -1, -1) if cd[i] <= r['sell']), None)
                else:
                    i1 = len(cd) - 1 if cd else None
                if i0 is None or i1 is None or i0 > i1:
                    continue  # 기여도 창과 안 겹치는 라운드
                runs_out.append({
                    'start': r['buy'].strftime('%Y-%m-%d'),
                    'end': r['sell'].strftime('%Y-%m-%d') if r['sell'] is not None else None,
                    'i0': i0, 'i1': i1,
                    'owner': tag_owner(dh_tags, c, r['buy'], r['sell'], pf_scopes, pf_name),
                })
            stocks[c] = {
                'name': name_map.get(c, c),
                'sector': sector_map.get(c) or '기타',
                'dh': any(rr['owner'] == 'DH' for rr in runs_out),
                'contrib': contrib[c],
                'weight': weight[c],
                'runs': runs_out,
            }
        result['portfolios'][pf_name] = {
            'dates': dates_out,
            'port_return': port_return,
            'stocks': stocks,
        }

        # --- 검증: 누적 Π(1+pr) vs 기준가 NAV 비율 ---
        if pf_name in nav.columns and len(dates_out):
            cum = 1.0
            for pr in port_return:
                cum *= (1 + pr)
            navs = nav[pf_name].dropna()
            try:
                nav_start = navs.loc[pd.Timestamp(cfg['start_date'])]  # 실제 시작일 종가(앵커 함정 회피)
                nav_last = navs.loc[pd.Timestamp(dates_out[-1])]
                nav_ratio = nav_last / nav_start
                diff_pp = (cum - nav_ratio) * 100.0
                validation.append((pf_name, len(dates_out), (cum - 1) * 100, (nav_ratio - 1) * 100, diff_pp))
            except KeyError:
                validation.append((pf_name, len(dates_out), (cum - 1) * 100, None, None))

    # 어떤 런과도 안 겹친 태그 경고 (오타·기간 어긋남 감지, 에러 아님)
    for t in dh_tags:
        if not t['_hit']:
            print(f"   ! 경고: 태그 미적중 — code={t['code']} owner={t['owner']} scope={t['scope']} "
                  f"{t['start'].date() if t['start'] is not None else None}~{t['end'].date() if t['end'] is not None else None}")

    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, separators=(',', ':'))
    sz = os.path.getsize(OUT_FILE) / 1024
    print(f"4. 저장: contribution_data.json ({sz:.0f} KB)")

    print("\n=== 정합성 검증 (기여도누적 vs 기준가) ===")
    print(f"{'포트폴리오':14s} {'일수':>4s} {'기여도누적%':>10s} {'기준가%':>9s} {'차이%p':>8s}")
    ok = True
    for pf, n, c, navr, diff in validation:
        if navr is None:
            print(f"{pf:14s} {n:>4d} {c:>10.2f} {'N/A':>9s} {'N/A':>8s}")
            continue
        flag = '' if abs(diff) < 0.5 else '  <-- 경고(>0.5%p)'
        if abs(diff) >= 0.5:
            ok = False
        print(f"{pf:14s} {n:>4d} {c:>10.2f} {navr:>9.2f} {diff:>+8.3f}{flag}")
    print("\n검증 결과:", "✅ 전 포트 정합(차이<0.5%p)" if ok else "⚠️ 불일치 포트 존재 → 원인 추적 필요")


if __name__ == '__main__':
    main()
