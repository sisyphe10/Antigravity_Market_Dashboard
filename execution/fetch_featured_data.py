"""
KRX OpenAPI로 Featured 데이터 수집 → featured_data.json 적재
- 거래대금 절대금액 상위 30
- 거래대금/시총 비율(회전율) 상위 30
"""
import sys
import os
import json
import logging
import pandas as pd
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

API_KEY = 'E9E8B0A915D74BC59CFA41D5534CF19EF4B24C9E'
FEATURED_JSON = 'featured_data.json'
TOP_N = 30


def get_daily_data(date_str):
    """KRX API에서 코스피+코스닥 전 종목 데이터 수집"""
    from pykrx_openapi import KRXOpenAPI
    api = KRXOpenAPI(API_KEY)

    kospi = pd.DataFrame(api.get_stock_daily_trade(date_str)['OutBlock_1'])
    kosdaq = pd.DataFrame(api.get_kosdaq_stock_daily_trade(date_str)['OutBlock_1'])
    df = pd.concat([kospi, kosdaq], ignore_index=True)

    for col in ['ACC_TRDVAL', 'MKTCAP', 'FLUC_RT', 'TDD_CLSPRC', 'CMPPREVDD_PRC']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df[(df['MKTCAP'] > 0) & df['ISU_NM'].notna() & (df['ISU_NM'] != '')]

    # 필터: 스팩, 리츠, 우선주, 시총 1500억 미만 제외
    df = df[~df['ISU_NM'].str.contains('스팩', na=False)]
    df = df[~df['ISU_NM'].str.contains('리츠', na=False)]
    df = df[df['ISU_CD'].str[-1] == '0']
    df = df[df['MKTCAP'] >= 150_000_000_000]

    df['TURNOVER'] = df['ACC_TRDVAL'] / df['MKTCAP'] * 100

    return df


def extract_top(df, date_str):
    """거래대금 TOP 30 (절대 + 회전율) 추출"""
    records = []

    # 절대금액 상위
    top_abs = df.nlargest(TOP_N, 'ACC_TRDVAL')
    for rank, (_, r) in enumerate(top_abs.iterrows(), 1):
        records.append({
            'd': date_str,
            'type': 'absolute',
            'rank': rank,
            'name': r['ISU_NM'],
            'code': r['ISU_CD'],
            'market': r['MKT_NM'] or '',
            'trdval': int(r['ACC_TRDVAL']),
            'mktcap': int(r['MKTCAP']),
            'turnover': round(r['TURNOVER'], 2),
            'chg': round(r['FLUC_RT'], 2) if pd.notna(r['FLUC_RT']) else 0,
            'price': int(r['TDD_CLSPRC']) if pd.notna(r['TDD_CLSPRC']) else 0,
        })

    # 회전율 상위
    top_turn = df.nlargest(TOP_N, 'TURNOVER')
    for rank, (_, r) in enumerate(top_turn.iterrows(), 1):
        records.append({
            'd': date_str,
            'type': 'turnover',
            'rank': rank,
            'name': r['ISU_NM'],
            'code': r['ISU_CD'],
            'market': r['MKT_NM'] or '',
            'trdval': int(r['ACC_TRDVAL']),
            'mktcap': int(r['MKTCAP']),
            'turnover': round(r['TURNOVER'], 2),
            'chg': round(r['FLUC_RT'], 2) if pd.notna(r['FLUC_RT']) else 0,
            'price': int(r['TDD_CLSPRC']) if pd.notna(r['TDD_CLSPRC']) else 0,
        })

    # 코스피 시총 상위
    def add_top(src_df, type_name, sort_col, ascending=False):
        top = src_df.nlargest(TOP_N, sort_col) if not ascending else src_df.nsmallest(TOP_N, sort_col)
        for rank, (_, r) in enumerate(top.iterrows(), 1):
            records.append({
                'd': date_str, 'type': type_name, 'rank': rank,
                'name': r['ISU_NM'], 'code': r['ISU_CD'],
                'market': r['MKT_NM'] or '',
                'trdval': int(r['ACC_TRDVAL']),
                'mktcap': int(r['MKTCAP']),
                'turnover': round(r['TURNOVER'], 2),
                'chg': round(r['FLUC_RT'], 2) if pd.notna(r['FLUC_RT']) else 0,
                'price': int(r['TDD_CLSPRC']) if pd.notna(r['TDD_CLSPRC']) else 0,
            })

    kospi = df[df['MKT_NM'] == 'KOSPI']
    kosdaq = df[df['MKT_NM'] == 'KOSDAQ']

    add_top(kospi, 'kospi_cap', 'MKTCAP')
    add_top(kosdaq, 'kosdaq_cap', 'MKTCAP')
    add_top(kospi, 'kospi_chg', 'FLUC_RT')
    add_top(kosdaq, 'kosdaq_chg', 'FLUC_RT')

    # 신고가 계산 (stock_price_history.json 기반)
    history_file = 'stock_price_history.json'
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            hist_dates = sorted(history['dates'])
            if date_str in hist_dates:
                for label, n_days in [('newhigh_20d', 20), ('newhigh_120d', 120), ('newhigh_52w', 252)]:
                    for code, stock in history['stocks'].items():
                        # 필터링된 df에 있는 종목만 (스팩/리츠/우선주/시총1500억 미만 제외)
                        match = df[df['ISU_CD'] == code]
                        if match.empty:
                            continue
                        highs = stock['highs']
                        high_today = highs.get(date_str, 0)
                        close = stock['closes'].get(date_str, 0)
                        if high_today == 0 or close == 0:
                            continue
                        past = [highs.get(d, 0) for d in hist_dates if d < date_str]
                        past = [h for h in past if h > 0]
                        recent = past[-n_days:] if len(past) >= n_days else past
                        if not recent:
                            continue
                        if high_today > max(recent):
                            mktcap = int(match.iloc[0]['MKTCAP']) if pd.notna(match.iloc[0]['MKTCAP']) else 0
                            trdval = int(match.iloc[0]['ACC_TRDVAL']) if pd.notna(match.iloc[0]['ACC_TRDVAL']) else 0
                            records.append({
                                'd': date_str, 'type': label, 'rank': 0,
                                'name': stock['name'], 'code': code,
                                'market': stock['market'],
                                'trdval': trdval, 'mktcap': mktcap,
                                'turnover': 0,
                                'chg': round(float(df[df['ISU_CD']==code]['FLUC_RT'].iloc[0]), 2) if not df[df['ISU_CD']==code].empty else 0,
                                'price': close,
                            })
        except Exception as e:
            logging.warning(f'신고가 계산 실패: {e}')

    return records


