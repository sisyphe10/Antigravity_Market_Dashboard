"""
한국원전수출산업협회(KNA) 세계원전시장동향 게시판 신규 글 수집.

사용:
  - import 하여 fetch_new_posts() 호출 (ra_sisyphe_bot.py에서 사용)
  - CLI로 직접 실행 시 dry-run (state 갱신 없이 신규 글 미리보기)

state 파일: DASHBOARD_DIR/kna_state.json — last_seen_num(internal num) 저장.
"""
import os
import re
import json
import html
import requests
from html.parser import HTMLParser

BOARD_BASE = 'https://e-kna.org/web/home.php?go=Emenu_01&go_pds=pds_text_list&pds_num=68&start=0'

DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(DASHBOARD_DIR, 'kna_state.json')

UA = {'User-Agent': 'Mozilla/5.0 (compatible; KNANewsBot/1.0)'}

PAGE_SIZE = 10
MAX_PAGES = 10


def _board_url(start=0):
    return (
        'https://e-kna.org/web/home.php?go=Emenu_01&go_pds=pds_text_list'
        f'&pds_num=68&start={start}&num=&mode=&field=&s_que=&s_memo_2='
    )


def _build_post_url(num):
    return f'{BOARD_BASE}&num={num}&mode=&field=&s_que=&s_memo_2='


def _fetch_html(url):
    r = requests.get(url, headers=UA, timeout=20)
    r.encoding = 'utf-8'
    return r.text


def parse_board_list(html_text):
    """게시판 목록에서 (internal_num, 표시번호, 제목, 작성일) 추출."""
    posts = []
    pattern = re.compile(
        r'<tr>\s*'
        r'<td[^>]*>\s*(?:<b><span[^>]*>)?\s*-?\s*(\d+)\s*-?\s*(?:</span></b>)?\s*</td>\s*'
        r'<td>\s*<a href="[^"]*num=(\d+)[^"]*">([^<]+)</a>.*?</td>\s*'
        r'<td[^>]*>([^<]*)</td>\s*'
        r'<td[^>]*>(\d{4}-\d{2}-\d{2})</td>',
        re.DOTALL,
    )
    for m in pattern.finditer(html_text):
        display_no = m.group(1).strip()
        internal_num = int(m.group(2))
        title = html.unescape(m.group(3).strip())
        date_str = m.group(5).strip()
        posts.append({
            'num': internal_num,
            'display_no': display_no,
            'title': title,
            'date': date_str,
            'url': _build_post_url(internal_num),
        })
    return posts


class _BodyTextExtractor(HTMLParser):
    """<div id='max_memo'> 내부 텍스트만 추출. <p>, <br> → 줄바꿈."""

    def __init__(self):
        super().__init__()
        self.in_target = False
        self.depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        if not self.in_target and tag == 'div' and attrs_d.get('id') == 'max_memo':
            self.in_target = True
            self.depth = 1
            return
        if self.in_target:
            if tag == 'div':
                self.depth += 1
            if tag in ('br', 'p', 'li', 'tr'):
                self.parts.append('\n')

    def handle_endtag(self, tag):
        if self.in_target and tag == 'div':
            self.depth -= 1
            if self.depth == 0:
                self.in_target = False
                return
        if self.in_target and tag in ('p', 'li', 'tr'):
            self.parts.append('\n')

    def handle_data(self, data):
        if self.in_target:
            self.parts.append(data)

    def get_text(self):
        text = ''.join(self.parts)
        text = html.unescape(text)
        text = text.replace('\xa0', ' ')
        text = re.sub(r'[ \t]+', ' ', text)
        # 1) "※ 원문 :" 으로 시작하는 줄 제거
        skip_re = re.compile(r'^\s*※\s*원문\s*[:：]')
        filtered = [ln for ln in text.split('\n') if not skip_re.match(ln)]
        # 2) 공백만 있는 줄도 빈 줄로 취급, 연속 빈 줄은 1개로 압축
        cleaned = []
        prev_blank = False
        for ln in filtered:
            ln = ln.rstrip()
            is_blank = not ln.strip()
            if is_blank and prev_blank:
                continue
            cleaned.append('' if is_blank else ln)
            prev_blank = is_blank
        return '\n'.join(cleaned).strip()


_TITLE_RE = re.compile(
    r'<th[^>]*>\s*제목\s*(?:<!--[^>]*-->)?\s*</th>\s*<td[^>]*colspan="3"[^>]*>([^<]+)</td>',
    re.DOTALL,
)


def fetch_post_detail(url):
    """본문 페이지에서 (정확한 제목, 본문 텍스트) 반환."""
    text = _fetch_html(url)
    title = ''
    m = _TITLE_RE.search(text)
    if m:
        title = html.unescape(m.group(1).strip())
    parser = _BodyTextExtractor()
    parser.feed(text)
    return title, parser.get_text()


def _load_state():
    if not os.path.exists(STATE_FILE):
        return {'last_seen_num': 0}
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'last_seen_num': 0}


def _save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fetch_new_posts(update_state=True):
    """신규 게시글(state 이후) 수집.
    최초 실행(state 파일 없음) 시에는 알림 없이 last_seen만 현재 최신으로 초기화.
    페이지네이션: 최대 MAX_PAGES 페이지를 돌되, 페이지의 최소 num이 last_seen 이하면 조기 종료.
    """
    state_existed = os.path.exists(STATE_FILE)
    state = _load_state()
    last_seen = int(state.get('last_seen_num') or 0)

    posts = []
    seen_nums = set()
    for page in range(MAX_PAGES):
        page_html = _fetch_html(_board_url(page * PAGE_SIZE))
        page_posts = parse_board_list(page_html)
        if page == 0 and not page_posts:
            raise RuntimeError('KNA 게시판 파싱 0건 (HTML 구조 변경 가능성)')
        if not page_posts:
            break
        for p in page_posts:
            if p['num'] not in seen_nums:
                seen_nums.add(p['num'])
                posts.append(p)
        if min(p['num'] for p in page_posts) <= last_seen:
            break

    if not posts:
        return []

    max_num = max(p['num'] for p in posts)

    if not state_existed:
        if update_state:
            _save_state({'last_seen_num': max_num})
        return []

    new_posts = [p for p in posts if p['num'] > last_seen]
    new_posts.sort(key=lambda p: p['num'])

    for p in new_posts:
        try:
            title, body = fetch_post_detail(p['url'])
            if title:
                p['title'] = title
            p['body'] = body
        except Exception as e:
            p['body'] = f'(본문 수집 실패: {e})'

    if update_state:
        _save_state({'last_seen_num': max_num})

    return new_posts


if __name__ == '__main__':
    posts = fetch_new_posts(update_state=False)
    print(f'신규 게시글 수: {len(posts)}')
    for p in posts:
        print('-' * 60)
        print(f"[{p['display_no']}] {p['title']} ({p['date']})")
        print(p['url'])
        body = p.get('body', '')
        print(body[:500] + ('...' if len(body) > 500 else ''))
