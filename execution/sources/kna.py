"""KNA 세계원전시장동향 어댑터 (원전수출정보지원시스템 k-neiss.org).

2026-06 한국원전수출산업협회가 미국 동향 콘텐츠를 회원 전용으로 전환 →
기존 e-kna.org(fetch_kna_news.py)는 미국 글 본문이 안내문으로 대체됨.
회원 게시판 k-neiss.org 로 소스를 전환해 미국 본문까지 수집한다.

실제 수집 로직은 execution/fetch_kneiss_news.py.
state 파일은 호환을 위해 DASHBOARD_DIR/kna_state.json 유지
(키는 last_seen_kneiss_idx, 기존 last_seen_num 은 보존만 됨).
"""
from __future__ import annotations

import html as _html
import os
import sys

# execution/ 부모 경로 (fetch_kneiss_news.py 임포트 위해)
_EXECUTION_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _EXECUTION_DIR not in sys.path:
    sys.path.insert(0, _EXECUTION_DIR)

import fetch_kneiss_news as _k  # noqa: E402

LABEL = 'KNA 세계원전시장동향'
ICON = '📰'


def fetch_new_posts(update_state: bool = False) -> list[dict]:
    posts = _k.fetch_new_posts(update_state=update_state)
    out = []
    for p in posts:
        out.append({
            'id': p['idx'],
            'display_no': p.get('display_no', ''),
            'category': p.get('category', ''),
            'title': p['title'],
            'date': p['date'],
            'url': _k._board_link(),
            'body': p.get('body', ''),
            'paywalled': bool(p.get('paywalled')),
        })
    return out


def latest_item_date() -> str | None:
    """게시판 최신 글 작성일(YYYY-MM-DD). staleness 감지용. 실패 시 None.

    목록 첫 페이지(최신순)에서 날짜가 있는 첫 행을 반환.
    """
    try:
        import requests
        r = requests.get(_k._list_url(1), headers=_k.UA, timeout=_k.REQ_TIMEOUT)
        posts = _k.parse_board_list(r.text)
    except Exception:
        return None
    for p in posts:
        d = (p.get('date') or '').strip()
        if d:
            return d
    return None


def commit_state(posts: list[dict]) -> None:
    if not posts:
        return
    max_idx = max(p['id'] for p in posts)
    _k.save_last_seen(max_idx)


def format_message(post: dict, label: str, icon: str) -> str:
    """KNA 룩 유지: 헤더 + □ 시작 줄 굵게 강조. 회원전용 차단 시 안내."""
    meta = f"{post['date']} · #{post.get('display_no', '')}"
    cat = post.get('category', '')
    if cat:
        meta += f" · {_html.escape(cat)}"
    header = (
        f"{icon} <b>[{label}] {_html.escape(post['title'])}</b>\n"
        f"{meta}\n"
        f"{post['url']}\n\n"
    )
    if post.get('paywalled') and not post.get('body'):
        return header + '🔒 회원 전용 콘텐츠 — 본문을 가져오지 못했습니다 (로그인/열람권한 확인 필요).'
    body_lines = []
    for ln in post.get('body', '').split('\n'):
        escaped = _html.escape(ln)
        if ln.lstrip().startswith('□'):
            body_lines.append(f'<b><u>{escaped}</u></b>')
        else:
            body_lines.append(escaped)
    return header + '\n'.join(body_lines)
