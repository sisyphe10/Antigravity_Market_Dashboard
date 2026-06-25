"""
원전수출정보지원시스템(k-neiss.org) '세계원전시장동향' 게시판 신규 글 수집.

배경: 2026-06 한국원전수출산업협회가 미국 동향 콘텐츠를 회원 전용으로 전환.
기존 e-kna.org(fetch_kna_news.py)는 미국 글 본문이 회원가입 안내문으로 대체됨.
k-neiss.org 회원 게시판으로 전환하여 미국 본문까지 수집한다.

구조(검증 완료):
  - 목록: GET  /portal/news/global/list.do?mid=0703000000   (비로그인 공개)
          각 글 <a data-req-p-idx="NNNNN">, 카테고리 '미국원전시장동향'/'세계원전시장동향'
  - 본문: POST /portal/news/global/view.do?mid=0703000000  body=idx=NNNNN
          '세계원전시장동향' → 비로그인 공개 / '미국원전시장동향' → 로그인 세션 필요
  - 로그인: GET  /portal/newUser/loginForm.do (TOKEN_KEY hidden 파싱)
            POST /portal/knaMember/login  (lId/lPassword/TOKEN_KEY)
            JSON {success, procCode, msg}, 개인회원 procCode='MEMBER_USER'
            자격증명: .env 의 KNEISS_ID / KNEISS_PW

state 파일: DASHBOARD_DIR/kna_state.json — 'last_seen_kneiss_idx' 저장
  (기존 e-kna 'last_seen_num' 키는 호환을 위해 그대로 둠)

사용:
  - import 하여 fetch_new_posts() 호출 (sources/kna.py 어댑터에서 사용)
  - CLI 직접 실행 시 dry-run (state 갱신 없이 신규 글 미리보기)
"""
import os
import re
import json
import html

import requests
from dotenv import load_dotenv

BASE = 'https://k-neiss.org'
MID = '0703000000'
LIST_PATH = f'/portal/news/global/list.do?mid={MID}'
VIEW_PATH = f'/portal/news/global/view.do?mid={MID}'
LOGIN_FORM_PATH = '/portal/newUser/loginForm.do'
LOGIN_POST_PATH = '/portal/knaMember/login'

DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(DASHBOARD_DIR, 'kna_state.json')
STATE_KEY = 'last_seen_kneiss_idx'

load_dotenv(os.path.join(DASHBOARD_DIR, '.env'))

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; KNEISSNewsBot/1.0)'}

MAX_PAGES = 5
REQ_TIMEOUT = 25


class KneissError(Exception):
    """k-neiss 수집 일반 오류."""


class KneissLoginError(KneissError):
    """로그인 실패."""


# ── URL 헬퍼 ────────────────────────────────────────────────────────────────

def _list_url(page=1):
    return f'{BASE}{LIST_PATH}&page={page}'


def _board_link():
    """게시글 개별 GET 영구링크가 없으므로(POST 전용) 게시판 목록 URL 반환."""
    return f'{BASE}{LIST_PATH}'


# ── 세션 / 로그인 ───────────────────────────────────────────────────────────

def _make_session():
    s = requests.Session()
    s.headers.update(UA)
    return s


def _login(session):
    """k-neiss 개인 계정 로그인. 성공 시 세션에 인증 쿠키 설정.
    실패 시 KneissLoginError."""
    uid = os.getenv('KNEISS_ID')
    pw = os.getenv('KNEISS_PW')
    if not uid or not pw:
        raise KneissLoginError('KNEISS_ID/KNEISS_PW 환경변수 없음')

    # 1) 로그인 폼 GET → TOKEN_KEY + #form 필드 수집 (CSRF 토큰은 세션별 발급)
    try:
        r = session.get(f'{BASE}{LOGIN_FORM_PATH}', timeout=REQ_TIMEOUT)
    except requests.RequestException as e:
        raise KneissLoginError(f'로그인 폼 GET 실패: {e}')
    fm = re.search(r'<form\b[^>]*id="form"[^>]*>(.*?)</form>', r.text, re.DOTALL)
    form_html = fm.group(1) if fm else r.text
    fields = {}
    for m in re.finditer(r'<input\b[^>]*>', form_html):
        name = re.search(r'name="([^"]+)"', m.group(0))
        if not name:
            continue
        val = re.search(r'value="([^"]*)"', m.group(0))
        fields[name.group(1)] = val.group(1) if val else ''
    if 'TOKEN_KEY' not in fields:
        raise KneissLoginError('로그인 폼에서 TOKEN_KEY 파싱 실패 (구조 변경 가능성)')

    # 2) 로그인 POST (ajaxSubmit 와 동일: #form 직렬화 + lId/lPassword)
    fields['lId'] = uid
    fields['lPassword'] = pw
    try:
        r2 = session.post(
            f'{BASE}{LOGIN_POST_PATH}', data=fields, timeout=REQ_TIMEOUT,
            headers={'X-Requested-With': 'XMLHttpRequest',
                     'Referer': f'{BASE}{LOGIN_FORM_PATH}'},
        )
    except requests.RequestException as e:
        raise KneissLoginError(f'로그인 POST 실패: {e}')
    try:
        j = r2.json()
    except ValueError:
        raise KneissLoginError(f'로그인 응답 JSON 아님 (HTTP {r2.status_code})')
    if not j.get('success'):
        raise KneissLoginError(f"로그인 거부: {j.get('msg') or j.get('procCode') or 'ID/PW 확인'}")
    return j.get('procCode')


