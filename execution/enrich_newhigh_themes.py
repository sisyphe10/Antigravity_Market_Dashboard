"""
20일 신고가 종목별 "구체 촉매" 테마 부여 → newhigh_20d.json의 각 종목 theme 필드 채움.

흐름 (fetch_featured_data_kis.py 직후 ~15:55 KST, 16:00 봇 전송 전 실행):
1) newhigh_20d.json 로드 (fetch_featured_data_kis.py 산출물).
2) 종목별 네이버 뉴스 최신 5건 수집 (NAVER API, sort=date — fetch_featured_news.py 패턴).
3) 섹터 단위 배치로 묶어 Claude Haiku에게 전달 → 종목별 구체 촉매 키워드 1개 부여.
   - 등락률을 함께 전달해 "같은 촉매면 같은 라벨"이 되도록 유도.
   - 일반론(조선수주/방산수혜/반도체호황) 금지. 구체 키워드(핵잠수함/MASGA/HBM) 지향.
4) 결과를 newhigh_20d.json의 각 종목 theme에 기록 (in-place, 다른 필드 보존).

키 요구사항(VM .env 전용): NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, ANTHROPIC_API_KEY.

실행:  python3 execution/enrich_newhigh_themes.py [newhigh_20d.json 경로]
"""
import sys
import os
import json
import re
import time
import logging
import requests
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
                    stream=sys.stdout)

KST = timezone(timedelta(hours=9))
NEWHIGH_FILE = 'newhigh_20d.json'

# 비용/지연 통제: 거래대금 상위 종목 위주로 테마 부여 (나머지는 무테마 → 섹터 1단 노출)
MAX_STOCKS_PER_SECTOR = 12   # 섹터당 테마 부여 상한 (거래대금순)
NEWS_PER_STOCK = 5           # 종목당 뉴스 헤드라인 수 (지침: 최신 5건)
MIN_SECTOR_SIZE = 1          # 1종목 섹터도 테마 부여

from dotenv import load_dotenv
load_dotenv()
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

HAIKU_MODEL = 'claude-haiku-4-5-20251001'


def _clean(text):
    text = re.sub(r'<.*?>', '', text)
    return (text.replace('&quot;', '"').replace('&amp;', '&')
                .replace('&lt;', '<').replace('&gt;', '>').replace('&#39;', "'"))


def search_naver_news(stock_name):
    """네이버 검색 API로 종목 뉴스 (헤드라인 + description). fetch_featured_news 패턴."""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return []
    headers = {
        'X-Naver-Client-Id': NAVER_CLIENT_ID,
        'X-Naver-Client-Secret': NAVER_CLIENT_SECRET,
    }
    params = {'query': stock_name, 'display': NEWS_PER_STOCK, 'sort': 'date'}
    try:
        r = requests.get('https://openapi.naver.com/v1/search/news.json',
                         headers=headers, params=params, timeout=5)
        r.raise_for_status()
        items = r.json().get('items', [])
    except Exception as e:
        logging.warning(f'뉴스 검색 실패 [{stock_name}]: {e}')
        return []

    out = []
    for item in items:
        out.append({
            'title': _clean(item.get('title', '')),
            'description': _clean(item.get('description', '')),
        })
        if len(out) >= NEWS_PER_STOCK:
            break
    return out


