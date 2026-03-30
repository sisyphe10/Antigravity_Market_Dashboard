"""
stock_price_history.json 일일 업데이트
- 최신 1일 추가
- 1년(370일) 초과 데이터 정리
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
HISTORY_FILE = 'stock_price_history.json'
MAX_DAYS = 370  # 보관 기간 (52주 + 여유)


def main():
    from pykrx_openapi import KRXOpenAPI
    api = KRXOpenAPI(API_KEY)

    # 기존 데이터 로드
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
    else:
        logging.warning("stock_price_history.json 없음. 전체 수집이 필요합니다.")
        return

    existing_dates = set(history['dates'])
    today = datetime.now().date()

    # 최근 5거래일 중 누락된 날짜 수집
    dates_to_fetch = []
    for i in range(7):
        d = today - timedelta(days=i)
        if d.weekday() < 5 and d.strftime('%Y-%m-%d') not in existing_dates:
            dates_to_fetch.append(d)

    if not dates_to_fetch:
        logging.info("새로 수집할 날짜 없음.")
    else:
        logging.info(f"수집 대상: {len(dates_to_fetch)}일")

        for d in sorted(dates_to_fetch):
            date_str = d.strftime('%Y%m%d')
            date_display = d.strftime('%Y-%m-%d')

            try:
                kospi = pd.DataFrame(api.get_stock_daily_trade(date_str)['OutBlock_1'])
                kosdaq = pd.DataFrame(api.get_kosdaq_stock_daily_trade(date_str)['OutBlock_1'])
                df = pd.concat([kospi, kosdaq], ignore_index=True)

                for col in ['TDD_HGPRC', 'TDD_CLSPRC']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

                df = df[df['ISU_NM'].notna() & (df['ISU_NM'] != '')]

                if len(df) < 100:
                    continue

                history['dates'].append(date_display)

                for _, r in df.iterrows():
                    code = r['ISU_CD']
                    if code not in history['stocks']:
                        history['stocks'][code] = {
                            'name': r['ISU_NM'],
                            'market': r['MKT_NM'] or '',
                            'highs': {},
                            'closes': {},
                        }
                    history['stocks'][code]['highs'][date_display] = int(r['TDD_HGPRC']) if pd.notna(r['TDD_HGPRC']) else 0
                    history['stocks'][code]['closes'][date_display] = int(r['TDD_CLSPRC']) if pd.notna(r['TDD_CLSPRC']) else 0

                logging.info(f"  {date_display}: {len(df)}종목 추가")
            except Exception as e:
                if 'TDD_HGPRC' in str(e) or 'ACC_TRDVAL' in str(e):
                    continue
                logging.warning(f"  {date_display} 실패: {e}")

    # 1년 초과 데이터 정리
    history['dates'] = sorted(set(history['dates']))
    cutoff = (today - timedelta(days=MAX_DAYS)).strftime('%Y-%m-%d')
    old_dates = [d for d in history['dates'] if d < cutoff]

    if old_dates:
        history['dates'] = [d for d in history['dates'] if d >= cutoff]
        for code in history['stocks']:
            history['stocks'][code]['highs'] = {d: v for d, v in history['stocks'][code]['highs'].items() if d >= cutoff}
            history['stocks'][code]['closes'] = {d: v for d, v in history['stocks'][code]['closes'].items() if d >= cutoff}
        # 데이터 없는 종목 제거
        history['stocks'] = {c: s for c, s in history['stocks'].items() if s['highs']}
        logging.info(f"  {len(old_dates)}일 정리 (cutoff: {cutoff})")

    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False)

    logging.info(f"완료: {len(history['dates'])}일, {len(history['stocks'])}종목")


if __name__ == '__main__':
    main()
