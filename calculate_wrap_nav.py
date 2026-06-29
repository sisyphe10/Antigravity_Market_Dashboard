import pandas as pd
import FinanceDataReader as fdr
import numpy as np
import os
import sys

# Windows console encoding fix
sys.stdout.reconfigure(encoding='utf-8')

# 단일 출처 레지스트리 (execution/wrap_config.py)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'execution'))
import wrap_config

# ---------------------------------------------------------
# 1. 설정
# ---------------------------------------------------------
# ── 완료된 목표전환형 이력 ──────────────────────────────────────────
# 청산 임계값(수수료·성과급 차감 전 명목): NH 6.5% / DB 7.5%
#   (실 net 목표는 NH 5%, DB 6%로 명목 기준 위 1.5%p 버퍼)
# [1차 DB 목표전환형] 2026-02-11 ~ 2026-02-25
#   시작 기준가: 1,000.00 / 청산 기준가: ~1,079.98 (YTD +8.0%, 목표 7.5% 초과 달성)
#   2026-03-16 2차 설정 예정.
# [2차 DB 목표전환형] 2026-03-16 ~ 2026-04-15
#   시작 기준가: 1,000.00 / 목표수익률(7.5%) 달성으로 청산.
# [NH 목표전환형 1호] 2026-03-25 ~ 2026-04-15
#   시작 기준가: 1,000.00 / 목표수익률(6.5%) 달성으로 청산.
# [DB 목표전환형 3차] 2026-04-30 ~ 2026-05-06
#   시작 기준가: 1,000.00 / 청산 기준가: 1,079.70 (+7.97%, 목표 7.5% 초과 달성)
# [NH 목표전환형 2호] 2026-04-29 ~ 2026-05-06
#   시작 기준가: 1,000.00 / 청산 기준가: 1,072.64 (+7.26%, 목표 6.5% 초과 달성)
#   운용 개시 AUM: 237억원
# [NH 목표전환형 3호] 2026-05-14 ~ 2026-05-27 (목표달성, 청산)
#   시작 기준가: 1,000.00 / 청산 기준가: 확인 후 기입 (calculate_wrap_nav.py 실행 후 기준가 시트에서)
#   운용 개시 AUM: 240억원
# [DB 목표전환형 4차] 2026-05-18 ~ 2026-05-27 (목표달성, 청산)
#   시작 기준가: 1,000.00 / 청산 기준가: 확인 후 기입
# [DB 목표전환형 5차] 2026-06-12 ~ 2026-06-19 (목표달성, 청산)
#   시작 기준가: 1,000.00 / 청산 기준가: 1,077.21 (+7.72%, 목표 7.5% 초과 달성) / 운용 6거래일
# [NH 목표전환형 4호] 2026-06-15 ~ 2026-06-19 (목표달성, 청산)
#   시작 기준가: 1,000.00 / 청산 기준가: 1,053.79 (+5.38%, 장중 6.5% 터치 후 즉시 전량매도 잔여가) / 운용 5거래일
# ───────────────────────────────────────────────────────────────────

# 포트폴리오별 초기 기준가 및 시작일 — 단일 출처: execution/wrap_config.py (keep_in_nav 상품)
portfolio_config = wrap_config.nav_portfolio_config()
initial_base_prices = {k: v['base_price'] for k, v in portfolio_config.items()}
initial_start_date_str = min(cfg['start_date'] for cfg in portfolio_config.values())

# 시장 지수
indices = {
    'KOSPI': '^KS11',
    'KOSDAQ': '^KQ11'
}

file_name = 'Wrap_NAV.xlsx'

# ---------------------------------------------------------
# 2. 기존 데이터 확인 및 시작점 설정
# ---------------------------------------------------------
print("1. 기존 데이터 확인 중...")

if not os.path.exists(file_name):
    print(f"오류: '{file_name}' 파일이 없습니다.")
    exit()

df_dict = pd.read_excel(file_name, sheet_name=None)
df_old = pd.DataFrame()
is_update = False

