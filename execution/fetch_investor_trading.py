"""
포트폴리오 보유 종목별 외국인/기관 순매수 5D/20D 누적 거래대금 수집.

데이터 소스
----------
네이버 금융 frgn 페이지 (page=1 = 최근 20거래일).
- KRX 인증 불필요, 안정적
- 종목당 약 0.3초

산출
----
investor_trading.json
- portfolio_data.json 의 모든 보유 종목 (중복 제거)
- 5D / 20D 누적 외국인·기관 순매수 (만주 + 거래대금 억원)

실행: VM cron (18:30 KST sisyphe_bot featured_update_job 안에서)
"""
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

KST = timezone(timedelta(hours=9))
PORTFOLIO_FILE = 'portfolio_data.json'
OUTPUT_FILE = 'investor_trading.json'
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
SHORT_WINDOW = 5
LONG_WINDOW = 20
RATE_LIMIT_SEC = 0.3


def fetch_one(code):
    """네이버 frgn page=1 (최근 20거래일) 파싱."""
    url = f'https://finance.naver.com/item/frgn.naver?code={code}&page=1'
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    rows = []
    for tr in soup.select('table.type2 tr'):
        tds = tr.select('td')
        if len(tds) < 9:
            continue
        date = tds[0].get_text(strip=True)
        if not date or '.' not in date:
            continue
        try:
            close = int(tds[1].get_text(strip=True).replace(',', ''))
            inst = int(tds[5].get_text(strip=True).replace(',', '').replace('+', ''))
            frgn = int(tds[6].get_text(strip=True).replace(',', '').replace('+', ''))
            rows.append({'date': date, 'close': close, 'inst': inst, 'frgn': frgn})
        except (ValueError, IndexError):
            continue
    return rows


def summarize(rows, window):
    head = rows[:window]
    inst_volume = sum(r['inst'] for r in head)
    frgn_volume = sum(r['frgn'] for r in head)
    inst_value_eok = sum(r['close'] * r['inst'] for r in head) / 1e8
    frgn_value_eok = sum(r['close'] * r['frgn'] for r in head) / 1e8
    return {
        'inst_volume': inst_volume,
        'frgn_volume': frgn_volume,
        'inst_value_eok': round(inst_value_eok, 1),
        'frgn_value_eok': round(frgn_value_eok, 1),
        'days_available': len(head),
    }


def main():
    if not os.path.exists(PORTFOLIO_FILE):
        logging.error(f'{PORTFOLIO_FILE} 없음')
        sys.exit(1)

    with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f:
        portfolios = json.load(f)

    codes = set()
    for holdings in portfolios.values():
        if not isinstance(holdings, list):
            continue
        for h in holdings:
            if h.get('code'):
                codes.add(h['code'])
    codes = sorted(codes)
    logging.info(f'대상 종목: {len(codes)}개')

    output = {
        'updated': datetime.now(tz=KST).isoformat(timespec='seconds'),
        'window_short': SHORT_WINDOW,
        'window_long': LONG_WINDOW,
        'stocks': {},
        'failed_codes': [],
    }

    for i, code in enumerate(codes, 1):
        try:
            rows = fetch_one(code)
            if not rows:
                output['failed_codes'].append(code)
                logging.warning(f'  {code}: 행 없음')
                continue
            output['stocks'][code] = {
                'last_date': rows[0]['date'],
                'short': summarize(rows, SHORT_WINDOW),
                'long': summarize(rows, LONG_WINDOW),
            }
            time.sleep(RATE_LIMIT_SEC)
            if i % 5 == 0 or i == len(codes):
                logging.info(f'  진행: {i}/{len(codes)}')
        except Exception as e:
            logging.warning(f'  {code} 실패: {e}')
            output['failed_codes'].append(code)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logging.info(
        f'완료: {OUTPUT_FILE} '
        f'({len(output["stocks"])}/{len(codes)} 성공, 실패 {len(output["failed_codes"])})'
    )


if __name__ == '__main__':
    main()