# ── 목록 파싱 ───────────────────────────────────────────────────────────────

def parse_board_list(html_text):
    """게시판 목록에서 (idx, display_no, category, 제목, 날짜) 추출. 최신순.

    행 구조:
      <td class="list-num"> 7834 </td>            게시판 번호
      <td class="list-etc mo-tit"> 미국원전시장동향 </td>  카테고리
      <td class="list-subj ..."><a data-req-p-idx="21347" ...>제목</a></td>
      <td class="list-etc mo-tit"> 14 </td>       조회수
      <td class="list-company mo-tit"> 2026-06-24 </td>  날짜
    """
    posts = []
    seen = set()
    for row in re.findall(r'<tr>(.*?)</tr>', html_text, re.DOTALL):
        mi = re.search(r'data-req-p-idx="(\d+)"', row)
        if not mi:
            continue
        idx = int(mi.group(1))
        if idx in seen:
            continue
        seen.add(idx)
        mn = re.search(r'list-num"[^>]*>\s*(\d+)', row)
        display_no = mn.group(1) if mn else str(idx)
        mc = re.search(r'(미국원전시장동향|세계원전시장동향)', row)
        category = mc.group(1) if mc else ''
        mt = re.search(r'data-req-p-idx="\d+"[^>]*>(.*?)</a>', row, re.DOTALL)
        title = html.unescape(re.sub(r'<[^>]+>', '', mt.group(1)).strip()) if mt else ''
        md = re.search(r'(\d{4}-\d{2}-\d{2})', row)
        date_str = md.group(1) if md else ''
        posts.append({
            'idx': idx,
            'display_no': display_no,
            'category': category,
            'title': title,
            'date': date_str,
        })
    return posts


# ── 본문 추출 ───────────────────────────────────────────────────────────────

def _clean_body(text):
    text = html.unescape(text)
    text = text.replace('\xa0', ' ')
    text = re.sub(r'[ \t]+', ' ', text)
    skip_re = re.compile(r'^\s*※\s*원문\s*[:：]')
    lines = [ln for ln in text.split('\n') if not skip_re.match(ln)]
    cleaned = []
    prev_blank = False
    for ln in lines:
        ln = ln.rstrip()
        is_blank = not ln.strip()
        if is_blank and prev_blank:
            continue
        cleaned.append('' if is_blank else ln)
        prev_blank = is_blank
    return '\n'.join(cleaned).strip()


def parse_detail(html_text):
    """view.do 응답에서 (제목, 날짜, 본문, paywalled) 추출.

    paywalled=True → 회원전용 차단(news_view/본문 영역 없음).
    """
    nv = re.search(
        r'<div[^>]*class="[^"]*news_view[^"]*"[^>]*>(.*?)<div class="taR',
        html_text, re.DOTALL,
    )
    if not nv:
        # news_view 컨테이너 자체가 없으면 회원전용 차단으로 간주
        return '', '', '', True
    block = nv.group(1)

    title = ''
    ms = re.search(r'<span class="subject">(.*?)</span>', block, re.DOTALL)
    if ms:
        title = html.unescape(re.sub(r'<[^>]+>', '', ms.group(1)).strip())

    date_str = ''
    for md in re.finditer(r'<span class="date">(.*?)</span>', block, re.DOTALL):
        d = re.sub(r'<[^>]+>', '', md.group(1)).strip()
        if re.match(r'\d{4}-\d{2}-\d{2}', d):
            date_str = d[:10]
            break

    body = ''
    mt = re.search(r'<div[^>]*class="[^"]*\btext\b[^"]*"[^>]*>(.*?)</div>',
                   block, re.DOTALL)
    if mt:
        raw = mt.group(1)
        raw = re.sub(r'<\s*br\s*/?\s*>', '\n', raw, flags=re.I)
        raw = re.sub(r'</\s*p\s*>', '\n', raw, flags=re.I)
        raw = re.sub(r'<[^>]+>', '', raw)
        body = _clean_body(raw)

    paywalled = not body
    return title, date_str, body, paywalled