# '기준가' 시트 확인
if '기준가' in df_dict:
    temp_df = df_dict['기준가']

    if temp_df.empty:
        print("   - '기준가' 시트가 비어있습니다. 처음부터 계산합니다.")
        is_update = False
    else:
        print("   - 기존 '기준가' 시트를 발견했습니다. 이어서 계산합니다.")
        df_old = temp_df.copy()

        # 날짜 인덱스 설정
        # 엑셀에서 읽어올 때 첫 번째 컬럼을 날짜로 인식하여 인덱스로 설정
        if 'Date' in df_old.columns:
            df_old['Date'] = pd.to_datetime(df_old['Date'])
            df_old = df_old.set_index('Date')
        else:
            df_old.index = pd.to_datetime(df_old.iloc[:, 0])
            df_old = df_old.iloc[:, 1:]

        last_date = df_old.index[-1]

        # 마지막 기준가 추출
        last_prices = {}
        for key in initial_base_prices.keys():
            if key in df_old.columns:
                last_prices[key] = df_old.iloc[-1][key]
            else:
                last_prices[key] = initial_base_prices[key]

        # ★ 중요: 이미 계산된 날짜의 다음 날부터 계산 시작
        start_date = last_date
        current_base_prices = last_prices
        is_update = True

        print(f"   - 마지막 기록일: {last_date.strftime('%Y-%m-%d')}")

# 초기화 필요 시
if not is_update:
    start_date = pd.Timestamp(initial_start_date_str)
    current_base_prices = initial_base_prices
    print(f"   - 계산 시작일: {start_date.strftime('%Y-%m-%d')}")

# 계산 종료일: KST 17시 이후면 당일 포함, 이전이면 전일까지.
#  ★ 17시 가드: KIS 확정 일봉(종가)이 안정적으로 들어오는 시각 이후에만 당일을 publish.
#    (구 15시 가드 + 16:00 잡 = 장 직후 잠정 종가가 기준가에 동결되던 한 원인 → 17시로 상향)
from datetime import timezone, timedelta as td
kst = timezone(td(hours=9))
now_kst = pd.Timestamp.now(tz=kst)
today_kst = now_kst.normalize().tz_localize(None)
if now_kst.hour >= 17:
    end_date = today_kst
else:
    end_date = today_kst - pd.Timedelta(days=1)

print(f"   - 계산 종료일(목표): {end_date.strftime('%Y-%m-%d')}")

# 신규 포트폴리오 확인 (기존 데이터에 없는 포트폴리오)
new_portfolios = []
if is_update:
    new_portfolios = [pf for pf in initial_base_prices.keys() if pf not in df_old.columns]

# 마지막 행에 NaN이 있는 포트폴리오도 미완료로 간주
incomplete_portfolios = []
if is_update and not new_portfolios:
    last_row = df_old.iloc[-1]
    for pf in initial_base_prices.keys():
        if pf in df_old.columns and pd.isna(last_row.get(pf)):
            # 청산(end_date) 회차는 청산일 이후 후행 NaN이 정상 → 미완료로 보지 않음
            # (그렇지 않으면 매 실행마다 미완료 플래그 → 롤백 루프).
            _ed = portfolio_config[pf].get('end_date')
            if _ed and pd.Timestamp(_ed) < df_old.index[-1]:
                continue
            incomplete_portfolios.append(pf)
    if incomplete_portfolios:
        # 마지막 행(NaN 포함)을 제거하고 그 전 날부터 재계산
        print(f"   - 미완료 포트폴리오 감지: {', '.join(incomplete_portfolios)}")
        df_old = df_old.iloc[:-1]
        last_date = df_old.index[-1]
        start_date = last_date
        last_prices = {}
        for key in initial_base_prices.keys():
            val = None
            if key in df_old.columns:
                valid = df_old[key].dropna()
                if not valid.empty:
                    val = valid.iloc[-1]
            if val is not None and not pd.isna(val):
                last_prices[key] = val
            else:
                last_prices[key] = initial_base_prices[key]
        current_base_prices = last_prices

