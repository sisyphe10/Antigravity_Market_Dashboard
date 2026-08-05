"""뉴스 소스 → datalake/news md 백필 (일회성·멱등, 존재 파일 skip으로 재개 가능).

kna         : k-neiss 목록 전체 순회 (로그인 시 미국 본문 포함), 글별 md
trendforce  : wp-json 페이지네이션 소급 (영문 원문)
semianalysis: 현재 RSS 피드 항목 (피드 특성상 최근분만)
foreign_ir  : 현재 IR 피드 항목 (제목·링크만 — 본문 미제공)

사용: venv/bin/python3 datalake/backfill_news.py --source kna [--max-pages N]
"""
import argparse
import os
import sys
import time

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, 'execution'))

from sources.archive import NEWS_ROOT, _safe_date, _safe_id, archive_post  # noqa: E402


def _exists(source, post):
    d8 = _safe_date(post.get('date'))
    return os.path.exists(os.path.join(
        NEWS_ROOT, source, d8[:4], f"{d8}_{_safe_id(post.get('id', ''))}.md"))


def backfill_kna(max_pages=None):
    import fetch_kneiss_news as k
    s = k._make_session()
    login_ok = False
    try:
        k._login(s)
        login_ok = True
    except Exception as e:
        print(f'[kna] 로그인 실패 — 미국 글은 건너뜀: {e}', flush=True)
    page, saved, skipped, paywalled = 1, 0, 0, 0
    while True:
        if max_pages and page > max_pages:
            break
        try:
            r = s.get(k._list_url(page), timeout=25)
        except Exception as e:
            print(f'[kna] page {page} 목록 실패: {e} — 10초 후 재시도', flush=True)
            time.sleep(10)
            continue
        rows = k.parse_board_list(r.text)
        if not rows:
            break
        for row in rows:
            post = dict(row)
            post['id'] = row['idx']
            post['url'] = k._post_link(row['idx'])
            if _exists('kna', post):
                skipped += 1
                continue
            if (not login_ok) and row.get('category') == '미국원전시장동향':
                paywalled += 1
                continue
            try:
                title, date_str, body, pw = k.fetch_post_detail(s, row['idx'])
            except Exception as e:
                print(f"[kna] idx={row['idx']} 본문 실패: {e}", flush=True)
                continue
            if pw:
                paywalled += 1
                continue
            if title:
                post['title'] = title
            if date_str:
                post['date'] = date_str
            post['body'] = body
            if archive_post('kna', post, 'KNA 세계원전시장동향'):
                saved += 1
            time.sleep(0.3)
        if page % 20 == 0:
            print(f'[kna] page {page}: 저장 {saved} / 기존 {skipped} / 차단 {paywalled}',
                  flush=True)
        if login_ok and page % 30 == 0:
            # 장시간 세션 만료 대비 주기 재로그인 (실패해도 계속)
            try:
                k._login(s)
            except Exception as e:
                print(f'[kna] 재로그인 실패(계속 진행): {e}', flush=True)
        page += 1
    print(f'[kna] 완료: 저장 {saved} / 기존 {skipped} / 차단 {paywalled}', flush=True)


def backfill_trendforce(max_pages=None):
    import json as _json
    import urllib.error
    import urllib.request

    from sources import trendforce as tf
    page, saved, skipped = 1, 0, 0
    while True:
        if max_pages and page > max_pages:
            break
        url = tf.API_URL + f'&page={page}'
        req = urllib.request.Request(url, headers={'User-Agent': tf.UA,
                                                   'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = _json.loads(resp.read().decode('utf-8', errors='replace'))
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                break  # wp-json 마지막 페이지 초과
            raise
        if not isinstance(data, list) or not data:
            break
        for p in data:
            post = {
                'id': p.get('id'),
                'title': tf._clean_title(((p.get('title') or {}).get('rendered')) or ''),
                'date': tf._post_date(p),
                'url': p.get('link') or '',
                'category': ', '.join(tf._term_names(p)),
                'body': tf._html_to_text(((p.get('content') or {}).get('rendered')) or ''),
            }
            if _exists('trendforce', post):
                skipped += 1
                continue
            if archive_post('trendforce', post, 'TrendForce'):
                saved += 1
        print(f'[trendforce] page {page}: 저장 {saved} / 기존 {skipped}', flush=True)
        page += 1
        time.sleep(0.5)
    print(f'[trendforce] 완료: 저장 {saved} / 기존 {skipped}', flush=True)


def backfill_semianalysis():
    import email.utils

    from sources import semianalysis as sa
    from sources import trendforce as tf
    posts = sa._parse_feed(sa._fetch_feed())
    saved = 0
    for p in posts:
        try:
            dt = email.utils.parsedate_to_datetime(p.get('date') or '')
            date_str = dt.strftime('%Y-%m-%d')
        except Exception:
            date_str = ''
        post = {
            'id': p.get('id'),
            'title': p.get('title') or '',
            'date': date_str,
            'url': p.get('url') or '',
            'category': p.get('author') or '',
            'body': tf._html_to_text(p.get('content_html') or ''),
        }
        if archive_post('semianalysis', post, 'SemiAnalysis'):
            saved += 1
    print(f'[semianalysis] 저장 {saved} / 피드 {len(posts)}건', flush=True)


def backfill_foreign_ir():
    from sources import foreign_ir as fir
    companies = fir._load_companies()
    results = fir._fetch_all(companies)
    saved = 0
    for r in results:
        if not isinstance(r, dict):
            continue
        comp = r.get('company') if isinstance(r.get('company'), dict) else {}
        cname = (comp.get('name') or comp.get('id') or r.get('company_id')
                 or r.get('name') or '')
        for it in (r.get('items') or []):
            if not isinstance(it, dict):
                continue
            post = {
                'id': it.get('id') or it.get('url') or '',
                'title': it.get('title') or '',
                'date': it.get('date') or '',
                'url': it.get('url') or '',
                'category': cname,
                'body': it.get('body') or '',
            }
            if not post['id']:
                continue
            if archive_post('foreign_ir', post, '해외 IR'):
                saved += 1
    print(f'[foreign_ir] 저장 {saved}건', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', required=True,
                    choices=['kna', 'trendforce', 'semianalysis', 'foreign_ir'])
    ap.add_argument('--max-pages', type=int, default=None)
    a = ap.parse_args()
    if a.source == 'kna':
        backfill_kna(a.max_pages)
    elif a.source == 'trendforce':
        backfill_trendforce(a.max_pages)
    elif a.source == 'semianalysis':
        backfill_semianalysis()
    else:
        backfill_foreign_ir()
