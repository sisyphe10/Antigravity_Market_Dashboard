"""
원전수출정보지원시스템(k-neiss.org) '세계원전시장동향' 게시판 신규 글 수집.

배경: 2026-06 한국원전수출산업협회가 미국 동향 콘텐츠를 회원 전용으로 전환.
기존 e-kna.org(fetch_kna_news.py)는 미국 글 본문이 회원가입 안내문으로 대체됨.
k-neiss.org 회원 게시판으로 전환하여 미국 본문까지 수집한다.

구조(2026-08 사이트 Next.js 전면 개편 반영 — 검증 완료):
  - 목록: GET  /news?newsDiv=GLOBAL%2CUS&page=N   (비로그인 공개, SSR HTML)
          각 글 <a href="/news/{idx}">, 카테고리 '미국원전시장동향'/'세계원전시장동향'
  - 본문: GET  /news/{idx}
          '세계원전시장동향' → 비로그인 공개 / '미국원전시장동향' → 로그인 세션 필요
          (비로그인 미국 글은 news_view 컨테이너 자체가 없음 → paywalled 판정)
  - 로그인: POST /api/v1/kna/auth/login  JSON {loginId, password}
            응답 JSON {success, data:{procCode}, message}, 개인회원 procCode='MEMBER_USER'
            쿠키 kneiss_access_token / kna_rt. CSRF 토큰(TOKEN_KEY) 폐지됨.
            자격증명: .env 의 KNEISS_ID / KNEISS_PW
  - 첨부: <div class="file_box"> <a href="/common/file/download.do?atchFileId=..&fileSn=..">
          다운로드 엔드포인트는 구버전과 동일, 마크업만 변경.

(구) 2026-06~07 구조: /portal/news/global/list.do + data-req-p-idx 앵커 +
POST view.do + /portal/knaMember/login — 2026-08-05 개편으로 전부 404/폐지.

state 파일: DASHBOARD_DIR/kna_state.json — 'last_seen_kneiss_idx' 저장
  (기존 e-kna 'last_seen_num' 키는 호환을 위해 그대로 둠.
   idx 채번은 개편 후에도 연속 — 21513(구) → 21517+(신))

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
NEWS_DIV = 'GLOBAL%2CUS'  # 세계+미국 원전시장동향 통합 게시판
LOGIN_POST_PATH = '/api/v1/kna/auth/login'

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
    return f'{BASE}/news?newsDiv={NEWS_DIV}&page={page}'


def _post_link(idx):
    """게시글 영구링크 (2026-08 개편으로 GET 개별 링크 생김)."""
    return f'{BASE}/news/{idx}'


def _board_link():
    """게시판 목록 URL (구버전 호환용 — 개별 글은 _post_link 사용)."""
    return f'{BASE}/news'


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

    try:
        r = session.post(
            f'{BASE}{LOGIN_POST_PATH}',
            json={'loginId': uid, 'password': pw},
            headers={'Accept': 'application/json', 'Referer': f'{BASE}/login'},
            timeout=REQ_TIMEOUT,
        )
    except requests.RequestException as e:
        raise KneissLoginError(f'로그인 POST 실패: {e}')
    try:
        j = r.json()
    except ValueError:
        raise KneissLoginError(f'로그인 응답 JSON 아님 (HTTP {r.status_code})')
    if not j.get('success') or j.get('data') is None:
        raise KneissLoginError(f"로그인 거부: {j.get('message') or 'ID/PW 확인'}")
    return (j.get('data') or {}).get('procCode')


# ── 목록 파싱 ───────────────────────────────────────────────────────────────

def parse_board_list(html_text):
    """게시판 목록에서 (idx, display_no, category, 제목, 날짜) 추출. 최신순.

    행 구조(2026-08 개편):
      <td class="list-num">8002</td>                          게시판 번호
      <td class="list-etc mo-tit">..<span>세계원전시장동향</span></td>  카테고리
      <td class="list-subj .."><a href="/news/21521"><strong>제목</strong></a></td>
      <td class="list-etc mo-tit">..<span>2</span></td>       조회수
      <td class="list-company mo-tit">..<span>2026-08-05</span></td>  날짜
    """
    posts = []
    seen = set()
    for row in re.findall(r'<tr>(.*?)</tr>', html_text, re.DOTALL):
        mi = re.search(r'<a href="/news/(\d+)"', row)
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
        mt = re.search(r'<a href="/news/\d+"[^>]*>(.*?)</a>', row, re.DOTALL)
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
    """상세 페이지에서 (제목, 날짜, 본문, paywalled) 추출.

    paywalled=True → 회원전용 차단(news_view 컨테이너도, 본문/이미지/첨부도 없음).
    본문 텍스트가 없어도 이미지·첨부가 있으면 정상 게시글이다
    (월간 종합 글이 이미지+PDF 첨부 형식으로 게시됨).
    제목 span 안에 <span class="blue bold">[NEW] </span> 배지가 중첩될 수 있어
    바깥 span 닫힘(</span></div>)까지 잡은 뒤 태그 제거 + [NEW] 접두 제거.
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
    ms = re.search(r'<span class="subject">(.*?)</span></div>', block, re.DOTALL)
    if not ms:
        ms = re.search(r'<span class="subject">(.*?)</span>', block, re.DOTALL)
    if ms:
        title = html.unescape(re.sub(r'<[^>]+>', '', ms.group(1)).strip())
        title = re.sub(r'^\[NEW\]\s*', '', title)

    date_str = ''
    for md in re.finditer(r'<span class="date">(.*?)</span>', block, re.DOTALL):
        d = re.sub(r'<[^>]+>', '', md.group(1)).strip()
        if re.match(r'\d{4}-\d{2}-\d{2}', d):
            date_str = d[:10]
            break

    body = ''
    has_img = False
    mt = re.search(r'<div[^>]*class="[^"]*\btext\b[^"]*"[^>]*>(.*?)</div>',
                   block, re.DOTALL)
    if mt:
        raw = mt.group(1)
        has_img = re.search(r'<img\b', raw, re.I) is not None
        raw = re.sub(r'<\s*br\s*/?\s*>', '\n', raw, flags=re.I)
        raw = re.sub(r'</\s*p\s*>', '\n', raw, flags=re.I)
        raw = re.sub(r'<[^>]+>', '', raw)
        body = _clean_body(raw)

    paywalled = not body and not has_img and not parse_attachments(block)
    return title, date_str, body, paywalled