# ── 잠정 종가 자가복구 (Fix A) ─────────────────────────────
# 자동 업데이트가 장중/마감직후(잠정) 종가로 한 행을 기록하면 아래 combine_first가
# 그 값을 영구 동결한다(지수·NAV 공통). 신규 포트폴리오가 없는 일반 일일 실행에서는
# 최근 RECOMPUTE_WINDOW 거래일을 다시 계산하도록 마지막 행들을 롤백해, 확정 종가
# 확보 후 실행이 잠정값을 덮어쓰도록 한다.
#   · 늦은-추가 훼손버그 방지(start_date 롤백금지)는 new_portfolios가 있을 때만
#     필요하므로 그 경우는 건드리지 않는다.
#   · 어떤 포트폴리오의 개시(시드) 행도 절대 지우지 않도록 latest_start로 cap.
RECOMPUTE_WINDOW = 3
if is_update and not new_portfolios and not incomplete_portfolios and len(df_old) > 1:
    latest_start = max(
        (pd.Timestamp(portfolio_config[pf]['start_date'])
         for pf in portfolio_config if pf in df_old.columns),
        default=df_old.index[0],
    )
    cut_idx = df_old.index[-RECOMPUTE_WINDOW] if len(df_old) > RECOMPUTE_WINDOW else df_old.index[0]
    rollback_floor = max(cut_idx, latest_start)  # 개시행 보존
    keep = df_old[df_old.index <= rollback_floor]
    if 1 <= len(keep) < len(df_old):
        dropped = len(df_old) - len(keep)
        df_old = keep
        last_date = df_old.index[-1]
        start_date = last_date
        last_prices = {}
        for key in initial_base_prices.keys():
            val = None
            if key in df_old.columns:
                valid = df_old[key].dropna()
                if not valid.empty:
                    val = valid.iloc[-1]
            last_prices[key] = val if (val is not None and not pd.isna(val)) else initial_base_prices[key]
        current_base_prices = last_prices
        print(f"   - [Fix A] 최근 {dropped}거래일 재계산 롤백 "
              f"(start={start_date.strftime('%Y-%m-%d')}, floor={rollback_floor.strftime('%Y-%m-%d')})")

if start_date >= end_date and not new_portfolios and not incomplete_portfolios:
    print("\n✅ 이미 최신 데이터까지 업데이트되어 있습니다. (종료)")
    exit()

# 신규 포트폴리오가 있으면 '데이터 수집 시작일'만 앞당긴다 (start_date 자체는 롤백 금지).
# ★ start_date를 롤백하면 last_date보다 과거에 개시한 포트폴리오를 뒤늦게 추가할 때
#    기존 포트폴리오가 겹치는 날짜를 잘못된 베이스(마지막 행)로 재계산하고, 신규 row가
#    기존 컬럼을 NaN으로 덮어써서 published 기준가가 훼손된다. 신규 컬럼은 아래 per-pf
#    로직이 pf_config_start 기준으로 독립 계산하므로 데이터만 충분히 수집하면 된다.
data_start_date = start_date
if new_portfolios:
    earliest_new_start = min(pd.Timestamp(portfolio_config[pf]['start_date']) for pf in new_portfolios)
    if earliest_new_start < data_start_date:
        data_start_date = earliest_new_start
    print(f"   - 신규 포트폴리오 감지: {', '.join(new_portfolios)} (데이터 수집 시작 {data_start_date.strftime('%Y-%m-%d')})")

# ---------------------------------------------------------
# 3. 비중 데이터 전처리
# ---------------------------------------------------------
target_sheet = 'NEW' if 'NEW' in df_dict.keys() else list(df_dict.keys())[0]
df_weights = df_dict[target_sheet].copy()

df_weights = df_weights.dropna(subset=['코드'])
df_weights['코드'] = df_weights['코드'].astype(str).str.strip()
df_weights = df_weights[df_weights['코드'].str.lower() != 'nan']
df_weights['코드'] = df_weights['코드'].str.zfill(6)
df_weights['날짜'] = pd.to_datetime(df_weights['날짜'])

# ---------------------------------------------------------
# 4. 데이터 수집
# ---------------------------------------------------------
all_codes = df_weights['코드'].unique()
print(f"2. 데이터 수집 (기간: {data_start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')})")

