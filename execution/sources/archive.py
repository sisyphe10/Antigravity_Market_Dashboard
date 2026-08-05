"""수집 소스 게시글 → datalake/news md 아카이브 (append-only·멱등).

ra_sisyphe_bot 소스 파이프라인이 fetch 직후 호출한다. 텔레그램 발송과 무관하게
글 1건 = md 1개로 영속해 위키 검색·운용보고서의 DB가 되게 한다.
발송을 절대 깨지 않도록 모든 예외를 삼키고 로그만 남긴다.

경로: ~/datalake/news/<source>/<연도>/<YYYYMMDD>_<id>.md (id 기준 멱등 skip)
frontmatter: source/label/id/title/category/date/url/archived_at
"""
from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import re

NEWS_ROOT = os.path.expanduser('~/datalake/news')


def _safe_id(post_id) -> str:
    s = str(post_id)
    if re.fullmatch(r'[A-Za-z0-9._-]{1,40}', s):
        return s
    return hashlib.md5(s.encode('utf-8')).hexdigest()[:12]


def _safe_date(d) -> str:
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', str(d or ''))
    if m:
        return f'{m.group(1)}{m.group(2)}{m.group(3)}'
    return datetime.date.today().strftime('%Y%m%d')


def archive_post(source: str, post: dict, label: str = '') -> str | None:
    """글 1건 저장. 저장한 경로 반환, 기존 존재/실패 시 None."""
    try:
        date8 = _safe_date(post.get('date'))
        d = os.path.join(NEWS_ROOT, source, date8[:4])
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{date8}_{_safe_id(post.get('id', ''))}.md")
        if os.path.exists(path):
            return None
        title = str(post.get('title') or '').strip()
        fm = {
            'source': source,
            'label': label,
            'id': str(post.get('id', '')),
            'title': title,
            'category': str(post.get('category') or ''),
            'date': str(post.get('date') or ''),
            'url': str(post.get('url') or ''),
            'archived_at': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
        }
        head = '\n'.join(f'{k}: {json.dumps(v, ensure_ascii=False)}'
                         for k, v in fm.items() if v)
        body = str(post.get('body') or '').strip()
        text = f'---\n{head}\n---\n\n# {title}\n\n{body}\n'
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(text)
        os.replace(tmp, path)
        return path
    except Exception as e:
        logging.warning(f"news archive 실패 ({source} id={post.get('id')}): {e}")
        return None


def archive_posts(source: str, posts, label: str = '') -> int:
    """posts 일괄 저장 → 신규 저장 건수."""
    n = 0
    for p in posts or []:
        if archive_post(source, p, label):
            n += 1
    return n
