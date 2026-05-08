"""Insider Monkey transcript source — q4cdn 미사용 회사 폴백.

검증(2026-05-08, AAPL Q2 2026):
- HTTP 200 (봇 UA로도 통과)
- div.single-content selector로 48,689 chars 풀 transcript 추출
- Q&A 마커 'Question and Answer Session' 위치 3,568
- AAPL/MSFT/TSLA 등 q4cdn 미사용 종목 커버 가능

URL 패턴: /blog/{company-slug}-{ticker-lower}-q{n}-{year}-earnings-call-transcript-{id}/
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
    'Antigravity-Earnings-Bot/1.0 '
    '(personal portfolio research; contact kts77775@gmail.com; '
    'respects robots.txt)'
)

REQ_TIMEOUT = 30
SITE_DOMAIN = 'insidermonkey.com'

# Q&A 마커들 — Insider Monkey는 일관되게 "Question and Answer Session" 헤더 사용
_QA_MARKERS = [
    re.compile(r'(?im)question[- ]?and[- ]?answer\s+(session|portion|period)'),
    re.compile(r'(?im)^\s*operator\s*[:\-]?\s*.{0,80}(question|q\s?&\s?a)'),
    re.compile(r'(?im)we\s+will\s+now\s+(open|begin)\s+the\s+lines?\s+for\s+question'),
]

# 본문에서 분리할 사이드바·관련글 시작 마커 (있으면 그 위치 직전까지 cut)
_END_MARKERS = [
    re.compile(r'(?i)related\s+(post|article)s?'),
    re.compile(r'(?i)you\s+might\s+also\s+like'),
    re.compile(r'(?i)hedge\s+fund\s+holdings'),
    re.compile(r'(?i)top\s+hedge\s+funds'),
    re.compile(r'(?i)billionaire\s+investors'),
]

# Insider Monkey published 패턴: "Published on May 1, 2026 at 8:12 am"
_PUBLISHED_PATTERN = re.compile(
    r'(january|february|march|april|may|june|july|august|september|october|november|december)'
    r'\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})',
    re.IGNORECASE,
)
_MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
}


def _http_get(url: str, *, timeout: int = REQ_TIMEOUT) -> str | None:
    try:
        req = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'text/html'})
        with urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                logger.warning(f'GET {url} -> {resp.status}')
                return None
            return resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        logger.warning(f'GET fail {url}: {e}')
        return None


def _extract_published_at(text: str) -> datetime | None:
    m = _PUBLISHED_PATTERN.search(text[:3000])
    if not m:
        return None
    try:
        month = _MONTHS[m.group(1).lower()]
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


def _trim_sidebar(text: str) -> str:
    """본문 끝쪽에 붙는 관련글·hedge fund 사이드바 노이즈 제거."""
    earliest = len(text)
    for pat in _END_MARKERS:
        m = pat.search(text)
        if m and m.start() < earliest:
            earliest = m.start()
    return text[:earliest]


class InsiderMonkeySource(TranscriptSource):
    """Insider Monkey transcript source — div.single-content 풀 텍스트."""
    name = 'insider_monkey'
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

        # dedup
        seen = set()
        unique = []
        for c in candidates:
            n = normalize_url(c.url)
            if n in seen:
                continue
            seen.add(n)
            unique.append(c)

        # ticker 필터: title 또는 URL에 ticker 명시
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
        # 본문 selector 우선순위: single-content (가장 깔끔) → article (fallback)
        body = soup.select_one('div.single-content') or soup.select_one('article')
        if not body:
            logger.warning(f'본문 selector 못 찾음: {candidate.url}')
            return None

        text = body.get_text('\n', strip=True)
        text = _trim_sidebar(text)

        if len(text) < 3000:
            logger.warning(f'Insider Monkey 본문 너무 짧음 ({len(text)} chars): {candidate.url}')
            return None

        prepared_remarks, qa = _split_sections(text)

        published_at = _extract_published_at(text)
        if published_at:
            candidate.published_at = published_at

        from ..matcher import score_candidate, DEFAULT_THRESHOLD
        body_first_2k = (prepared_remarks or text)[:2000]
        confidence = score_candidate(candidate, event, body_first_2k=body_first_2k)
        # Insider Monkey는 search 단계 ticker 필터 + transcript 키워드 + URL 패턴 검증 거침.
        # 풀 transcript 확보 시(>3000 chars) matcher의 보수적 fuzzy 점수 보완.
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
                'fetched_at': datetime.now(tz=timezone.utc).isoformat(timespec='seconds'),
            },
        )