# 4-1. 개별 종목 — KIS 확정 일봉(종가) 우선, 실패 종목만 FDR 폴백.
#  ★ 근본원인 수정: 기존 FDR 'Change'는 장 직후 당일 봉이 잠정 → 16:00 publish 시 NAV 잠정 반영.
#    KIS 일봉(inquire-daily-itemchartprice)은 장 마감 후 KRX 확정 종가 → close.pct_change()로 등락률 산출
#    (= FDR 'Change'와 동일 의미, KIS==FDR-final 전 구간 일치 검증 완료).
df_change = pd.DataFrame()
_start_ymd = pd.Timestamp(data_start_date).strftime('%Y%m%d')
_end_ymd = pd.Timestamp(end_date).strftime('%Y%m%d')
kis_closes = {}
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'execution'))
    import kis_token as _kt
    kis_closes = _kt.fetch_daily_closes(list(all_codes), _start_ymd, _end_ymd)
    print(f"   - KIS 확정 일봉 수집: {len(kis_closes)}/{len(all_codes)}종목")
except Exception as e:
    print(f"   - KIS 일봉 수집 불가({e}) → 전 종목 FDR 폴백")

_fdr_fallback = 0
for code in all_codes:
    s = None
    ck = str(code).zfill(6)
    if ck in kis_closes and len(kis_closes[ck]) >= 2:
        s = pd.Series(kis_closes[ck])
        s.index = pd.to_datetime(s.index)
        s = s.sort_index()
    if s is None or len(s) < 2:
        try:
            d = fdr.DataReader(code, start=data_start_date)
            if not d.empty:
                s = d['Close']
                _fdr_fallback += 1
        except Exception:
            s = None
    if s is not None and len(s) >= 2:
        df_change[code] = s.pct_change()
if _fdr_fallback:
    print(f"   - FDR 폴백 종목: {_fdr_fallback}개")

# 4-2. 시장 지수 (KIS 일자별 확정지수 → 네이버 금융 → FDR 폴백)
print("   - KOSPI, KOSDAQ 지수 수집 중...")
df_indices = pd.DataFrame()

def _fetch_naver_index(code, pages=15):
    """네이버 금융 일별 시세에서 지수 종가 수집"""
    import requests
    from bs4 import BeautifulSoup
    rows = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    for page in range(1, pages + 1):
        try:
            url = f'https://finance.naver.com/sise/sise_index_day.naver?code={code}&page={page}'
            r = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            for tr in soup.select('table.type_1 tr'):
                tds = tr.select('td')
                if len(tds) >= 2:
                    try:
                        date = pd.to_datetime(tds[0].text.strip())
                        close = float(tds[1].text.strip().replace(',', ''))
                        rows.append({'Date': date, 'Close': close})
                    except:
                        pass
        except:
            break
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows).drop_duplicates('Date').set_index('Date').sort_index()
    return df['Close']

def _fetch_kis_index(iscd, start):
    """KIS 국내업종 일자별지수 확정 종가 → pd.Series(start 이후).
    거래소 공식 확정 종가라 장중/마감직후 잠정값을 회피한다.
    1콜당 최근 100거래일 반환 → start까지 FID_INPUT_DATE_1 날짜 페이징."""
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'execution'))
    import kis_token
    PATH = '/uapi/domestic-stock/v1/quotations/inquire-index-daily-price'
    TRID = 'FHPUP02120000'
    start_ts = pd.Timestamp(start)
    rows = {}
    cursor = pd.Timestamp(end_date)
    for _ in range(8):  # 최대 8콜(=800거래일) 안전상한
        params = {'FID_COND_MRKT_DIV_CODE': 'U', 'FID_INPUT_ISCD': iscd,
                  'FID_INPUT_DATE_1': cursor.strftime('%Y%m%d'), 'FID_PERIOD_DIV_CODE': 'D'}
        j = kis_token.kis_get(PATH, tr_id=TRID, params=params)
        got = []
        for r in (j.get('output2') or []):
            d = r.get('stck_bsop_date'); c = r.get('bstp_nmix_prpr')
            if not d or c in (None, '', '0'):
                continue
            try:
                got.append((pd.to_datetime(d), float(c)))
            except Exception:
                pass
        if not got:
            break
        for d, c in got:
            rows[d] = c
        earliest = min(d for d, _ in got)
        if earliest <= start_ts:
            break
        cursor = earliest - pd.Timedelta(days=1)
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series(rows).sort_index()
    return s[s.index >= start_ts]

