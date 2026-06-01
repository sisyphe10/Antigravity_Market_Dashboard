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
THEME_MIN_STOCKS = 2         # 하단 테마 블록(설명 포함)은 이 종목수 이상 묶인 테마만

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


def _norm_key(label):
    """표기 차이 흡수용 정규화 키: 공백·구두점 제거 + 영문 소문자.
    예) '젠슨황 방한' / '젠슨황방한' → '젠슨황방한' (동일 키)."""
    k = re.sub(r'[\s·・/\\\-_,.()\[\]]+', '', label or '')
    return k.lower()


def normalize_themes(name_to_theme):
    """섹터별 개별 Haiku 호출로 생긴 같은 촉매의 표기 흔들림(주로 띄어쓰기)을
    하나의 대표 라벨로 통일. 정규화 키가 같은 라벨들을 한 그룹으로 묶고,
    대표는 (빈도 최다 → 더 짧은 표기 → 사전순) 우선으로 선택.
    의미는 같지만 표면형이 다른 경우(예: '엔비디아 협력' vs '젠슨황방한')나
    부분포함(예: 'HBM' vs 'HBM4 양산')은 구체성 훼손 우려로 병합하지 않음."""
    from collections import Counter
    labels = [v for v in name_to_theme.values() if v]
    if not labels:
        return name_to_theme
    freq = Counter(labels)
    groups = {}
    for lab in set(labels):
        groups.setdefault(_norm_key(lab), []).append(lab)
    key_to_canon = {}
    for key, labs in groups.items():
        canon = sorted(labs, key=lambda l: (-freq[l], len(l), l))[0]
        key_to_canon[key] = canon
        if len(labs) > 1:
            logging.info('  라벨 정규화: %s → "%s"', sorted(labs), canon)
    for k, v in name_to_theme.items():
        if v:
            name_to_theme[k] = key_to_canon[_norm_key(v)]
    return name_to_theme


def semantic_merge_themes(name_to_theme):
    """2차 통합: 표기 정규화로 못 잡는 '의미는 같은데 표현이 다른' 라벨을
    Claude Haiku 1회 호출로 묶어 대표 라벨로 통일.
    예) '젠슨황방한'/'젠슨황 AI협력'/'젠슨황효과'/'엔비디아 옴니버스' → '젠슨황 방한'.
    애매하면 분리 유지(구체성 보존). 키 없거나 실패 시 원본 그대로."""
    if not ANTHROPIC_API_KEY:
        return name_to_theme
    labels = sorted({v for v in name_to_theme.values() if v})
    if len(labels) < 2:
        return name_to_theme
    import anthropic
    label_list = '\n'.join('- ' + l for l in labels)
    prompt = f"""다음은 오늘 신고가 종목들에 부여된 '구체 촉매' 테마 라벨 목록입니다.
이 중 **의미가 사실상 동일한**(같은 사건·촉매를 가리키는) 라벨들을 한 그룹으로 묶고,
각 라벨을 그룹의 **대표 라벨**로 매핑하세요.

라벨 목록:
{label_list}

규칙(엄수):
- 정말 같은 촉매/이벤트일 때만 묶으세요. 조금이라도 다른 촉매면 따로 두세요(구체성 보존).
  예: '젠슨황방한'·'젠슨황 AI협력'·'젠슨황효과'·'엔비디아 옴니버스' → 모두 엔비디아 CEO 방한 → 대표 '젠슨황 방한'.
  단 'HBM4 양산'과 'AI서버 기판'은 다른 촉매 → 묶지 않음.
- 대표 라벨은 그룹에서 가장 명확·간결한 표현(없으면 새로 간결하게). 최대 12자 내외.
- 묶이지 않는 라벨도 자기 자신을 대표로 그대로 포함.
출력: 모든 입력 라벨을 키로 갖는 JSON {{"원본라벨":"대표라벨", ...}}만. 코드블록·설명 금지."""
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(model=HAIKU_MODEL, max_tokens=2048,
                                       messages=[{"role": "user", "content": prompt}])
        text = resp.content[0].text.strip().encode('utf-8', 'ignore').decode('utf-8')
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if not m:
            logging.warning('  의미통합 JSON 미발견 → 스킵')
            return name_to_theme
        mapping = json.loads(m.group(0))
    except Exception as e:
        logging.warning(f'  의미통합 실패(스킵): {e}')
        return name_to_theme
    merged = {}
    for k, v in name_to_theme.items():
        if v:
            canon = (mapping.get(v) or v).strip()
            canon = re.sub(r'\s+', ' ', canon) or v
            if canon != v:
                merged[v] = canon
            name_to_theme[k] = canon
    for o, c in sorted(merged.items()):
        logging.info('  의미통합: "%s" → "%s"', o, c)
    return name_to_theme


