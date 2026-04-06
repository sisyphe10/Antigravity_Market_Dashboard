"""
투자일지 시장 데이터 자동 수집 → Google Spreadsheet 입력
- 네이버 금융: 지수, 변동, 거래대금, 투자자별
- KRX OpenAPI: 상승/보합/하락 종목수
"""
import sys
import os
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

JOURNAL_SHEET_ID = '13HXDxF62ILXyRz7meRZ5CxJT5HfWAwIKc8IsCavuVXk'
KRX_API_KEY = 'E9E8B0A915D74BC59CFA41D5534CF19EF4B24C9E'
HEADERS = {'User-Agent': 'Mozilla/5.0'}
KST = timezone(timedelta(hours=9))


def get_index_data():
    """네이버 금융에서 KOSPI/KOSDAQ 지수 + 거래대금"""
    result = {}
    for code, prefix in [('KOSPI', 'k'), ('KOSDAQ', 'q')]:
        r = requests.get(f'https://finance.naver.com/sise/sise_index_day.naver?code={code}', headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.select('table')[0]
        rows = table.select('tr')
        # 첫 번째 데이터 행 (오늘)
        for row in rows:
            cells = row.select('td')
            if len(cells) >= 6:
                date_text = cells[0].text.strip()
                close = cells[1].text.strip().replace(',', '')
                chg_rate = cells[3].text.strip()
                volume_mil = cells[5].text.strip().replace(',', '')  # 거래대금(백만)
                try:
                    volume_eok = round(int(volume_mil) / 100)  # 백만 → 억원
                except:
                    volume_eok = volume_mil
                result[f'{prefix}_close'] = close
                result[f'{prefix}_chg'] = chg_rate
                result[f'{prefix}_vol'] = volume_eok
                raw = date_text.replace('.', '')
                result['date'] = f'20{raw}' if len(raw) == 6 else raw  # 26.03.31 → 20260331, 2026.03.31 → 20260331
                break

    # 거래대금 변동률 (전일 대비)
    for code, prefix in [('KOSPI', 'k'), ('KOSDAQ', 'q')]:
        r = requests.get(f'https://finance.naver.com/sise/sise_index_day.naver?code={code}', headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.select('table')[0]
        rows = table.select('tr')
        vols = []
        for row in rows:
            cells = row.select('td')
            if len(cells) >= 6:
                vol = cells[5].text.strip().replace(',', '')
                try:
                    vols.append(int(vol))
                except:
                    pass
                if len(vols) == 2:
                    break
        if len(vols) == 2 and vols[1] > 0:
            vol_chg = round((vols[0] / vols[1] - 1) * 100, 1)
            result[f'{prefix}_vol_chg'] = f'{vol_chg:+.1f}%'
        else:
            result[f'{prefix}_vol_chg'] = ''

    return result


def get_investor_data(date_str):
    """네이버 금융에서 투자자별 순매수 (개인/외국인/기관)"""
    result = {}
    for sosok, prefix in [('01', 'k'), ('02', 'q')]:
        r = requests.get(f'https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate={date_str}&sosok={sosok}', headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        tables = soup.select('table')
        if tables:
            rows = tables[0].select('tr')
            for row in rows:
                cells = row.select('td')
                if len(cells) >= 4:
                    row_date = cells[0].text.strip().replace('.', '')
                    if row_date == date_str[2:]:  # 26.03.31 매칭
                        result[f'{prefix}_per'] = cells[1].text.strip().replace(',', '')
                        result[f'{prefix}_for'] = cells[2].text.strip().replace(',', '')
                        result[f'{prefix}_inst'] = cells[3].text.strip().replace(',', '')
                        break
    return result


def get_rise_fall_count():
    """네이버 금융에서 상승/보합/하락 종목수 크롤링"""
    import re
    result = {}
    for code, prefix in [('KOSPI', 'k'), ('KOSDAQ', 'q')]:
        try:
            r = requests.get(f'https://finance.naver.com/sise/sise_index.naver?code={code}', headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            for table in soup.select('table'):
                t = table.get_text()
                if '상한종목수' in t and '하한종목수' in t:
                    limit_up = int(re.search(r'상한종목수(\d+)', t).group(1))
                    rise = int(re.search(r'상승종목수(\d+)', t).group(1))
                    flat = int(re.search(r'보합종목수(\d+)', t).group(1))
                    fall = int(re.search(r'하락종목수(\d+)', t).group(1))
                    limit_down = int(re.search(r'하한종목수(\d+)', t).group(1))
                    result[f'{prefix}_up'] = limit_up + rise
                    result[f'{prefix}_flat'] = flat
                    result[f'{prefix}_down'] = fall + limit_down
                    break
        except Exception as e:
            logging.warning(f'{code} 상승/하락 크롤링 실패: {e}')
    return result


def write_to_sheet(data):
    """Google Spreadsheet에 데이터 쓰기"""
    import gspread
    from google.oauth2.service_account import Credentials

    sa_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_KEY')
    if sa_json:
        import json
        sa_info = json.loads(sa_json)
        creds = Credentials.from_service_account_info(sa_info, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    else:
        # 로컬 테스트용
        key_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'extreme-height-486504-c4-b6e5cda22ed7.json')
        creds = Credentials.from_service_account_file(key_file, scopes=['https://www.googleapis.com/auth/spreadsheets'])

    gc = gspread.authorize(creds)
    sh = gc.open_by_key(JOURNAL_SHEET_ID)
    ws = sh.worksheet('Data')

    # 날짜 변환
    raw_date = data.get('date', '')
    if len(raw_date) == 8:
        date_str = f'{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}'
    else:
        date_str = raw_date

    dow = ['월', '화', '수', '목', '금', '토', '일']
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        day_name = dow[d.weekday()]
    except:
        day_name = ''

    # 기존 데이터에서 같은 날짜 확인
    existing = ws.col_values(1)
    for i, v in enumerate(existing):
        if date_str in str(v):
            logging.info(f'{date_str} 이미 존재 (행 {i+1}), 시장 데이터만 업데이트')
            # 시장 데이터 컬럼만 업데이트 (C~V, 3~22)
            row_num = i + 1
            ws.update(f'A{row_num}', [[
                date_str, day_name,
                data.get('k_close', ''), data.get('k_chg', ''), data.get('k_vol', ''), data.get('k_vol_chg', ''),
                data.get('k_up', ''), data.get('k_flat', ''), data.get('k_down', ''),
                data.get('k_per', ''), data.get('k_for', ''), data.get('k_inst', ''),
                data.get('q_close', ''), data.get('q_chg', ''), data.get('q_vol', ''), data.get('q_vol_chg', ''),
                data.get('q_up', ''), data.get('q_flat', ''), data.get('q_down', ''),
                data.get('q_per', ''), data.get('q_for', ''), data.get('q_inst', ''),
                data.get('k_ma120', ''), data.get('q_ma120', ''),
                data.get('nq_close', ''), data.get('nq_chg', ''), data.get('nq_vol', ''), data.get('nq_vol_chg', ''),
            ]])
            return

    # 새 행 추가
    row = [
        date_str, day_name,
        data.get('k_close', ''), data.get('k_chg', ''), data.get('k_vol', ''), data.get('k_vol_chg', ''),
        data.get('k_up', ''), data.get('k_flat', ''), data.get('k_down', ''),
        data.get('k_per', ''), data.get('k_for', ''), data.get('k_inst', ''),
        data.get('q_close', ''), data.get('q_chg', ''), data.get('q_vol', ''), data.get('q_vol_chg', ''),
        data.get('q_up', ''), data.get('q_flat', ''), data.get('q_down', ''),
        data.get('q_per', ''), data.get('q_for', ''), data.get('q_inst', ''),
        data.get('k_ma120', ''), data.get('q_ma120', ''),
        data.get('nq_close', ''), data.get('nq_chg', ''), data.get('nq_vol', ''), data.get('nq_vol_chg', ''),
    ]
    ws.append_row(row, value_input_option='USER_ENTERED')
    logging.info(f'{date_str} 새 행 추가 완료')


def main():
    logging.info('투자일지 데이터 수집 시작')

    # 1. 지수/거래대금
    idx = get_index_data()
    date_str = idx.get('date', '')
    logging.info(f'날짜: {date_str}, KOSPI: {idx.get("k_close")}, KOSDAQ: {idx.get("q_close")}')

    # 2. 투자자별
    inv = get_investor_data(date_str)
    idx.update(inv)
    logging.info(f'투자자: 개인 {inv.get("k_per")}, 외국인 {inv.get("k_for")}, 기관 {inv.get("k_inst")}')

    # 3. 상승/하락
    rf = get_rise_fall_count()
    idx.update(rf)
    logging.info(f'상승/하락: {rf.get("k_up")}/{rf.get("k_flat")}/{rf.get("k_down")}')

    # 4. NASDAQ 전일 종가 (dataset.csv)
    try:
        import pandas as pd
        ds = pd.read_csv('dataset.csv')
        nq = ds[ds['제품명'] == 'NASDAQ'].sort_values('날짜')
        if not nq.empty:
            nq_latest = nq.iloc[-1]
            idx['nq_close'] = float(nq_latest['가격'])
            if len(nq) >= 2:
                prev = float(nq.iloc[-2]['가격'])
                chg = round((float(nq_latest['가격']) / prev - 1) * 100, 2)
                idx['nq_chg'] = f'{chg:+.1f}%'
            # NASDAQ 거래량 (FDR/yfinance)
            import FinanceDataReader as fdr
            nq_df = fdr.DataReader('^IXIC', '2026-01-01')
            if not nq_df.empty and len(nq_df) >= 2:
                vol = nq_df.iloc[-1]['Volume']
                prev_vol = nq_df.iloc[-2]['Volume']
                idx['nq_vol'] = round(vol / 1e9, 1)  # 십억주(B)
                vol_chg = round((vol / prev_vol - 1) * 100, 1)
                idx['nq_vol_chg'] = f'{vol_chg:+.1f}%'
            logging.info(f'NASDAQ: {idx.get("nq_close")} ({idx.get("nq_chg", "")}) Vol: {idx.get("nq_vol", "")}B')
    except Exception as e:
        logging.warning(f'NASDAQ 수집 실패: {e}')

    # 5. 120일선 계산 (Wrap_NAV.xlsx 기준가)
    try:
        import pandas as pd
        nav = pd.read_excel('Wrap_NAV.xlsx', sheet_name='기준가')
        nav['Date'] = pd.to_datetime(nav['Date'])
        nav = nav.sort_values('Date')
        for col, prefix in [('KOSPI', 'k'), ('KOSDAQ', 'q')]:
            if col in nav.columns:
                series = nav[col].dropna()
                if len(series) >= 120:
                    ma120 = series.rolling(120).mean().iloc[-1]
                    current = series.iloc[-1]
                    idx[f'{prefix}_ma120'] = 'UP' if current > ma120 else 'DOWN'
                    logging.info(f'{col} 120MA: {ma120:.0f}, 현재: {current:.0f} → {idx[f"{prefix}_ma120"]}')
    except Exception as e:
        logging.warning(f'120일선 계산 실패: {e}')

    # 5. 스프레드시트 저장
    write_to_sheet(idx)
    logging.info('완료!')


if __name__ == '__main__':
    main()
