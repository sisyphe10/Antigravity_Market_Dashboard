import pandas as pd
import FinanceDataReader as fdr
import numpy as np
import os
import sys

# Windows console encoding fix
sys.stdout.reconfigure(encoding='utf-8')

# ---------------------------------------------------------
# 1. 설정
# ---------------------------------------------------------
# 포트폴리오별 초기 기준가 및 시작일
portfolio_config = {
    '트루밸류': {'base_price': 2021.31, 'start_date': '2025-12-30'},
    'Value ESG': {'base_price': 1980.49, 'start_date': '2025-12-30'},
    '자문형 랩': {'base_price': 1518.52, 'start_date': '2025-12-30'},
    '목표전환형': {'base_price': 1000.00, 'start_date': '2026-02-11'},
}
initial_base_prices = {k: v['base_price'] for k, v in portfolio_config.items()}
initial_start_date_str = min(cfg['start_date'] for cfg in portfolio_config.values())

# 시장 지수
indices = {
    'KOSPI': 'KS11',
    'KOSDAQ': 'KQ11'
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

# 계산 종료일 (어제)
today = pd.Timestamp.now().normalize()
end_date = today - pd.Timedelta(days=1)

print(f"   - 계산 종료일(목표): {end_date.strftime('%Y-%m-%d')}")

# 신규 포트폴리오 확인 (기존 데이터에 없는 포트폴리오)
new_portfolios = []
if is_update:
    new_portfolios = [pf for pf in initial_base_prices.keys() if pf not in df_old.columns]

if start_date >= end_date and not new_portfolios:
    print("\n✅ 이미 최신 데이터까지 업데이트되어 있습니다. (종료)")
    exit()

# 신규 포트폴리오가 있으면 데이터 수집 시작일을 조정
if new_portfolios:
    earliest_new_start = min(pd.Timestamp(portfolio_config[pf]['start_date']) for pf in new_portfolios)
    if earliest_new_start < start_date:
        start_date = earliest_new_start
    print(f"   - 신규 포트폴리오 감지: {', '.join(new_portfolios)}")

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
print(f"2. 데이터 수집 (기간: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')})")

# 4-1. 개별 종목
df_change = pd.DataFrame()
for code in all_codes:
    try:
        d = fdr.DataReader(code, start=start_date)
        if not d.empty:
            df_change[code] = d['Change']
    except:
        pass

# 4-2. 시장 지수
print("   - KOSPI, KOSDAQ 지수 수집 중...")
df_indices = pd.DataFrame()
for name, code in indices.items():
    try:
        d = fdr.DataReader(code, start=start_date)
        if not d.empty:
            df_indices[name] = d['Close']
    except:
        pass

if df_change.empty and df_indices.empty:
    print("\n[알림] 해당 기간의 데이터가 없습니다.")
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

    if is_new_portfolio:
        # 신규 포트폴리오: 설정된 시작일 기준
        pf_start_date = pf_config_start
        pf_calc_dates = df_change.index[(df_change.index > pf_config_start) & (df_change.index <= end_date)]
    else:
        # 기존 포트폴리오: 기존 데이터 이후부터
        pf_start_date = start_date
        pf_calc_dates = calc_dates

    w_table = sub_df.pivot(index='날짜', columns='코드', values='비중')
    full_idx = pf_calc_dates.union(w_table.index).sort_values()
    w_table = w_table.reindex(full_idx).ffill().fillna(0)

    idx_list = []
    date_list = []

    # 처음 생성 시 또는 신규 포트폴리오: 시작일(T=0) 초기값 기록
    if not is_update or is_new_portfolio:
        idx_list.append(start_price)
        date_list.append(pf_start_date)

    current_index = start_price

    for d in pf_calc_dates:
        # 전일(d-1)까지 유효했던 비중 찾기
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
        df_final = pd.concat([df_old, df_new_combined])
        # 중복 제거 (날짜 기준)
        df_final = df_final[~df_final.index.duplicated(keep='last')]
    else:
        df_final = df_new_combined

    # 소수점 둘째 자리 반올림
    df_final = df_final.round(2)

    # ★ [수정 포인트]
    # 문자열로 변환하는 strftime 코드를 제거했습니다.
    # 대신 DatetimeIndex인지 확실히 하여, 엑셀이 '날짜' 포맷으로 인식하게 합니다.
    if not isinstance(df_final.index, pd.DatetimeIndex):
        df_final.index = pd.to_datetime(df_final.index)

    # (선택) 시/분/초가 있다면 제거(00:00:00)하여 깔끔하게 만듦
    # 실제 엑셀 저장 시에는 데이터 타입이 Date가 됩니다.
    df_final.index = df_final.index.normalize()

    # 엑셀 저장
    with pd.ExcelWriter(file_name, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        df_final.to_excel(writer, sheet_name='기준가')

    print(f"\n[성공] 저장이 완료되었습니다. (날짜 형식 인식 가능)")
    print(df_final.tail())

else:
    print("계산된 결과가 없습니다.")
