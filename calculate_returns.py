import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys

# Windows console encoding fix
sys.stdout.reconfigure(encoding='utf-8')

file_name = 'Wrap_NAV.xlsx'

# 포트폴리오별 YTD 기준일 설정
ytd_base_dates = {
    '트루밸류': '2025-12-30',
    'Value ESG': '2025-12-30',
    '개방형 랩': '2025-12-30',
    # '목표전환형': '2026-02-11',  # 1차 완료 (6% 목표달성, 2026-02-25 청산)
    'KOSPI': '2025-12-30',
    'KOSDAQ': '2025-12-30',
}

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

# 최신 날짜: 각 컬럼의 최신 유효 날짜 중 가장 많이 등장하는 날짜를 기준일로 사용
from collections import Counter
col_latest_dates = []
for col in df.columns:
    col_data = df[col].dropna()
    if len(col_data) > 0:
        col_latest_dates.append(col_data.index[-1])
latest_date = Counter(col_latest_dates).most_common(1)[0][0]
print(f"\n2. 수익률 계산 중... (기준일: {latest_date.strftime('%Y-%m-%d')})")

# 수익률 계산 함수
def calculate_return(current_value, past_value):
    """수익률 계산 및 포맷 (소수점 첫째자리 + % 기호)"""
    if pd.isna(past_value) or past_value == 0 or pd.isna(current_value):
        return np.nan
    return_pct = ((current_value - past_value) / past_value) * 100
    return f"{return_pct:.1f}%"

# 각 컬럼(상품/지수)에 대해 수익률 계산
# 컬럼별로 최신 유효 데이터를 기준으로 계산 (시작일이 다른 포트폴리오 대응)
print("   - 계산 중...")

# 결과를 저장할 딕셔너리 (날짜를 키로 사용)
current_date_str = latest_date.strftime('%Y-%m-%d')
returns_data = {'날짜': current_date_str}

for col in df.columns:
    # 해당 컬럼의 유효 데이터만 추출
    col_series = df[col].dropna()

    if len(col_series) == 0:
        for period in ['1D', '1W', '1M', '3M', '6M', '1Y', 'YTD']:
            returns_data[f"{col}_{period}"] = np.nan
        continue

    current_value = col_series.iloc[-1]
    col_latest = col_series.index[-1]
    print(f"   - {col}: 기준일 {col_latest.strftime('%Y-%m-%d')}, 값 {current_value:,.2f}")

    # 1D (전일 대비)
    if len(col_series) >= 2:
        returns_data[f"{col}_1D"] = calculate_return(current_value, col_series.iloc[-2])
    else:
        returns_data[f"{col}_1D"] = np.nan

    # 1W (7일 전)
    target_1w = col_latest - timedelta(days=7)
    past_1w = col_series[col_series.index <= target_1w]
    returns_data[f"{col}_1W"] = calculate_return(current_value, past_1w.iloc[-1]) if len(past_1w) > 0 else np.nan

    # 1M (1개월 전)
    target_1m = col_latest - pd.DateOffset(months=1)
    past_1m = col_series[col_series.index <= target_1m]
    returns_data[f"{col}_1M"] = calculate_return(current_value, past_1m.iloc[-1]) if len(past_1m) > 0 else np.nan

    # 3M (3개월 전)
    target_3m = col_latest - pd.DateOffset(months=3)
    past_3m = col_series[col_series.index <= target_3m]
    returns_data[f"{col}_3M"] = calculate_return(current_value, past_3m.iloc[-1]) if len(past_3m) > 0 else np.nan

    # 6M (6개월 전)
    target_6m = col_latest - pd.DateOffset(months=6)
    past_6m = col_series[col_series.index <= target_6m]
    returns_data[f"{col}_6M"] = calculate_return(current_value, past_6m.iloc[-1]) if len(past_6m) > 0 else np.nan

    # 1Y (1년 전)
    target_1y = col_latest - pd.DateOffset(years=1)
    past_1y = col_series[col_series.index <= target_1y]
    returns_data[f"{col}_1Y"] = calculate_return(current_value, past_1y.iloc[-1]) if len(past_1y) > 0 else np.nan

    # YTD (포트폴리오별 기준일 사용)
    if col in ytd_base_dates:
        ytd_base_date = pd.Timestamp(ytd_base_dates[col])
        ytd_dates = col_series[col_series.index <= ytd_base_date]
        returns_data[f"{col}_YTD"] = calculate_return(current_value, ytd_dates.iloc[-1]) if len(ytd_dates) > 0 else np.nan
    else:
        # 기본값: 2025-12-30
        ytd_base_date = pd.Timestamp('2025-12-30')
        ytd_dates = col_series[col_series.index <= ytd_base_date]
        returns_data[f"{col}_YTD"] = calculate_return(current_value, ytd_dates.iloc[-1]) if len(ytd_dates) > 0 else np.nan

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