def generate_theme_descriptions(theme_to_stocks, news_by_name):
    """2종목 이상 묶인 각 테마에 대해 '왜 함께 신고가인지' 한 줄(줄글) 설명 생성.
    소속 종목명 + 수집해둔 뉴스 헤드라인을 근거로 Claude Haiku 1회 배치 호출.
    반환: {테마: 설명}. 키 없거나 실패 시 빈 dict."""
    if not ANTHROPIC_API_KEY or not theme_to_stocks:
        return {}
    import anthropic
    blocks = []
    for th, names in theme_to_stocks.items():
        heads = []
        for nm in names:
            for n in (news_by_name.get(nm) or [])[:2]:
                t = (n.get('title') or '').strip()
                if t:
                    heads.append(f'  {nm}: {t}'[:160])
        blocks.append(f'[{th}] 종목: {", ".join(names)}\n' + '\n'.join(heads[:8]))
    body = '\n\n'.join(blocks)
    prompt = f"""다음은 오늘 20일 신고가 종목들을 '구체 촉매' 테마별로 묶은 것입니다.
각 테마에 대해 **왜 이 종목들이 함께 신고가를 기록했는지** 한 줄(한국어 40~70자)로 설명하세요.

{body}

규칙(엄수):
- 구체적 사건·맥락을 담되 간결하게. 일반론("실적 개선", "수급 호조") 금지.
- 종목 나열·등락률 반복 금지(설명에 집중). 한 문장.
출력: {{"테마명":"설명", ...}} 형태의 JSON만. 입력 테마 전부 포함. 코드블록·설명문 금지."""
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(model=HAIKU_MODEL, max_tokens=2048,
                                       messages=[{"role": "user", "content": prompt}])
        text = resp.content[0].text.strip().encode('utf-8', 'ignore').decode('utf-8')
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if not m:
            logging.warning('  테마 설명 JSON 미발견 → 스킵')
            return {}
        desc = json.loads(m.group(0))
        return {k: re.sub(r'\s+', ' ', (v or '').strip()) for k, v in desc.items() if v}
    except Exception as e:
        logging.warning(f'  테마 설명 실패(스킵): {e}')
        return {}


def enrich(path=NEWHIGH_FILE):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    stocks = data.get('stocks', [])           # 20일 신고가 (52주 해당분은 is_52w 플래그)
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
    news_by_name = {}      # 테마 설명 생성에 재사용 (종목명 → 뉴스 리스트)
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
                news_by_name[s['name']] = news
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

    name_to_theme = normalize_themes(name_to_theme)       # 1차: 표기(공백·구두점) 통일
    name_to_theme = semantic_merge_themes(name_to_theme)  # 2차: 의미 동일 라벨 통합

    tagged = 0
    for s in stocks:
        key = (s.get('sector') or '기타', s.get('name'))
        th = name_to_theme.get(key)
        s['theme'] = th if th else ''
        if th:
            tagged += 1

    # 2종목 이상 묶인 테마별 줄글 설명 생성 (봇 하단 테마 블록용)
    theme_to_stocks = {}
    for s in stocks:
        if s.get('theme'):
            theme_to_stocks.setdefault(s['theme'], []).append(s['name'])
    multi = {t: ns for t, ns in theme_to_stocks.items() if len(ns) >= THEME_MIN_STOCKS}
    data['theme_descriptions'] = generate_theme_descriptions(multi, news_by_name)
    logging.info(f'테마 설명: {len(data["theme_descriptions"])}개 (≥{THEME_MIN_STOCKS}종목 테마 {len(multi)}개)')

    data['themes_enriched_at'] = datetime.now(tz=KST).isoformat()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    logging.info(f'테마 부여 완료: {tagged}/{len(stocks)}종목 → {path}')
    return data


if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else NEWHIGH_FILE
    enrich(target)
