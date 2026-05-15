"""Globe and Mail transcript source — Motley Fool syndication 미러.

theglobeandmail.com이 The Motley Fool의 transcript을 syndication 받아 자체 host.
fool.com이 일시 장애일 때 동일 콘텐츠를 별도 hosting에서 fetch 가능 (fool fallback).

검증(2026-05-08, AAPL Q2 2026):
- HTTP 200, 봇 UA 통과
- article tag로 55,527 chars 풀 transcript
- "Image source: The Motley Fool" 헤더 + 끝 "The Motley Fool has positions" 디스클로저로 syndication 확인
- DATE 형식: "Thursday, Apr. 30, 2026 at 5 p.m. ET" (abbreviated month)
- Q&A 마커: "first question" @ 32558
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from . import (EarningsEvent, ParsedTranscript, TranscriptCandidate,
               TranscriptSource, content_hash, normalize_url)
from .search_provider import anthropic_web_search

logger = logging.getLogger(__name__)

USER_AGENT = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
)

REQ_TIMEOUT = 30
SITE_DOMAIN = 'theglobeandmail.com'

# G&M(fool 미러) date 형식: "Thursday, Apr. 30, 2026 at 5 p.m. ET"
# 또는 일반 "April 30, 2026" — full + abbreviated 모두 지원
_DATE_PATTERN = re.compile(
    r'(jan(?:uary|\.)?|feb(?:ruary|\.)?|mar(?:ch|\.)?|apr(?:il|\.)?|may'
    r'|jun(?:e|\.)?|jul(?:y|\.)?|aug(?:ust|\.)?|sep(?:tember|t\.|\.)?'
    r'|oct(?:ober|\.)?|nov(?:ember|\.)?|dec(?:ember|\.)?)'
    r'\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})',
    re.IGNORECASE,
)
_MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}

_QA_MARKERS = [
    re.compile(r'(?im)question[- ]?and[- ]?answer\s+(session|portion|period)'),
    re.compile(r'(?im)^\s*operator\s*[:\-]?\s*.{0,80}(question|q\s?&\s?a)'),
    re.compile(r'(?im)we\s+will\s+now\s+(open|begin)\s+the\s+lines?\s+for\s+question'),
    re.compile(r'(?im)first\s+question'),
]


def _http_get(url: str, *, timeout: int = REQ_TIMEOUT) -> str | None:
    """4xx 즉시 None, 5xx/timeout 1회 retry (motley_fool 동일 패턴)."""
    import time
    from urllib.error import HTTPError

    for attempt in range(2):
        try:
            req = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'text/html'})
            with urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    logger.warning(f'GET {url} -> {resp.status}')
                    return None
                return resp.read().decode('utf-8', errors='ignore')
        except HTTPError as e:
            code = e.code
            transient = code >= 500 or code in (408, 429)
            if not transient:
                logger.warning(f'GET {url} -> {code} (4xx 영구실패)')
                return None
            if attempt == 0:
                logger.info(f'GET {url} -> {code} (일시 장애), 2s 후 retry')
                time.sleep(2.0)
                continue
            return None
        except Exception as e:
            msg = str(e).lower()
            if 'cloudflare' in msg or '403' in msg or 'blocked' in msg:
                logger.error(f'BLOCKED {url}: {e}')
                return None
            if attempt == 0 and ('timed out' in msg or 'timeout' in msg or 'urlerror' in msg or 'connection' in msg):
                logger.info(f'GET {url} 일시 네트워크({e}), 2s 후 retry')
                time.sleep(2.0)
                continue
            logger.warning(f'GET fail {url}: {e}')
            return None
    return None


def _extract_published_at(text: str) -> datetime | None:
    m = _DATE_PATTERN.search(text[:2000])
    if not m:
        return None
    try:
        mon_key = m.group(1).lower().rstrip('.').strip()
        # 'apr', 'april', 'sept' -> 'sep' 보정
        if mon_key.startswith('sept'):
            mon_key = 'sep'
        month = _MONTHS.get(mon_key[:3])
        if not month:
            return None
        day = int(m.group(2))
        year = int(m.group(3))
        return datetime(year, month, day, 13, 30, tzinfo=timezone.utc)
    except Exception:
        return None


def _split_sections(text: str) -> tuple[str, str]:
    earliest = -1
    for pat in _QA_MARKERS:
        m = pat.search(text)
        if m and (earliest == -1 or m.start() < earliest):
            earliest = m.start()
    if earliest < 0:
        return text, ''
    return text[:earliest], text[earliest:]


class GlobeAndMailSource(TranscriptSource):
    """Globe and Mail transcript source — Motley Fool syndication 미러."""
    name = 'globe_and_mail'
    parser_version = '1.0'

    def search(self, event: EarningsEvent) -> list[TranscriptCandidate]:
        candidates: list[TranscriptCandidate] = []
        for query in self._build_queries(event):
            results = anthropic_web_search(query, site=SITE_DOMAIN, max_results=5)
            for c in results:
                url_lower = c.url.lower()
                if SITE_DOMAIN not in url_lower:
                    continue
                if 'transcript' not in url_lower and 'transcript' not in (c.title or '').lower():
                    continue
                candidates.append(TranscriptCandidate(
                    url=c.url, title=c.title or '', snippet=c.snippet or '', source=self.name,
                ))
            if candidates:
                break

        seen = set()
        unique = []
        for c in candidates:
            n = normalize_url(c.url)
            if n in seen:
                continue
            seen.add(n)
            unique.append(c)

        ticker_lower = event.ticker.lower()
        filtered = [
            c for c in unique
            if ticker_lower in (c.title or '').lower() or ticker_lower in c.url.lower()
        ]
        return filtered[:5]

    def _build_queries(self, event: EarningsEvent) -> list[str]:
        names = event.company_names or [event.ticker]
        primary = names[0]
        fy = event.fiscal_year
        fq = event.fiscal_quarter
        return [
            f'{event.ticker} Q{fq} {fy} earnings call transcript',
            f'{primary} Q{fq} {fy} earnings call transcript',
        ]

    def parse(self, candidate: TranscriptCandidate, event: EarningsEvent) -> ParsedTranscript | None:
        html = _http_get(candidate.url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')
        body = soup.select_one('article') or soup.select_one('main') or soup.select_one('div.content')
        if not body:
            logger.warning(f'본문 selector 못 찾음: {candidate.url}')
            return None

        text = body.get_text('\n', strip=True)
        if len(text) < 5000:
            logger.warning(f'G&M 본문 너무 짧음 ({len(text)} chars): {candidate.url}')
            return None

        prepared_remarks, qa = _split_sections(text)

        published_at = _extract_published_at(text)
        if published_at:
            candidate.published_at = published_at

        from ..matcher import score_candidate, DEFAULT_THRESHOLD
        body_first_2k = (prepared_remarks or text)[:2000]
        confidence = score_candidate(candidate, event, body_first_2k=body_first_2k)
        # Globe and Mail은 fool 콘텐츠 syndication (검증된 transcript). source trust + floor 동일 패턴.
        SOURCE_TRUST_BOOST = 0.10
        confidence = min(1.0, max(DEFAULT_THRESHOLD, confidence + SOURCE_TRUST_BOOST))

        return ParsedTranscript(
            source_url=candidate.url,
            normalized_url=normalize_url(candidate.url),
            prepared_remarks=prepared_remarks,
            qa=qa,
            content_hash=content_hash(text),
            parser_version=self.parser_version,
            match_confidence=confidence,
            metadata={
                'text_chars': len(text),
                'qa_split_found': bool(qa),
                'published_at': published_at.isoformat() if published_at else None,
                'syndicated_from': 'motley_fool',
                'fetched_at': datetime.now(tz=timezone.utc).isoformat(timespec='seconds'),
            },
        )
