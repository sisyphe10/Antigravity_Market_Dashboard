"""
신고가 종목 뉴스 수집 → featured_news.json
- featured_data.json에서 당일 신고가 종목 추출
- 섹터별 시총 상위 종목의 네이버 뉴스 검색
- 당일분만 유지 (매일 덮어쓰기)
"""
import sys
import os
import json
import re
import time
import logging
import requests
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
                    stream=sys.stdout)

KST = timezone(timedelta(hours=9))
FEATURED_JSON = 'featured_data.json'
WICS_JSON = 'wics_mapping.json'
NEWS_JSON = 'featured_news.json'
TOP_PER_SECTOR = 3   # 섹터당 뉴스 검색할 종목 수
NEWS_PER_STOCK = 2    # 종목당 뉴스 헤드라인 수

# .env에서 네이버 API 키 로드
from dotenv import load_dotenv
load_dotenv()
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')


def load_newhigh_stocks(target_date):
    """featured_data.json에서 특정 날짜의 신고가 종목 전체 로드"""
    if not os.path.exists(FEATURED_JSON):
        logging.error(f'{FEATURED_JSON} 없음')
        return {}

    with open(FEATURED_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)

    result = {}  # {type: [{'code','name','mktcap','chg','market'}, ...]}
    for r in data:
        if r['d'] != target_date:
            continue
        if r['type'] not in ('newhigh_20d', 'newhigh_120d', 'newhigh_52w'):
            continue
        if r['type'] not in result:
            result[r['type']] = []
        result[r['type']].append({
            'code': r['code'],
            'name': r['name'],
            'mktcap': r['mktcap'],
            'chg': r['chg'],
            'market': r['market'],
        })

    # 시총 내림차순 정렬
    for t in result:
        result[t].sort(key=lambda x: x['mktcap'], reverse=True)

    return result


def load_wics_mapping():
    """wics_mapping.json 로드"""
    if not os.path.exists(WICS_JSON):
        return {}
    with open(WICS_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('mapping', {})


def get_stocks_to_search(newhigh_data, wics):
    """섹터별 시총 상위 종목 선정 (뉴스 검색 대상)"""
    # 모든 기간의 신고가 종목을 합쳐서 섹터별 그룹핑
    all_stocks = {}  # code -> stock info (시총 최대값 기준)
    for stocks in newhigh_data.values():
        for s in stocks:
            code = s['code']
            if code not in all_stocks or s['mktcap'] > all_stocks[code]['mktcap']:
                all_stocks[code] = s

    # 섹터별 그룹핑
    sector_stocks = {}  # sector -> [stocks sorted by mktcap]
    for code, stock in all_stocks.items():
        sector = wics.get(code, '기타')
        if sector not in sector_stocks:
            sector_stocks[sector] = []
        sector_stocks[sector].append(stock)

    # 각 섹터에서 시총 상위 N개 선정
    to_search = []
    for sector in sector_stocks:
        sector_stocks[sector].sort(key=lambda x: x['mktcap'], reverse=True)
        for stock in sector_stocks[sector][:TOP_PER_SECTOR]:
            to_search.append(stock)

    return to_search


def search_naver_news(stock_name, date_str):
    """네이버 검색 API로 종목 뉴스 검색"""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        logging.warning('네이버 API 키 미설정')
        return []

    headers = {
        'X-Naver-Client-Id': NAVER_CLIENT_ID,
        'X-Naver-Client-Secret': NAVER_CLIENT_SECRET,
    }
    params = {
        'query': stock_name,
        'display': 5,  # 여유 있게 가져와서 필터링
        'sort': 'date',
    }

    try:
        r = requests.get('https://openapi.naver.com/v1/search/news.json',
                         headers=headers, params=params, timeout=5)
        r.raise_for_status()
        items = r.json().get('items', [])
    except Exception as e:
        logging.warning(f'뉴스 검색 실패 [{stock_name}]: {e}')
        return []

    results = []
    for item in items:
        title = re.sub(r'<.*?>', '', item.get('title', ''))
        title = title.replace('&quot;', '"').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        link = item.get('link', '')
        results.append({'title': title, 'link': link})
        if len(results) >= NEWS_PER_STOCK:
            break

    return results


def fetch_news(target_date=None):
    """메인: 신고가 종목 뉴스 수집"""
    if target_date is None:
        target_date = datetime.now(tz=KST).strftime('%Y-%m-%d')

    logging.info(f'신고가 뉴스 수집 시작: {target_date}')

    newhigh_data = load_newhigh_stocks(target_date)
    if not newhigh_data:
        logging.info('신고가 종목 없음, 스킵')
        return

    total_stocks = sum(len(v) for v in newhigh_data.values())
    logging.info(f'신고가 종목 수: 20일={len(newhigh_data.get("newhigh_20d", []))}, '
                 f'120일={len(newhigh_data.get("newhigh_120d", []))}, '
                 f'52주={len(newhigh_data.get("newhigh_52w", []))}')

    wics = load_wics_mapping()
    to_search = get_stocks_to_search(newhigh_data, wics)
    logging.info(f'뉴스 검색 대상: {len(to_search)}개 종목')

    # 뉴스 검색
    news = {}
    for i, stock in enumerate(to_search):
        code = stock['code']
        name = stock['name']
        results = search_naver_news(name, target_date)
        if results:
            news[code] = results
            logging.info(f'  [{i+1}/{len(to_search)}] {name}: {len(results)}건')
        else:
            logging.info(f'  [{i+1}/{len(to_search)}] {name}: 뉴스 없음')
        time.sleep(0.3)  # rate limiting

    # 저장
    output = {
        'date': target_date,
        'news': news,
    }
    with open(NEWS_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logging.info(f'저장 완료: {NEWS_JSON} ({len(news)}개 종목 뉴스)')


if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else None
    fetch_news(target)
