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
                     "contrib": [bp,...], "weight": [%,...]}   # dates 와 정렬
        }
      }
    }
  }

검증: 누적 Π(1+port_return) 이 기준가 시트 NAV 비율과 일치하는지 포트·기간별 대조.
DH 구분: dh_codes.json (코드 기준).
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

# calculate_wrap_nav.py 와 동일 (활성 포트폴리오만; 청산분은 주석 유지로 자동 제외)
portfolio_config = {
    '트루밸류':      {'base_price': 2021.31, 'start_date': '2025-12-30'},
    'Value ESG':     {'base_price': 1980.49, 'start_date': '2025-12-30'},
    '개방형 랩':     {'base_price': 1518.52, 'start_date': '2025-12-30'},
    '목표전환형 5차': {'base_price': 1000.00, 'start_date': '2026-06-12'},
    '목표전환형 4호': {'base_price': 1000.00, 'start_date': '2026-06-15'},
}


def load_dh():
    """returns (set(codes), {code: name})"""
    if not os.path.exists(DH_FILE):
        return set(), {}
    with open(DH_FILE, encoding='utf-8') as f:
        j = json.load(f)
    codes = set(str(c).zfill(6) for c in j.get('codes', []))
    names = {str(k).zfill(6): v for k, v in j.get('names', {}).items()}
    return codes, names


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

    dh_codes, dh_names = load_dh()
    # DH 종목은 사용자 표기(dh_codes.json names) 우선 — Code 시트 옛이름(예 HSD엔진) 회피
    for c, nm in dh_names.items():
        name_map[c] = nm
    print(f"   - DH 코드: {sorted(dh_codes)}")

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

        # 기간 내 한 번도 비중이 없던 종목 제외
        stocks = {}
        for c in codes_pf:
            if all(w == 0 for w in weight[c]):
                continue
            stocks[c] = {
                'name': name_map.get(c, c),
                'sector': sector_map.get(c) or '기타',
                'dh': c in dh_codes,
                'contrib': contrib[c],
                'weight': weight[c],
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
