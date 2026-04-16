"""
신고가 종목 뉴스 수집 + 섹터별 AI 요약 → featured_news.json
- featured_data.json에서 당일 신고가 종목 추출
- 섹터별 시총 상위 종목의 네이버 뉴스 검색
- Claude API로 섹터별 종합 요약 생성
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
NEWS_PER_STOCK = 3    # 종목당 뉴스 헤드라인 수

from dotenv import load_dotenv
load_dotenv()
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')


def load_newhigh_stocks(target_date):
    """featured_data.json에서 특정 날짜의 신고가 종목 전체 로드"""
    if not os.path.exists(FEATURED_JSON):
        logging.error(f'{FEATURED_JSON} 없음')
        return {}

    with open(FEATURED_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)

    result = {}
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


def group_by_sector(newhigh_data, wics):
    """모든 기간의 신고가 종목을 섹터별로 그룹핑"""
    all_stocks = {}
    for stocks in newhigh_data.values():
        for s in stocks:
            code = s['code']
            if code not in all_stocks or s['mktcap'] > all_stocks[code]['mktcap']:
                all_stocks[code] = s

    sector_stocks = {}
    for code, stock in all_stocks.items():
        sector = wics.get(code, '기타')
        if sector not in sector_stocks:
            sector_stocks[sector] = []
        sector_stocks[sector].append(stock)

    for sector in sector_stocks:
        sector_stocks[sector].sort(key=lambda x: x['mktcap'], reverse=True)

    return sector_stocks


def search_naver_news(stock_name):
    """네이버 검색 API로 종목 뉴스 검색 (헤드라인 + description)"""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return []

    headers = {
        'X-Naver-Client-Id': NAVER_CLIENT_ID,
        'X-Naver-Client-Secret': NAVER_CLIENT_SECRET,
    }
    params = {
        'query': stock_name,
        'display': 5,
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

    def clean(text):
        text = re.sub(r'<.*?>', '', text)
        return text.replace('&quot;', '"').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')

    results = []
    for item in items:
        title = clean(item.get('title', ''))
        desc = clean(item.get('description', ''))
        results.append({'title': title, 'description': desc})
        if len(results) >= NEWS_PER_STOCK:
            break

    return results


def fix_stock_names(text, correct_names):
    """<b>태그</b> 안의 종목명 오타를 실제 종목명으로 교정
    전략: 이미 정확한 이름은 건드리지 않고, 텍스트에 없는 이름만 오타에서 찾아 교정"""
    from difflib import SequenceMatcher

    # 정확히 존재하지 않는 이름만 교정 대상
    missing = [n for n in correct_names if n not in text]
    if not missing:
        return text

    b_tags = re.findall(r'<b>([^<]+)</b>', text)
    for tag_content in b_tags:
        name_part = re.split(r'[(（]', tag_content)[0].strip()
        if name_part in correct_names:
            continue  # 이미 정확

        # missing 중 가장 유사한 이름 찾기
        best, best_ratio = None, 0
        for m in missing:
            ratio = SequenceMatcher(None, name_part, m).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best = m

        if best and best_ratio >= 0.3:
            suffix = tag_content[len(name_part):]
            text = text.replace(f'<b>{tag_content}</b>', f'<b>{best}{suffix}</b>')
            missing.remove(best)

    return text


def summarize_sector_news(sector, stocks_with_news):
    """Claude API로 섹터별 뉴스 종합 요약"""
    if not ANTHROPIC_API_KEY:
        logging.warning('ANTHROPIC_API_KEY 미설정, 요약 건너뜀')
        return ''

    import anthropic

    correct_names = [name for name, _, _ in stocks_with_news]

    # 프롬프트 구성
    news_text = ''
    for stock_name, chg, news_items in stocks_with_news:
        news_text += f'\n[{stock_name} (등락률: {chg:+.1f}%)]\n'
        for n in news_items:
            news_text += f'- {n["title"]}: {n["description"]}\n'

    prompt = f"""아래는 "{sector}" 섹터에서 신고가를 기록한 종목들의 최신 뉴스입니다.

