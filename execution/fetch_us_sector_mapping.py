"""
미국 주식 섹터/산업 매핑 수집
- NASDAQ API로 종목 리스트 → yfinance로 sector/industry 수집
- us_sector_mapping.json 저장
"""
import sys
import json
import logging
import time
import requests

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')


def get_us_tickers():
    """NASDAQ API에서 전체 미국 상장 종목 리스트"""
    url = 'https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25000&offset=0'
    headers = {'User-Agent': 'Mozilla/5.0'}
    r = requests.get(url, headers=headers, timeout=60)
    rows = r.json()['data']['table']['rows']
    # 워런트, 유닛 등 제외
    tickers = []
    for row in rows:
        sym = row['symbol']
        if '^' in sym or '/' in sym:
            continue
        tickers.append(sym)
    return tickers


def fetch_us_sectors():
    """전 종목 yfinance sector/industry 수집"""
    import yfinance as yf

    tickers = get_us_tickers()
    logging.info(f"수집 대상: {len(tickers)}종목")

    # 기존 매핑 로드 (이어하기 지원)
    existing = {}
    try:
        with open('us_sector_mapping.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            existing = data.get('mapping', {})
        logging.info(f"기존 매핑 로드: {len(existing)}종목")
    except:
        pass

    mapping = dict(existing)
    new_count = 0
    fail_count = 0

    for i, sym in enumerate(tickers):
        if sym in mapping:
            continue
        try:
            info = yf.Ticker(sym).info
            sector = info.get('sector', '')
            industry = info.get('industry', '')
            if sector:
                mapping[sym] = {'sector': sector, 'industry': industry}
                new_count += 1
            else:
                fail_count += 1
        except Exception:
            fail_count += 1

        # 진행 상황 로그 (500개마다)
        if (i + 1) % 500 == 0:
            logging.info(f"  {i+1}/{len(tickers)} (신규 {new_count}, 실패 {fail_count})")
            # 중간 저장
            with open('us_sector_mapping.json', 'w', encoding='utf-8') as f:
                json.dump({'mapping': mapping}, f, ensure_ascii=False)

    with open('us_sector_mapping.json', 'w', encoding='utf-8') as f:
        json.dump({'mapping': mapping}, f, ensure_ascii=False)

    logging.info(f"완료: {len(mapping)}종목 매핑 (신규 {new_count}, 실패 {fail_count})")
    return mapping


if __name__ == '__main__':
    fetch_us_sectors()
