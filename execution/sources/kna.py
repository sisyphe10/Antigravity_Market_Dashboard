"""KNA 세계원전시장동향 어댑터.

기존 execution/fetch_kna_news.py 를 그대로 호출하는 얇은 wrapper.
state 파일은 호환을 위해 DASHBOARD_DIR/kna_state.json 유지 (sources_state/ 아님).
"""
from __future__ import annotations

import html as _html
import os
import sys

# execution/ 부모 경로 (fetch_kna_news.py 임포트 위해)
_EXECUTION_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _EXECUTION_DIR not in sys.path:
    sys.path.insert(0, _EXECUTION_DIR)

from fetch_kna_news import fetch_new_posts as _fetch_new_posts  # noqa: E402
from fetch_kna_news import _save_state as _kna_save_state  # noqa: E402

LABEL = 'KNA 세계원전시장동향'
ICON = '📰'


def fetch_new_posts(update_state: bool = False) -> list[dict]:
    posts = _fetch_new_posts(update_state=update_state)
    out = []
    for p in posts:
        out.append({
            'id': p['num'],
            'display_no': p.get('display_no', ''),
            'title': p['title'],
            'date': p['date'],
            'url': p['url'],
            'body': p.get('body', ''),
            'paywalled': False,
        })
    return out


def latest_item_date() -> str | None:
    """게시판 최신 글 작성일(YYYY-MM-DD 또는 YYYY.MM.DD). staleness 감지용. 실패 시 None.

    목록 첫 페이지(start=0)는 최신순이므로 날짜가 있는 첫 행을 반환.
    """
    try:
        from fetch_kna_news import (  # noqa: E402
            _board_url, _fetch_html, parse_board_list,
        )
        posts = parse_board_list(_fetch_html(_board_url(0)))
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
    max_num = max(p['id'] for p in posts)
    _kna_save_state({'last_seen_num': max_num})


def format_message(post: dict, label: str, icon: str) -> str:
    """KNA 룩 유지: 헤더 + □ 시작 줄 굵게 강조."""
    header = (
        f"{icon} <b>[{label}] {_html.escape(post['title'])}</b>\n"
        f"{post['date']} · #{post.get('display_no', '')}\n"
        f"{post['url']}\n\n"
    )
    body_lines = []
    for ln in post.get('body', '').split('\n'):
        escaped = _html.escape(ln)
        if ln.lstrip().startswith('□'):
            body_lines.append(f'<b><u>{escaped}</u></b>')
        else:
            body_lines.append(escaped)
    return header + '\n'.join(body_lines)