{news_text}

위 뉴스를 바탕으로 이 섹터의 신고가 배경을 요약해주세요.

구조:
1) 섹터 전체 테마 1~2문장
2) 빈 줄
3) 개별 종목별로 각각 1문장씩, 종목마다 줄바꿈

규칙:
- 한국어로만 작성 (영문 약어/종목명은 허용)
- 투자자가 빠르게 읽을 수 있는 간결한 문체, 존댓말 금지
- 특별히 강한 상승을 보인 종목은 등락률과 함께 언급

출력 형식 (반드시 준수):
- 마크다운 문법(#, **, -, ```, 목록기호) 절대 사용 금지
- 강조할 종목명은 <b>태그</b>로 감싸기
- 제목/헤더 넣지 말 것, 바로 본문부터 시작"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    for attempt in range(2):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.content[0].text.strip()
            # 깨진 유니코드 문자 제거
            text = text.encode('utf-8', errors='ignore').decode('utf-8')
            text = re.sub(r'[\ufffd\udcff-\udfff]', '', text)
            # 종목명 오타 교정
            text = fix_stock_names(text, correct_names)
            return text
        except Exception as e:
            err_str = str(e).lower()
            if '529' in str(e) or 'overloaded' in err_str or '429' in str(e):
                if attempt < 1:
                    logging.warning(f'  요약 재시도 대기 (30초): {e}')
                    time.sleep(30)
                    continue
            logging.error(f'  요약 실패 [{sector}]: {e}')
            return ''


def fetch_news(target_date=None):
    """메인: 신고가 종목 뉴스 수집 + 섹터별 요약"""
    if target_date is None:
        target_date = datetime.now(tz=KST).strftime('%Y-%m-%d')

    logging.info(f'신고가 뉴스 수집 시작: {target_date}')

    newhigh_data = load_newhigh_stocks(target_date)
    if not newhigh_data:
        logging.info('신고가 종목 없음, 스킵')
        return

    logging.info(f'신고가 종목 수: 20일={len(newhigh_data.get("newhigh_20d", []))}, '
                 f'120일={len(newhigh_data.get("newhigh_120d", []))}, '
                 f'52주={len(newhigh_data.get("newhigh_52w", []))}')

    wics = load_wics_mapping()
    sector_stocks = group_by_sector(newhigh_data, wics)
    logging.info(f'섹터 수: {len(sector_stocks)}개')

    # 섹터별 뉴스 수집
    sector_news = {}  # sector -> [(stock_name, chg, [news_items])]
    searched = 0
    for sector, stocks in sector_stocks.items():
        sector_news[sector] = []
        for stock in stocks[:TOP_PER_SECTOR]:
            news_items = search_naver_news(stock['name'])
            if news_items:
                sector_news[sector].append((stock['name'], stock['chg'], news_items))
                searched += 1
                logging.info(f'  [{searched}] {stock["name"]}: {len(news_items)}건')
            time.sleep(0.3)

    logging.info(f'뉴스 수집 완료: {searched}개 종목')

    # 섹터별 Claude 요약
    summaries = {}
    sectors_with_news = {s: items for s, items in sector_news.items() if items}
    logging.info(f'요약 대상 섹터: {len(sectors_with_news)}개')

    for i, (sector, stocks_with_news) in enumerate(sectors_with_news.items()):
        summary = summarize_sector_news(sector, stocks_with_news)
        if summary:
            summaries[sector] = summary
            logging.info(f'  요약 [{i+1}/{len(sectors_with_news)}] {sector}: {len(summary)}자')
        time.sleep(0.5)

    # 저장
    output = {
        'date': target_date,
        'summaries': summaries,
    }
    with open(NEWS_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logging.info(f'저장 완료: {NEWS_JSON} ({len(summaries)}개 섹터 요약)')


if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else None
    fetch_news(target)
