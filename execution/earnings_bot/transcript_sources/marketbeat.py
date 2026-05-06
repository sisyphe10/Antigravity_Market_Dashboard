"""MarketBeat transcript source — fallback after Motley Fool.

Codex Phase 2 v2 권고: search-first + DDG fallback.

URL 패턴 (검증 미완, 라이브 운영 시 fixture로 보강):
  https://www.marketbeat.com/stocks/{exchange}/{ticker}/earnings/
  https://www.marketbeat.com/earnings-transcripts/{date}/{slug}/  (추정)
"""
from __future__ import annotations

import logging
from urllib.parse import quote

from bs4 import BeautifulSoup

from . import (EarningsEvent, ParsedTranscript, TranscriptCandidate,
               TranscriptSource, content_hash, normalize_url)
from .motley_fool import _http_get  # 동일 헬퍼 재사용

logger = logging.getLogger(__name__)


class MarketBeatSource(TranscriptSource):
    name = 'marketbeat'
    parser_version = '1.0'

    HOST = 'https://www.marketbeat.com'

    def search(self, event: EarningsEvent) -> list[TranscriptCandidate]:
        candidates = self._search_marketbeat(event)
        if not candidates:
            candidates = self._search_ddg(event)
        return candidates

    def _search_marketbeat(self, event: EarningsEvent) -> list[TranscriptCandidate]:
        q = f'{event.ticker} Q{event.fiscal_quarter} {event.fiscal_year} earnings transcript'
        url = f'{self.HOST}/search/?ticker={quote(event.ticker)}'
        html = _http_get(url)
        if not html:
            return []
        return self._extract_links(html, ticker=event.ticker)

    def _search_ddg(self, event: EarningsEvent) -> list[TranscriptCandidate]:
        q = (
            f'site:marketbeat.com {event.ticker} Q{event.fiscal_quarter} '
            f'{event.fiscal_year} earnings transcript'
        )
        url = f'https://html.duckduckgo.com/html/?q={quote(q)}'
        html = _http_get(url)
        if not html:
            return []
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        for a in soup.select('a.result__a')[:15]:
            href = a.get('href') or ''
            if 'marketbeat.com' not in href:
                continue
            if 'earnings' not in href.lower() and 'transcript' not in href.lower():
                continue
            title = a.get_text(strip=True)
            results.append(TranscriptCandidate(
                url=href, title=title, snippet='', source=self.name,
            ))
        return results

    def _extract_links(self, html: str, ticker: str) -> list[TranscriptCandidate]:
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        for a in soup.select('a[href]'):
            href = a.get('href') or ''
            if 'marketbeat.com' not in href and not href.startswith('/'):
                continue
            href_lower = href.lower()
            if 'earnings' not in href_lower and 'transcript' not in href_lower:
                continue
            title = a.get_text(strip=True)
            if not title or len(title) > 200:
                continue
            full_url = href if href.startswith('http') else self.HOST + href
            results.append(TranscriptCandidate(
                url=full_url, title=title, snippet='', source=self.name,
            ))
            if len(results) >= 15:
                break
        # dedup
        seen = set()
        out = []
        for c in results:
            n = normalize_url(c.url)
            if n in seen:
                continue
            seen.add(n)
            out.append(c)
        return out

    def parse(self, candidate: TranscriptCandidate, event: EarningsEvent) -> ParsedTranscript | None:
        html = _http_get(candidate.url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')
        article = soup.find('article') or soup.find('main') or soup.find('div', class_='content')
        if not article:
            article = soup.body
        if not article:
            return None

        text = article.get_text('\n', strip=True)
        # MarketBeat은 transcript 구조가 사이트마다 차이. 일단 본문 전체 사용.
        # 섹션 분리는 motley_fool과 동일한 로직 차용
        from .motley_fool import MotleyFoolSource
        prepared, qa = MotleyFoolSource()._split_sections(text)
        if not prepared and not qa:
            prepared = text[:50000]

        from ..matcher import score_candidate
        body_first_2k = (prepared or '')[:2000]
        confidence_estimate = score_candidate(candidate, event, body_first_2k=body_first_2k)

        return ParsedTranscript(
            source_url=candidate.url,
            normalized_url=normalize_url(candidate.url),
            prepared_remarks=prepared,
            qa=qa,
            content_hash=content_hash(text),
            parser_version=self.parser_version,
            match_confidence=confidence_estimate,
            metadata={},
        )
