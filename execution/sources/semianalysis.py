"""SemiAnalysis 어댑터.

수집: Substack RSS (newsletter.semianalysis.com/feed), content:encoded 에 풀 HTML 본문.
  ※ 2026-05 기준 semianalysis.com/feed/ (구 WordPress 피드)는 2025-09 이후 갱신 중단됨.
    실제 신규 글은 Substack 뉴스레터로만 발행되어 그쪽 피드로 전환.
번역: _translator.translate_to_korean (Haiku 4.5).

state: sources_state/semianalysis.json — last_seen_guids (최근 200개 GUID).
paywall 감지: 본문 끝 '[…]' (구 피드) + Substack 유료글 truncation 문구.
"""
from __future__ import annotations

import html as _html
import logging
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any

from . import STATE_DIR
from .base import load_state, save_state, state_path

logger = logging.getLogger(__name__)

LABEL = 'SemiAnalysis'
ICON = '📊'
FEED_URL = 'https://newsletter.semianalysis.com/feed'
STATE_NAME = 'semianalysis'
MAX_REMEMBERED_GUIDS = 200

UA = 'Mozilla/5.0 (compatible; RA_Sisyphe_bot/1.0; +https://github.com/sisyphe10)'

NS = {
    'content': 'http://purl.org/rss/1.0/modules/content/',
    'dc': 'http://purl.org/dc/elements/1.1/',
}


