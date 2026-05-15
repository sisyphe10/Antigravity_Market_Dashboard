"""Source 어댑터 공통 헬퍼.

각 어댑터(<name>.py)는 다음 인터페이스를 구현:

    LABEL: str   # 텔레그램 헤더 표시명 (sources.json의 label이 우선)
    ICON: str    # 이모지

    def fetch_new_posts(update_state: bool = False) -> list[dict]:
        '''신규 게시글 반환. 각 dict 필수 키: id, title, date, url, body
           선택 키: display_no, paywalled (bool), body_html (텔레그램 직접 사용 시)'''

    def commit_state(posts: list[dict]) -> None:
        '''발송 성공 후 state 갱신 (last_seen).'''

    def format_message(post: dict, label: str, icon: str) -> str:
        '''텔레그램 HTML 메시지 1건 (4000자 초과 시 봇이 분할).'''
"""
from __future__ import annotations

import json
import os
from typing import Any

from . import STATE_DIR, ensure_state_dir


def state_path(name: str) -> str:
    """기본 state 경로. (KNA처럼 호환을 위해 커스텀 경로 쓸 거면 어댑터에서 override)"""
    ensure_state_dir()
    return os.path.join(STATE_DIR, f'{name}.json')


def load_state(name: str) -> dict[str, Any]:
    p = state_path(name)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(name: str, state: dict[str, Any]) -> None:
    p = state_path(name)
    ensure_state_dir()
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def split_for_telegram(text: str, max_chars: int = 4000) -> list[str]:
    """텔레그램 메시지 분할. 문단 경계(빈 줄) 1순위 → 줄 경계 2순위 → 강제 분할."""
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        idx = remaining.rfind('\n\n', 0, max_chars)
        if idx <= 0:
            idx = remaining.rfind('\n', 0, max_chars)
        if idx <= 0:
            idx = max_chars
        chunks.append(remaining[:idx].rstrip())
        remaining = remaining[idx:].lstrip('\n')
    if remaining:
        chunks.append(remaining)
    return chunks