def get_existing_dates():
    """이미 수집된 날짜 목록"""
    if not os.path.exists(FEATURED_JSON):
        return set()
    with open(FEATURED_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return set(r['d'] for r in data)


def get_trading_days(start, end):
    """주말 제외 날짜 리스트"""
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def main():
    import datetime as _dt
    KST = _dt.timezone(_dt.timedelta(hours=9))
    today = datetime.now(tz=KST).date()
    start = datetime(today.year - 1, 12, 25).date()  # 전년 마지막주부터 (YTD 기준가 확보)

    existing = get_existing_dates()
    trading_days = get_trading_days(start, today)
    to_fetch = [d for d in trading_days if d.strftime('%Y-%m-%d') not in existing]

    # 당일은 항상 재수집 (16:10 1차→18:30 2차 갱신을 위해)
    today_str = today.strftime('%Y-%m-%d')
    if today.weekday() < 5 and today_str not in [d.strftime('%Y-%m-%d') for d in to_fetch]:
        to_fetch.append(today)

    if not to_fetch:
        logging.info("완료! 수집할 날짜 없음 (주말/공휴일)")
        return

    logging.info(f"수집 대상: {len(to_fetch)}일 ({to_fetch[0]} ~ {to_fetch[-1]})")

    # 기존 데이터 로드
    if os.path.exists(FEATURED_JSON):
        with open(FEATURED_JSON, 'r', encoding='utf-8') as f:
            all_records = json.load(f)
    else:
        all_records = []

    # 재수집 대상 날짜의 기존 데이터 제거 (당일 재수집 시)
    fetch_dates = set(d.strftime('%Y-%m-%d') for d in to_fetch)
    removed = sum(1 for r in all_records if r['d'] in fetch_dates)
    if removed:
        all_records = [r for r in all_records if r['d'] not in fetch_dates]
        logging.info(f"기존 {removed}건 제거 (재수집 대상)")

    for i, d in enumerate(to_fetch):
        date_str = d.strftime('%Y%m%d')
        date_display = d.strftime('%Y-%m-%d')
        logging.info(f"[{i+1}/{len(to_fetch)}] {date_display} 수집 중...")

        try:
            df = get_daily_data(date_str)
            if len(df) < 100:
                logging.info(f"  → 데이터 부족 ({len(df)}건), 건너뜀")
                continue
            records = extract_top(df, date_display)
            all_records.extend(records)
            logging.info(f"  → {len(records)}건 수집")
        except Exception as e:
            logging.warning(f"  → 실패: {e}")

    with open(FEATURED_JSON, 'w', encoding='utf-8') as f:
        json.dump(all_records, f, ensure_ascii=False)

    dates = sorted(set(r['d'] for r in all_records))
    logging.info(f"완료! 총 {len(all_records)}건 ({dates[0]} ~ {dates[-1]})")


if __name__ == '__main__':
    main()