def fetch_post_detail(session, idx):
    """본문 페이지 POST → (제목, 날짜, 본문, paywalled)."""
    r = session.post(
        f'{BASE}{VIEW_PATH}',
        data={'idx': str(idx), 'searchCondition': '', 'searchTxt': '', 'page': '1'},
        timeout=REQ_TIMEOUT,
        headers={'Referer': f'{BASE}{LIST_PATH}'},
    )
    return parse_detail(r.text)


# ── state ───────────────────────────────────────────────────────────────────

def _load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def save_last_seen(idx):
    """기존 state(e-kna last_seen_num 등)는 보존하고 k-neiss idx만 갱신."""
    state = _load_state()
    state[STATE_KEY] = int(idx)
    _save_state(state)


# ── 메인 ────────────────────────────────────────────────────────────────────

def fetch_new_posts(update_state=True):
    """신규 게시글(state 이후) 수집.

    최초 실행(STATE_KEY 없음) 시에는 알림 없이 last_seen 만 현재 최신으로 초기화.
    로그인 실패해도 비-미국(세계원전시장동향) 본문은 공개라 정상 수집되고,
    미국(미국원전시장동향) 본문은 paywalled=True 로 표시된다.
    """
    state = _load_state()
    initialized = STATE_KEY in state
    last_seen = int(state.get(STATE_KEY) or 0)

    # 목록 수집 (페이지네이션: 최소 idx 가 last_seen 이하가 될 때까지)
    posts = []
    seen_idx = set()
    for page in range(1, MAX_PAGES + 1):
        try:
            r = requests.get(_list_url(page), headers=UA, timeout=REQ_TIMEOUT)
        except requests.RequestException as e:
            if page == 1:
                raise KneissError(f'목록 GET 실패: {e}')
            break
        page_posts = parse_board_list(r.text)
        if page == 1 and not page_posts:
            raise KneissError('k-neiss 목록 파싱 0건 (HTML 구조 변경 가능성)')
        if not page_posts:
            break
        for p in page_posts:
            if p['idx'] not in seen_idx:
                seen_idx.add(p['idx'])
                posts.append(p)
        if min(p['idx'] for p in page_posts) <= last_seen:
            break

    if not posts:
        return []

    max_idx = max(p['idx'] for p in posts)

    # 최초 실행: 알림 없이 현재 최신으로 기준선 설정.
    # 파이프라인이 update_state=False 로 호출하므로 여기서 저장하지 않으면
    # 영영 초기화되지 않아 신규 글을 영구히 못 본다 → update_state 무관하게 baseline 저장.
    if not initialized:
        save_last_seen(max_idx)
        return []

    new_posts = [p for p in posts if p['idx'] > last_seen]
    new_posts.sort(key=lambda p: p['idx'])
    if not new_posts:
        return []

    # 세션 로그인 (실패해도 진행 — 비미국은 공개)
    session = _make_session()
    login_ok = False
    try:
        _login(session)
        login_ok = True
    except KneissLoginError as e:
        print(f'[경고] k-neiss 로그인 실패: {e} — 미국 본문은 회원전용 표시됨')

    out = []
    for p in new_posts:
        try:
            title, date_str, body, paywalled = fetch_post_detail(session, p['idx'])
            if title:
                p['title'] = title
            if date_str:
                p['date'] = date_str
            p['body'] = body
            p['paywalled'] = paywalled
        except Exception as e:
            p['body'] = f'(본문 수집 실패: {e})'
            p['paywalled'] = False
        p['login_ok'] = login_ok
        out.append(p)

    if update_state:
        save_last_seen(max_idx)

    return out


if __name__ == '__main__':
    items = fetch_new_posts(update_state=False)
    print(f'신규 게시글 수: {len(items)}')
    for p in items:
        print('-' * 60)
        flag = ' [회원전용-차단]' if p.get('paywalled') else ''
        print(f"[{p.get('category', '')}] {p['title']} ({p['date']}) idx={p['idx']}{flag}")
        body = p.get('body', '')
        print(body[:500] + ('...' if len(body) > 500 else ''))
