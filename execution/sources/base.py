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
import re
from typing import Any

from . import STATE_DIR, ensure_state_dir


_HEADER_LINE = re.compile(
    r'^\s*(?:'
    r'<b><u>[^<]+</u></b>'      # SemiAnalysis HTML 섹션 헤더
    r'|#{1,6}\s+\S.*'            # 마크다운 헤더
    r')\s*$',
)


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


def _ends_with_orphan_header(chunk: str) -> bool:
    """chunk 끝의 마지막 비공백 줄이 섹션 헤더면 True (헤더만 매달림)."""
    stripped = chunk.rstrip()
    if not stripped:
        return False
    last_line = stripped.rsplit('\n', 1)[-1]
    return bool(_HEADER_LINE.match(last_line))


def split_for_telegram(text: str, max_chars: int = 4000) -> list[str]:
    """텔레그램 메시지 분할.

    - 1순위: 문단 경계(빈 줄)
    - 2순위: 줄 경계
    - 3순위: 강제 분할
    - 추가: 청크 끝이 섹션 헤더로 끝나면 헤더를 다음 청크로 내림 (제목-본문 분리 방지)
    """
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

        # 헤더 고아 방지: 청크 끝이 헤더 한 줄이면 그 헤더 앞으로 경계 후퇴
        candidate = remaining[:idx]
        if _ends_with_orphan_header(candidate):
            stripped = candidate.rstrip()
            header_start = stripped.rfind('\n') + 1 if '\n' in stripped else 0
            new_idx = remaining.rfind('\n\n', 0, header_start)
            if new_idx <= 0:
                new_idx = remaining.rfind('\n', 0, header_start)
            if new_idx > 0:
                idx = new_idx

        chunks.append(remaining[:idx].rstrip())
        remaining = remaining[idx:].lstrip('\n')
    if remaining:
        chunks.append(remaining)
    return chunks