KIS_ISCD = {'KOSPI': '0001', 'KOSDAQ': '1001'}
naver_codes = {'KOSPI': 'KOSPI', 'KOSDAQ': 'KOSDAQ'}
for name in indices:
    s = pd.Series(dtype=float)
    # 1순위: KIS 일자별 확정 종가 (거래소 공식, 잠정값 회피)
    if name in KIS_ISCD:
        try:
            s = _fetch_kis_index(KIS_ISCD[name], data_start_date)
            if not s.empty:
                df_indices[name] = s
                print(f"     {name}: KIS ({len(s)}일)")
        except Exception as e:
            print(f"     {name}: KIS 실패 ({e}), 네이버 시도...")
    # 2순위: 네이버 금융
    if s.empty:
        try:
            s = _fetch_naver_index(naver_codes[name])
            if not s.empty:
                df_indices[name] = s
                print(f"     {name}: 네이버 금융 ({len(s)}일)")
        except Exception as e:
            print(f"     {name}: 네이버 실패 ({e}), FDR 시도...")
    # 3순위: FDR
    if s.empty:
        try:
            d = fdr.DataReader(indices[name], start=data_start_date)
            if not d.empty:
                df_indices[name] = d['Close']
                print(f"     {name}: FDR ({len(d)}일)")
        except Exception:
            pass

if df_change.empty:
    print("\n[알림] 새로 계산할 종목 가격 변동 데이터가 없습니다 (새 거래일 없음 또는 수집 실패). 기존 데이터 보존, 종료.")
    exit()

df_change = df_change.fillna(0)
df_change = df_change[df_change.index <= end_date]

if not df_indices.empty:
    df_indices = df_indices[df_indices.index <= end_date]

# ★ [핵심 수정] 시작일(start_date) 당일은 제외하고, 그 다음 날부터 수익률 계산
calc_dates = df_change.index[df_change.index > start_date]

if len(calc_dates) == 0 and not new_portfolios:
    print("\n✅ 업데이트할 거래일이 없습니다. (종료)")
    exit()

# ---------------------------------------------------------
# 5. 기준가 계산
# ---------------------------------------------------------
print("3. 추가분 기준가 계산 중...")

new_pf_results = {}

for pf_name, start_price in current_base_prices.items():
    sub_df = df_weights[df_weights['상품명'] == pf_name]
    if sub_df.empty: continue

    # 포트폴리오별 시작일 및 계산 대상 날짜 결정
    pf_config_start = pd.Timestamp(portfolio_config[pf_name]['start_date'])
    is_new_portfolio = is_update and pf_name not in df_old.columns

    # 청산(end_date) 회차는 청산일까지만 계산 (이후 날짜 미생성 → 죽은 회차 연장 방지).
    pf_config_end = portfolio_config[pf_name].get('end_date')
    pf_end = min(end_date, pd.Timestamp(pf_config_end)) if pf_config_end else end_date

    if is_new_portfolio:
        # 신규 포트폴리오: 설정된 시작일 기준
        pf_start_date = pf_config_start
        pf_calc_dates = df_change.index[(df_change.index > pf_config_start) & (df_change.index <= pf_end)]
    else:
        # 기존 포트폴리오: 기존 데이터 이후부터
        pf_start_date = start_date
        pf_calc_dates = calc_dates[calc_dates <= pf_end]

    # ★ 비중 = '리밸런스일 완전 스냅샷' (NEW 시트 한 날짜 = 그 시점 전체 포트폴리오, 편출종목은 미기재=0).
    #   과거 reindex(calc_dates).ffill()는 편출된 종목의 옛 비중을 영구히 되살려(resurrect)
    #   비중합 100% 초과·NAV 왜곡 유발 → 2026-03-23 수동→자동 전환 후 기준가 오염의 주원인.
    #   따라서 ffill 금지: pivot 후 미기재 종목만 0으로 채우고(fillna), 각 리밸런스일 행을 그대로 사용.
    w_table = sub_df.pivot_table(index='날짜', columns='코드', values='비중', aggfunc='last').fillna(0)

    idx_list = []
    date_list = []

    # 처음 생성 시 또는 신규 포트폴리오: 시작일(T=0) 초기값 기록
    if not is_update or is_new_portfolio:
        idx_list.append(start_price)
        date_list.append(pf_start_date)

    current_index = start_price

    for d in pf_calc_dates:
        # 전일(d-1)까지 유효했던 비중 찾기.
        # 엄격한 '<' 필수: '<='로 바꾸면 당일 NEW 시트에 추가된 새 비중으로 당일 NAV가
        # 계산되어 룩어헤드 버그 발생 (자문 워크플로상 오늘 변경은 다음 거래일부터 적용).
        past_dates = w_table.index[w_table.index < d]

        if len(past_dates) == 0:
            port_return = 0
        else:
            eff_date = past_dates[-1]
            weights = w_table.loc[eff_date]
            valid_cols = weights.index.intersection(df_change.columns)

            if len(valid_cols) == 0:
                port_return = 0
            else:
                today_change = df_change.loc[d, valid_cols]
                w_vec = weights[valid_cols]
                port_return = (w_vec * today_change).sum() / 100

        current_index = current_index * (1 + port_return)
        idx_list.append(current_index)
        date_list.append(d)

    new_pf_results[pf_name] = pd.Series(idx_list, index=date_list)

