"""TrendForce 뉴스 어댑터 (반도체·메모리·디스플레이 등 테크 뉴스).

수집: WordPress REST API
  GET https://www.trendforce.com/news/wp-json/wp/v2/posts?per_page=N&_embed=wp:term
  (RSS /news/feed/ 는 2026-04 이후 캐시 동결돼 못 씀. wp-json 은 현행+JSON.)
번역: _translator.summarize_news_to_korean (Haiku 4.5) — 글별 한글 제목 + 불릿 요약.

발송: 하루 1회 다이제스트 — 그날 신규 글 전체를 단일 합성 post 1건으로 묶어
  파이프라인이 1메시지(필요시 자동분할)로 발송. (개별 N메시지 아님)

state: sources_state/trendforce.json — last_seen_post_id (정수, post id 기준).
  최초 실행 시 baseline self-init (과거글 스팸 방지), update_state 무관하게 저장.
"""
from __future__ import annotations

import html as _html
import logging
import os
import re
import urllib.request
import json as _json
from typing import Any

from . import STATE_DIR, ensure_state_dir
from .base import load_state, save_state, state_path

logger = logging.getLogger(__name__)

LABEL = 'TrendForce'
ICON = '🟢'
STATE_NAME = 'trendforce'
STATE_KEY = 'last_seen_post_id'

API_URL = ('https://www.trendforce.com/news/wp-json/wp/v2/posts'
           '?per_page=50&_embed=wp:term&_fields=id,date,link,title,content,excerpt,_links,_embedded')
NEWS_PAGE = 'https://www.trendforce.com/news/'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36'

REQ_TIMEOUT = 30
MAX_TERMS = 5


# ── HTML → 평문 ──────────────────────────────────────────────────────────
_BLOCK_CLOSE = re.compile(r'</(?:p|li|h[1-6]|div|tr|blockquote)>', re.I)
_BR = re.compile(r'<br\s*/?>', re.I)
_TAG = re.compile(r'<[^>]+>')


def _html_to_text(s: str) -> str:
    if not s:
        return ''
    s = _BR.sub('\n', s)
    s = _BLOCK_CLOSE.sub('\n', s)
    s = _TAG.sub('', s)
    s = _html.unescape(s).replace('\xa0', ' ')
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return '\n'.join(ln.strip() for ln in s.split('\n')).strip()


def _clean_title(t: str) -> str:
    """'[News] ...' / '[Insights] ...' 접두 유지하되 HTML 엔티티만 정리."""
    return _html.unescape(_TAG.sub('', t or '')).strip()