def assign_sector_themes(sector, stocks_with_news):
    """
    Claude Haiku로 섹터 배치 → {종목명: 구체촉매 라벨}.
    stocks_with_news: [(name, chg, [news_items]), ...]
    반환: {name: theme}  (라벨 없으면 키 생략)
    """
    if not ANTHROPIC_API_KEY:
        logging.warning('ANTHROPIC_API_KEY 미설정, 테마 건너뜀')
        return {}
    if not stocks_with_news:
        return {}

    import anthropic

    names = [n for n, _, _ in stocks_with_news]

    blocks = []
    for name, chg, news in stocks_with_news:
        sign = '+' if (chg or 0) >= 0 else ''
        lines = [f'[{name}] (등락률 {sign}{chg}%)']
        for n in news:
            t = n.get('title', '').strip()
            d = n.get('description', '').strip()
            if t:
                lines.append(f'- {t}: {d}'[:200])
        blocks.append('\n'.join(lines))
    news_text = '\n\n'.join(blocks)

    prompt = f"""다음은 "{sector}" 섹터에서 오늘 20일 신고가를 기록한 종목들의 최신 뉴스입니다.
각 종목이 신고가를 만든 **구체적인 촉매(catalyst)**를 한 개의 짧은 키워드로 뽑아주세요.

{news_text}

규칙(엄수):
- 일반론·뻔한 말 금지. 나쁜 예: "조선수주", "방산수혜", "반도체호황", "실적개선", "수급개선".
- 구체적이어야 함. 좋은 예: "핵잠수함", "MASGA", "HBM", "AI데이터센터 전력", "스테이블코인", "휴머노이드".
- 같은 촉매로 함께 움직인 종목들은 **반드시 동일한 라벨**을 부여(등락률·뉴스 맥락 참고).
- 라벨은 한국어 명사구 1개, 최대 12자 내외. 종목명·등락률·문장 금지.
- 뉴스만으로 구체 촉매를 못 찾으면 그 종목은 라벨을 비워두세요(빈 문자열).

출력: 아래 JSON만 출력. 코드블록·설명·마크다운 금지.
{{{', '.join(f'"{n}": "라벨"' for n in names)}}}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    for attempt in range(2):
        try:
            resp = client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            text = text.encode('utf-8', errors='ignore').decode('utf-8')
            # 코드블록/잡텍스트 제거 → 첫 { ~ 마지막 } 추출
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if not m:
                logging.warning(f'  [{sector}] JSON 미발견: {text[:120]}')
                return {}
            parsed = json.loads(m.group(0))
            result = {}
            for name in names:
                lab = (parsed.get(name) or '').strip()
                lab = re.sub(r'\s+', ' ', lab)
                if lab:
                    result[name] = lab
            return result
        except Exception as e:
            err = str(e).lower()
            if '529' in str(e) or 'overloaded' in err or '429' in str(e):
                if attempt < 1:
                    logging.warning(f'  [{sector}] 재시도 대기(30s): {e}')
                    time.sleep(30)
                    continue
            logging.error(f'  테마 실패 [{sector}]: {e}')
            return {}
    return {}


def enrich(path=NEWHIGH_FILE):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    stocks = data.get('stocks', [])
    if not stocks:
        logging.info('신고가 종목 없음, 스킵')
        return data

    logging.info(f'신고가 {len(stocks)}종목 → 테마 부여 시작 (date={data.get("date")})')

    by_sector = {}
    for s in stocks:
        by_sector.setdefault(s.get('sector') or '기타', []).append(s)
    for sec in by_sector:
        by_sector[sec].sort(key=lambda x: x.get('trdval', 0), reverse=True)

    name_to_theme = {}
    sec_order = sorted(by_sector, key=lambda k: -len(by_sector[k]))
    for sec in sec_order:
        group = by_sector[sec]
        if len(group) < MIN_SECTOR_SIZE:
            continue
        targets = group[:MAX_STOCKS_PER_SECTOR]
        stocks_with_news = []
        for s in targets:
            news = search_naver_news(s['name'])
            if news:
                stocks_with_news.append((s['name'], s.get('chg', 0), news))
            time.sleep(0.3)
        if not stocks_with_news:
            logging.info(f'  [{sec}] 뉴스 없음 → 스킵')
            continue
        themes = assign_sector_themes(sec, stocks_with_news)
        applied = 0
        for s in targets:
            th = themes.get(s['name'])
            if th:
                name_to_theme[(sec, s['name'])] = th
                applied += 1
        logging.info(f'  [{sec}] {len(stocks_with_news)}종목 뉴스 → {applied}개 테마 부여')
        time.sleep(0.5)

    tagged = 0
    for s in stocks:
        key = (s.get('sector') or '기타', s.get('name'))
        th = name_to_theme.get(key)
        s['theme'] = th if th else ''
        if th:
            tagged += 1

    data['themes_enriched_at'] = datetime.now(tz=KST).isoformat()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    logging.info(f'테마 부여 완료: {tagged}/{len(stocks)}종목 → {path}')
    return data


if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else NEWHIGH_FILE
    enrich(target)
