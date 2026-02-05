import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys

# Windows console encoding fix
sys.stdout.reconfigure(encoding='utf-8')

file_name = 'Wrap_NAV.xlsx'

print("1. 기준가 데이터 읽기 중...")

# 기준가 시트 읽기
df = pd.read_excel(file_name, sheet_name='기준가')

# Date 컬럼을 인덱스로 설정
if 'Date' in df.columns:
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date')
else:
    df.index = pd.to_datetime(df.iloc[:, 0])
    df = df.iloc[:, 1:]

# NaN이 아닌 컬럼만 선택 (Unnamed 컬럼 제거)
df = df.loc[:, ~df.columns.str.contains('Unnamed', na=False)]

print(f"   - 데이터 기간: {df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')}")
print(f"   - 대상 항목: {', '.join(df.columns.tolist())}")

# 최신 날짜
latest_date = df.index[-1]
print(f"\n2. 수익률 계산 중... (기준일: {latest_date.strftime('%Y-%m-%d')})")

# 수익률 계산 함수
def calculate_return(current_value, past_value):
    """수익률 계산 및 포맷 (소수점 첫째자리 + % 기호)"""
    if pd.isna(past_value) or past_value == 0 or pd.isna(current_value):
        return np.nan
    return_pct = ((current_value - past_value) / past_value) * 100
    return f"{return_pct:.1f}%"

# 각 컬럼(상품/지수)에 대해 수익률 계산
print("   - 계산 중...")

# 결과를 저장할 딕셔너리 (날짜를 키로 사용)
current_date_str = latest_date.strftime('%Y-%m-%d')
returns_data = {'날짜': current_date_str}

for col in df.columns:
    current_value = df.loc[latest_date, col]
    
    if pd.isna(current_value):
        # 데이터가 없으면 모든 기간에 대해 NaN
        for period in ['1D', '1W', '1M', '3M', '6M', '1Y', 'YTD']:
            returns_data[f"{col}_{period}"] = np.nan
        continue
    
    # 1D (전일 대비)
    past_dates_1d = df.index[df.index < latest_date]
    if len(past_dates_1d) > 0:
        past_value = df.loc[past_dates_1d[-1], col]
        returns_data[f"{col}_1D"] = calculate_return(current_value, past_value)
    else:
        returns_data[f"{col}_1D"] = np.nan
    
    # 1W (7일 전)
    target_date_1w = latest_date - timedelta(days=7)
    past_dates_1w = df.index[df.index <= target_date_1w]
    if len(past_dates_1w) > 0:
        past_value = df.loc[past_dates_1w[-1], col]
        returns_data[f"{col}_1W"] = calculate_return(current_value, past_value)
    else:
        returns_data[f"{col}_1W"] = np.nan
    
    # 1M (1개월 전)
    target_date_1m = latest_date - pd.DateOffset(months=1)
    past_dates_1m = df.index[df.index <= target_date_1m]
    if len(past_dates_1m) > 0:
        past_value = df.loc[past_dates_1m[-1], col]
        returns_data[f"{col}_1M"] = calculate_return(current_value, past_value)
    else:
        returns_data[f"{col}_1M"] = np.nan
    
    # 3M (3개월 전)
    target_date_3m = latest_date - pd.DateOffset(months=3)
    past_dates_3m = df.index[df.index <= target_date_3m]
    if len(past_dates_3m) > 0:
        past_value = df.loc[past_dates_3m[-1], col]
        returns_data[f"{col}_3M"] = calculate_return(current_value, past_value)
    else:
        returns_data[f"{col}_3M"] = np.nan
    
    # 6M (6개월 전)
    target_date_6m = latest_date - pd.DateOffset(months=6)
    past_dates_6m = df.index[df.index <= target_date_6m]
    if len(past_dates_6m) > 0:
        past_value = df.loc[past_dates_6m[-1], col]
        returns_data[f"{col}_6M"] = calculate_return(current_value, past_value)
    else:
        returns_data[f"{col}_6M"] = np.nan
    
    # 1Y (1년 전)
    target_date_1y = latest_date - pd.DateOffset(years=1)
    past_dates_1y = df.index[df.index <= target_date_1y]
    if len(past_dates_1y) > 0:
        past_value = df.loc[past_dates_1y[-1], col]
        returns_data[f"{col}_1Y"] = calculate_return(current_value, past_value)
    else:
        returns_data[f"{col}_1Y"] = np.nan
    
    # YTD (연초 첫 거래일)
    year_start = datetime(latest_date.year, 1, 1)
    ytd_dates = df.index[df.index >= year_start]
    if len(ytd_dates) > 0:
        ytd_start_date = ytd_dates[0]
        past_value = df.loc[ytd_start_date, col]
        returns_data[f"{col}_YTD"] = calculate_return(current_value, past_value)
    else:
        returns_data[f"{col}_YTD"] = np.nan

print("   - 완료")

# 새로운 행을 DataFrame으로 변환
df_new_row = pd.DataFrame([returns_data])

print("\n3. 결과 저장 중...")

# 기존 '수익률' 시트가 있는지 확인
try:
    df_existing = pd.read_excel(file_name, sheet_name='수익률')
    
    # 같은 날짜가 이미 있으면 제거 (업데이트)
    if '날짜' in df_existing.columns:
        df_existing = df_existing[df_existing['날짜'] != current_date_str]
    
    # 기존 데이터에 새 행 추가
    df_returns = pd.concat([df_existing, df_new_row], ignore_index=True)
    print(f"   - 기존 데이터에 {current_date_str} 추가")
    
except:
    # '수익률' 시트가 없으면 새로 생성
    df_returns = df_new_row
    print(f"   - 새로운 '수익률' 시트 생성")

# 엑셀에 '수익률' 시트로 저장
with pd.ExcelWriter(file_name, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
    df_returns.to_excel(writer, sheet_name='수익률', index=False)

print(f"\n[성공] '수익률' 시트가 업데이트되었습니다.")
print(f"\n최신 데이터 ({current_date_str}):")
print(df_new_row.T)