# ── API fetch ─────────────────────────────────────────────────────────
def _fetch_posts() -> list[dict[str, Any]]:
    req = urllib.request.Request(API_URL, headers={'User-Agent': UA,
                                                   'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=REQ_TIMEOUT) as resp:
        data = resp.read().decode('utf-8', errors='replace')
    posts = _json.loads(data)
    if not isinstance(posts, list):
        raise RuntimeError('TrendForce wp-json 응답이 배열이 아님 (구조 변경 가능성)')
    return posts


def _term_names(post: dict) -> list[str]:
    """_embedded.wp:term 에서 카테고리/태그 이름 추출 (중복 제거, 최대 MAX_TERMS)."""
    out: list[str] = []
    emb = (post.get('_embedded') or {}).get('wp:term') or []
    for grp in emb:
        for t in grp:
            name = _html.unescape((t.get('name') or '').strip())
            if name and name not in out:
                out.append(name)
    return out[:MAX_TERMS]


def _post_date(post: dict) -> str:
    """post date(ISO) → 'YYYY-MM-DD'."""
    d = (post.get('date') or '')[:10]
    return d if re.match(r'\d{4}-\d{2}-\d{2}', d) else ''


# ── state ───────────────────────────────────────────────────────────────
def _save_last_seen(post_id: int) -> None:
    st = load_state(STATE_NAME)
    st[STATE_KEY] = int(post_id)
    save_state(STATE_NAME, st)


# ── 공개 API ───────────────────────────────────────────────────────────
def fetch_new_posts(update_state: bool = False) -> list[dict[str, Any]]:
    """신규 글 수집 → 글별 한글 요약 → 단일 다이제스트 합성 post 1건 반환.

    최초 실행(STATE_KEY 없음): baseline 만 잡고 빈 리스트 반환(알림 없음).
    파이프라인이 update_state=False 로 호출하므로 baseline 은 무관하게 저장(self-init).
    """
    state = load_state(STATE_NAME)
    initialized = STATE_KEY in state
    last_seen = int(state.get(STATE_KEY) or 0)

    posts = _fetch_posts()
    if not posts:
        raise RuntimeError('TrendForce wp-json 0건 (API 차단/구조 변경 가능성)')

    new_posts = [p for p in posts if int(p.get('id', 0)) > last_seen]
    new_posts.sort(key=lambda p: int(p.get('id', 0)))  # 오래된 순

    # 최초 실행: baseline 설정만
    if not initialized:
        _save_last_seen(max(int(p.get('id', 0)) for p in posts))
        logger.info('TrendForce 최초 실행 — baseline 초기화')
        return []

    if not new_posts:
        return []

    if len(new_posts) > 30:
        logger.warning(f'TrendForce 신규 {len(new_posts)}건 — 다이제스트가 길 수 있음')

    from ._translator import summarize_news_to_korean

    blocks: list[str] = []
    tok_in = tok_out = 0
    for i, p in enumerate(new_posts, 1):
        title_en = _clean_title((p.get('title') or {}).get('rendered', ''))
        body_en = _html_to_text((p.get('content') or {}).get('rendered', '')) \
            or _html_to_text((p.get('excerpt') or {}).get('rendered', ''))
        link = (p.get('link') or '').strip()
        terms = _term_names(p)
        try:
            s = summarize_news_to_korean(title_en, body_en)
            title_kr = s['title_kr']
            summary = s['summary_kr']
            tok_in += s.get('input_tokens', 0)
            tok_out += s.get('output_tokens', 0)
        except Exception as e:
            logger.error(f'TrendForce 요약 실패 (id={p.get("id")}): {e}')
            title_kr = title_en  # 폴백: 영문 제목 + 발췌
            summary = '- ' + _html_to_text((p.get('excerpt') or {}).get('rendered', ''))[:300]

        tag_line = ('🏷 ' + ' · '.join(terms) + '\n') if terms else ''
        blocks.append(
            f"<b>{i}. {_html.escape(title_kr)}</b>\n"
            f"{summary}\n"
            f"{tag_line}"
            f"🔗 {link}"
        )

    digest_body = '\n\n'.join(blocks)
    max_id = max(int(p.get('id', 0)) for p in new_posts)
    latest_date = _post_date(new_posts[-1]) or _post_date(posts[0])

    synthetic = {
        'id': max_id,
        'title': f'{latest_date} 다이제스트 ({len(new_posts)}건)',
        'date': latest_date,
        'url': NEWS_PAGE,
        'body': digest_body,
        'count': len(new_posts),
    }
    logger.info(
        f'TrendForce 다이제스트 {len(new_posts)}건 — in={tok_in} out={tok_out}'
    )

    if update_state:
        _save_last_seen(max_id)

    return [synthetic]


def latest_item_date() -> str | None:
    """최신 글 작성일(YYYY-MM-DD). staleness 감지용 (state 미변경)."""
    try:
        posts = _fetch_posts()
    except Exception as e:
        logger.warning(f'TrendForce latest_item_date 실패: {e}')
        return None
    for p in posts:
        d = _post_date(p)
        if d:
            return d
    return None


def commit_state(posts: list[dict[str, Any]]) -> None:
    """발송 성공 후 state 갱신 — 다이제스트의 max post id 저장."""
    if not posts:
        return
    max_id = max(int(p.get('id', 0)) for p in posts)
    _save_last_seen(max_id)


def format_message(post: dict[str, Any], label: str, icon: str) -> str:
    """다이제스트 메시지 1건. 헤더 + 합성된 본문(이미 글별 블록 포함)."""
    header = (
        f"{icon} <b>[{label}] {post.get('date', '')} 다이제스트 "
        f"({post.get('count', 0)}건)</b>\n"
        f"{post.get('url', NEWS_PAGE)}\n\n"
    )
    return (header + (post.get('body') or '')).rstrip()


# ── CLI dry-run ────────────────────────────────────────────────────────
if __name__ == '__main__':
    import argparse
    import sys as _sys

    _EXEC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _EXEC not in _sys.path:
        _sys.path.insert(0, _EXEC)
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(_EXEC), '.env'))

    ap = argparse.ArgumentParser(description='TrendForce 어댑터 dry-run')
    ap.add_argument('--since', type=int, default=None,
                    help='이 post id 초과만 신규 취급 (미지정 시 state 무시하고 최근 N건)')
    ap.add_argument('--limit', type=int, default=3, help='--since 없을 때 최근 N건 요약')
    args = ap.parse_args()

    raw = _fetch_posts()
    print(f'[API] {len(raw)} posts, 최신 id={raw[0].get("id")} date={_post_date(raw[0])}')
    from ._translator import summarize_news_to_korean
    sample = ([p for p in raw if int(p.get('id', 0)) > args.since]
              if args.since is not None else raw[:args.limit])
    sample.sort(key=lambda p: int(p.get('id', 0)))
    for p in sample:
        title_en = _clean_title((p.get('title') or {}).get('rendered', ''))
        body_en = _html_to_text((p.get('content') or {}).get('rendered', ''))
        s = summarize_news_to_korean(title_en, body_en)
        print('=' * 70)
        print('EN :', title_en[:70])
        print('KR :', s['title_kr'])
        print('태그:', ' · '.join(_term_names(p)))
        print(s['summary_kr'])