# ---------------------------------------------------------
# 6. 결과 병합 및 저장
# ---------------------------------------------------------
print("4. 결과 병합 및 저장 중...")

if new_pf_results:
    df_new_pf = pd.DataFrame(new_pf_results)

    # 지수 병합
    df_new_combined = df_new_pf.join(df_indices, how='left')
    df_new_combined.index.name = 'Date'

    if is_update:
        # 컬럼 인지 병합: 기존(df_old) 값은 보존하고 신규 컬럼·신규 행(df_old가 NaN/없음)만 채운다.
        # 단순 concat+dedup(keep=last)은 신규 포트폴리오의 과거 row가 기존 컬럼을 NaN으로
        # 덮어써 published 기준가를 훼손하므로 combine_first 사용 (미완료 마지막 행은 위에서
        # df_old.iloc[:-1]로 제거되므로 그 날짜는 df_new가 채움 → 정상 갱신).
        df_final = df_old.combine_first(df_new_combined)
        ordered = list(df_old.columns) + [c for c in df_final.columns if c not in df_old.columns]
        df_final = df_final[ordered].sort_index()
    else:
        df_final = df_new_combined

    # 소수점 둘째 자리 반올림
    df_final = df_final.round(2)

    # DatetimeIndex를 'YYYY-MM-DD' 문자열 형식으로 변환
    if not isinstance(df_final.index, pd.DatetimeIndex):
        df_final.index = pd.to_datetime(df_final.index)

    df_final.index = df_final.index.strftime('%Y-%m-%d')

    # 엑셀 저장
    with pd.ExcelWriter(file_name, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        df_final.to_excel(writer, sheet_name='기준가')

    print(f"\n[성공] 저장이 완료되었습니다. (날짜 형식 인식 가능)")
    print(df_final.tail())

    # ---------------------------------------------------------
    # 7. 검증: 마지막 행에 NaN인 포트폴리오가 있으면 경고
    # ---------------------------------------------------------
    last_row = df_final.iloc[-1]
    last_date = df_final.index[-1]
    problems = []
    for pf in portfolio_config.keys():
        if pf in df_final.columns:
            val = last_row.get(pf)
            if pd.isna(val):
                # 시작일이 미래면 NaN 정상
                pf_start = pd.Timestamp(portfolio_config[pf]['start_date'])
                # 청산(end_date) 회차는 청산일 이후 NaN이 정상 → 검증 실패로 보지 않음
                _ed = portfolio_config[pf].get('end_date')
                if _ed and pd.Timestamp(_ed) < pd.Timestamp(last_date):
                    continue
                if pf_start <= pd.Timestamp(last_date):
                    problems.append(pf)
    if problems:
        print(f"\n⚠️ [검증 실패] {last_date} 기준가 NaN: {', '.join(problems)}")
        print("   재실행 필요!")
        exit(1)
    else:
        print(f"\n✅ [검증 통과] {last_date} 모든 포트폴리오 기준가 정상")

else:
    print("계산된 결과가 없습니다.")