def parse_attachments(html_text):
    """첨부파일 목록 [(파일명, atchFileId, fileSn)] 추출.

    마크업(2026-08 개편): <div class="file_box .."><ul class="file_list">
      <li><a href="/common/file/download.do?atchFileId=HEX&amp;fileSn=HEX" ..>이름.pdf</a></li>
    """
    atts = []
    for m in re.finditer(
        r'<a href="/common/file/download\.do\?atchFileId=([0-9A-Fa-f]+)'
        r'&(?:amp;)?fileSn=([0-9A-Fa-f]+)"[^>]*>(.*?)</a>',
        html_text, re.DOTALL,
    ):
        atts.append({
            'name': html.unescape(re.sub(r'<[^>]+>', '', m.group(3)).strip()),
            'atch_file_id': m.group(1),
            'file_sn': m.group(2),
        })
    return atts


PDF_TEXT_MAX = 12000  # 텔레그램 분할 발송(4000자 청크) 감안 상한


def _fetch_pdf_text(session, att):
    """첨부 PDF 다운로드 → 텍스트 추출. 실패 시 '' (발송은 계속)."""
    try:
        r = session.get(
            f'{BASE}/common/file/download.do',
            params={'atchFileId': att['atch_file_id'], 'fileSn': att['file_sn']},
            timeout=REQ_TIMEOUT,
        )
        if r.status_code != 200 or not r.content.startswith(b'%PDF'):
            return ''
        import io
        from pypdf import PdfReader
        pages = [p.extract_text() or '' for p in PdfReader(io.BytesIO(r.content)).pages]
        text = re.sub(r'^\s*-\s*\d+\s*-\s*$', '', '\n'.join(pages), flags=re.M)  # 페이지 번호
        text = _clean_body(text)
        if len(text) > PDF_TEXT_MAX:
            text = text[:PDF_TEXT_MAX] + '\n…(이하 생략 — 원문 PDF 참조)'
        return text.strip()
    except Exception:
        return ''


def fetch_post_detail(session, idx):
    """상세 페이지 GET → (제목, 날짜, 본문, paywalled).

    본문이 이미지/첨부 전용이면 PDF 첨부에서 텍스트를 추출해 본문으로 쓰고,
    추출 불가 시 첨부 안내 문구로 대체한다.
    """
    r = session.get(
        _post_link(idx),
        timeout=REQ_TIMEOUT,
        headers={'Referer': _list_url(1)},
    )
    title, date_str, body, paywalled = parse_detail(r.text)
    if not paywalled and not body:
        atts = parse_attachments(r.text)
        pdf = next((a for a in atts if a['name'].lower().endswith('.pdf')), None)
        if pdf:
            body = _fetch_pdf_text(session, pdf)
        if not body:
            body = '(본문이 이미지/첨부파일 형식입니다 — 원문 링크 참조)'
        if atts:
            body += '\n\n📎 첨부: ' + ' / '.join(a['name'] for a in atts)
    return title, date_str, body, paywalled


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