# ── HTML → 텍스트 추출 ──────────────────────────────────────────────────
class _ContentExtractor(HTMLParser):
    """RSS content:encoded HTML → 텍스트.

    - <p>, <h1~6>, <li>, <br>, <figure>, <blockquote> 줄바꿈
    - <a> 텍스트만 유지 (URL 제거)
    - <figcaption> 은 '[그림: ...]' 형식으로 마킹
    - <script>, <style>, <iframe> 무시
    """

    SKIP_TAGS = {'script', 'style', 'iframe', 'svg', 'noscript'}
    BLOCK_TAGS = {'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                  'li', 'tr', 'blockquote', 'pre'}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0
        self.in_figcaption = False
        self.in_heading = False
        self.heading_level = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == 'br':
            self.parts.append('\n')
        elif tag in self.BLOCK_TAGS:
            self.parts.append('\n')
            if tag in ('h1', 'h2', 'h3'):
                self.in_heading = True
                self.heading_level = int(tag[1])
                self.parts.append('## ')
            elif tag in ('h4', 'h5', 'h6'):
                self.in_heading = True
                self.heading_level = int(tag[1])
                self.parts.append('### ')
            elif tag == 'li':
                self.parts.append('• ')
        elif tag == 'figure':
            self.parts.append('\n')
        elif tag == 'figcaption':
            self.in_figcaption = True
            self.parts.append('[그림: ')
        elif tag == 'img':
            attrs_d = dict(attrs)
            alt = attrs_d.get('alt', '').strip()
            if alt:
                self.parts.append(f'[이미지: {alt}]')
            else:
                self.parts.append('[이미지]')

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag in self.BLOCK_TAGS:
            self.parts.append('\n')
            if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
                self.in_heading = False
        elif tag == 'figcaption':
            self.parts.append(']')
            self.in_figcaption = False
        elif tag == 'figure':
            self.parts.append('\n')

    def handle_data(self, data):
        if self.skip_depth:
            return
        self.parts.append(data)

    def get_text(self) -> str:
        text = ''.join(self.parts)
        text = _html.unescape(text)
        text = text.replace('\xa0', ' ')
        # 공백 정리
        text = re.sub(r'[ \t]+', ' ', text)
        # 3개 이상 줄바꿈 → 2개
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 각 줄 trim
        lines = [ln.strip() for ln in text.split('\n')]
        # 연속 빈 줄 1개로
        out: list[str] = []
        prev_blank = False
        for ln in lines:
            if not ln:
                if prev_blank:
                    continue
                prev_blank = True
                out.append('')
            else:
                prev_blank = False
                out.append(ln)
        return '\n'.join(out).strip()


_FOOTER_PATTERNS = [
    re.compile(r'^\s*By signing up.*Privacy Policy.*$', re.IGNORECASE),
    re.compile(r'^\s*Privacy Policy\s+and\s+Terms.*$', re.IGNORECASE),
    re.compile(r'^\s*Subscribe (now |today |to ).*$', re.IGNORECASE),
    # Substack 푸터/CTA
    re.compile(r'^\s*Thanks for reading.*$', re.IGNORECASE),
    re.compile(r'^\s*Leave a comment\s*$', re.IGNORECASE),
    re.compile(r'^\s*Share\s*$', re.IGNORECASE),
    re.compile(r'^\s*(Give a gift subscription|Get \d+% off).*$', re.IGNORECASE),
]

# 텔레그램은 이미지 없이 텍스트만이라 figcaption placeholder는 노이즈. 본문 추출 단계에서 제거.
_FIGCAPTION_PATTERN = re.compile(r'\[그림:[^\]]*\]')


def _strip_figcaptions(text: str) -> str:
    text = _FIGCAPTION_PATTERN.sub('', text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _strip_footer(text: str) -> str:
    """본문 끝의 SemiAnalysis footer (Privacy/Terms/Subscribe CTA) 제거."""
    lines = text.split('\n')
    # 뒤에서부터 footer 패턴 매칭되는 줄을 모두 제거
    while lines:
        ln = lines[-1].strip()
        if not ln:
            lines.pop()
            continue
        matched = any(p.match(ln) for p in _FOOTER_PATTERNS)
        if matched:
            lines.pop()
            continue
        break
    return '\n'.join(lines).rstrip()


_SUBSTACK_PAYWALL_MARKERS = (
    'subscribe to read',
    'this post is for paid subscribers',
    'this post is for paying subscribers',
    'keep reading with a 7-day free trial',
)


def _is_paywalled(text: str) -> bool:
    """본문이 잘린 유료글인지.

    - 구 WordPress 피드: 본문 끝 '[…]' / '[...]' 마커
    - Substack 피드: 본문 끝부분에 'Subscribe to read' 등 유료 전환 문구
    """
    tail = text[-400:].strip()
    if tail.endswith('[…]') or tail.endswith('[...]'):
        return True
    tail_low = tail.lower()
    return any(m in tail_low for m in _SUBSTACK_PAYWALL_MARKERS)


# ── RSS fetch ─────────────────────────────────────────────────────────
def _fetch_feed() -> str:
    req = urllib.request.Request(FEED_URL, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode('utf-8', errors='replace')


def _parse_feed(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    posts: list[dict[str, Any]] = []
    for item in root.findall('.//item'):
        guid_el = item.find('guid')
        guid = (guid_el.text or '').strip() if guid_el is not None else ''
        title = (item.findtext('title') or '').strip()
        link = (item.findtext('link') or '').strip()
        pub_date = (item.findtext('pubDate') or '').strip()
        author = (item.findtext('dc:creator', namespaces=NS) or '').strip()
        content_encoded = item.findtext('content:encoded', namespaces=NS) or ''
        description = item.findtext('description') or ''
        posts.append({
            'id': guid or link,
            'guid': guid,
            'title': title,
            'date': pub_date,
            'url': link,
            'author': author,
            'content_html': content_encoded or description,
            'has_content_encoded': bool(content_encoded),
        })
    return posts


# ── 공개 API ───────────────────────────────────────────────────────────
def fetch_new_posts(update_state: bool = False) -> list[dict[str, Any]]:
    """RSS 에서 신규 글 수집 + 본문 텍스트화 + 번역.

    최초 실행 (state 없음) 시: 현재 RSS 의 모든 GUID 를 last_seen 에 적재만 하고
    알림 없이 빈 리스트 반환 (KNA 와 동일 정책).
    """
    state_existed = os.path.exists(state_path(STATE_NAME))
    state = load_state(STATE_NAME)
    seen_guids: set[str] = set(state.get('last_seen_guids') or [])

    xml_text = _fetch_feed()
    feed_posts = _parse_feed(xml_text)
    if not feed_posts:
        raise RuntimeError('SemiAnalysis RSS 파싱 0건 (구조 변경 가능성)')

    # 최초 실행: 알림 없이 현재 상태만 저장
    if not state_existed:
        current_guids = [p['id'] for p in feed_posts if p['id']]
        if update_state:
            save_state(STATE_NAME, {'last_seen_guids': current_guids[:MAX_REMEMBERED_GUIDS]})
        logger.info(f'SemiAnalysis 최초 실행 — last_seen_guids 초기화 ({len(current_guids)}개)')
        return []

    # 신규 글만 (오래된 순)
    new_posts = [p for p in feed_posts if p['id'] and p['id'] not in seen_guids]
    new_posts.reverse()  # RSS는 최신순 → 오래된 순으로 발송

    # 본문 텍스트화 + paywall 감지 + 번역
    from ._translator import translate_to_korean

    enriched: list[dict[str, Any]] = []
    for p in new_posts:
        try:
            parser = _ContentExtractor()
            parser.feed(p['content_html'])
            body_en = _strip_figcaptions(_strip_footer(parser.get_text()))
            paywalled = _is_paywalled(body_en)

            # 번역
            tr = translate_to_korean(body_en, title=p['title'])
            body_kr = tr['text']

            enriched.append({
                'id': p['id'],
                'title': p['title'],
                'date': _format_date(p['date']),
                'url': p['url'],
                'author': p['author'],
                'body_en': body_en,
                'body_kr': body_kr,
                'paywalled': paywalled,
                'translate_chunks': tr.get('chunks', 0),
                'translate_input_tokens': tr.get('input_tokens', 0),
                'translate_output_tokens': tr.get('output_tokens', 0),
            })
            logger.info(
                f'SemiAnalysis post 처리 완료: "{p["title"][:60]}" — '
                f'chunks={tr.get("chunks")} in={tr.get("input_tokens")} out={tr.get("output_tokens")}'
            )
        except Exception as e:
            logger.error(f'SemiAnalysis post 처리 실패: {p["title"][:60]} — {e}')
            enriched.append({
                'id': p['id'],
                'title': p['title'],
                'date': _format_date(p['date']),
                'url': p['url'],
                'author': p['author'],
                'body_en': '',
                'body_kr': f'(번역/추출 실패: {e})',
                'paywalled': False,
                'error': str(e),
            })

    if update_state and enriched:
        new_seen = list(seen_guids) + [p['id'] for p in enriched]
        save_state(STATE_NAME, {'last_seen_guids': new_seen[-MAX_REMEMBERED_GUIDS:]})

    return enriched


def latest_item_date() -> str | None:
    """피드 최신 item 의 날짜(YYYY-MM-DD). staleness 감지용 (state 미변경).

    피드는 최신순이므로 ISO 날짜로 변환되는 첫 item 을 반환. 실패 시 None.
    """
    try:
        posts = _parse_feed(_fetch_feed())
    except Exception as e:
        logger.warning(f'SemiAnalysis latest_item_date 실패: {e}')
        return None
    for p in posts:
        d = _format_date(p.get('date', ''))
        if len(d) == 10 and d[4] == '-':
            return d
    return None


def commit_state(posts: list[dict[str, Any]]) -> None:
    """발송 성공 후 state 갱신 — 신규 GUID 들을 last_seen 에 추가."""
    if not posts:
        return
    state = load_state(STATE_NAME)
    seen = list(state.get('last_seen_guids') or [])
    for p in posts:
        if p.get('id') and p['id'] not in seen:
            seen.append(p['id'])
    save_state(STATE_NAME, {'last_seen_guids': seen[-MAX_REMEMBERED_GUIDS:]})


def format_message(post: dict[str, Any], label: str, icon: str) -> str:
    """텔레그램 HTML 메시지 1건."""
    title_esc = _html.escape(post['title'])
    paywall_badge = ' 🔒' if post.get('paywalled') else ''
    author_line = ''
    if post.get('author'):
        author_line = f"by {_html.escape(post['author'])}\n"
    header = (
        f"{icon} <b>[{label}] {title_esc}</b>{paywall_badge}\n"
        f"{post['date']}\n"
        f"{author_line}"
        f"{post['url']}\n\n"
    )
    body = post.get('body_kr', '') or ''
    return header + body


def _format_date(rfc822: str) -> str:
    """RFC 822 'Tue, 16 Sep 2025 17:38:01 +0000' → 'YYYY-MM-DD'."""
    if not rfc822:
        return ''
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(rfc822)
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return rfc822[:16]


# ── CLI dry-run ────────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys as _sys
    import argparse

    parser = argparse.ArgumentParser(description='SemiAnalysis 어댑터 dry-run')
    parser.add_argument('--limit', type=int, default=1, help='최신 N건만 추출/번역')
    parser.add_argument('--no-translate', action='store_true', help='번역 스킵 (영문만)')
    parser.add_argument('--preview-chars', type=int, default=600, help='출력 미리보기 길이')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    xml_text = _fetch_feed()
    feed_posts = _parse_feed(xml_text)
    print(f'\n[RSS] {len(feed_posts)} items\n')

    for p in feed_posts[:args.limit]:
        parser_html = _ContentExtractor()
        parser_html.feed(p['content_html'])
        body_en = _strip_figcaptions(_strip_footer(parser_html.get_text()))
        paywalled = _is_paywalled(body_en)

        print('=' * 80)
        print(f'TITLE : {p["title"]}')
        print(f'DATE  : {_format_date(p["date"])}')
        print(f'URL   : {p["url"]}')
        print(f'AUTHOR: {p["author"]}')
        print(f'BODY  : {len(body_en)} chars · paywalled={paywalled}')
        print('-' * 80)
        print('[ENGLISH PREVIEW]')
        print(body_en[:args.preview_chars] + ('...' if len(body_en) > args.preview_chars else ''))

        if not args.no_translate:
            print('-' * 80)
            print('[TRANSLATING (Haiku 4.5)...]')
            from ._translator import translate_to_korean
            tr = translate_to_korean(body_en, title=p['title'])
            print(f"chunks={tr['chunks']} in_tokens={tr['input_tokens']} out_tokens={tr['output_tokens']}")
            print('-' * 80)
            print('[KOREAN PREVIEW]')
            kr = tr['text']
            print(kr[:args.preview_chars] + ('...' if len(kr) > args.preview_chars else ''))
            print('-' * 80)
            print(f'[KOREAN FULL LENGTH] {len(kr)} chars')
        print('=' * 80)
        print()
