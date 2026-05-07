"""Motley Fool transcript source — search-first, DDG fallback.

Codex Phase 2 v2 권고:
- search-first: fool.com 자체 검색 → 실패 시 DuckDuckGo HTML 검색
- URL 패턴 직접 생성은 폴백 (slug 역산 불가능)
- robots.txt 준수, 명확한 User-Agent

URL 패턴 예시 (검증 후 보강 예정):
  https://www.fool.com/earnings/call-transcripts/YYYY/MM/DD/{slug}/
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from . import (EarningsEvent, ParsedTranscript, TranscriptCandidate,
               TranscriptSource, content_hash, normalize_url)

logger = logging.getLogger(__name__)

USER_AGENT = (
    'Antigravity-Earnings-Bot/1.0 '
    '(personal portfolio research; contact kts77775@gmail.com; '
    'respects robots.txt)'
)

REQ_TIMEOUT = 30
REQ_DELAY_SEC = 2.0  # 동일 호스트 호출 간 최소 간격


def _http_get(url: str, *, timeout: int = REQ_TIMEOUT) -> str | None:
    """간단 GET. 비-200은 None 반환. 차단 식별 키워드 로깅."""
    try:
        req = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'text/html'})
        with urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                logger.warning(f"GET {url} → {resp.status}")
                return None
            return resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        msg = str(e).lower()
        if 'cloudflare' in msg or '403' in msg or 'blocked' in msg:
            logger.error(f"BLOCKED {url}: {e}")
        else:
            logger.warning(f"GET fail {url}: {e}")
        return None


class MotleyFoolSource(TranscriptSource):
    name = 'motley_fool'
    parser_version = '1.0'

    HOST = 'https://www.fool.com'

    def search(self, event: EarningsEvent) -> list[TranscriptCandidate]:
        """1순위: Anthropic web_search → 2순위: fool.com 자체 검색 → 3순위: DDG HTML."""
        from .search_provider import anthropic_web_search
        query = f'{event.ticker} Q{event.fiscal_quarter} {event.fiscal_year} earnings call transcript'
        candidates = anthropic_web_search(query, site='fool.com')
        if candidates:
            return candidates
        candidates = self._search_fool(event)
        if not candidates:
            candidates = self._search_ddg(event)
        return candidates

    # ─── fool.com 자체 검색 ───
    def _search_fool(self, event: EarningsEvent) -> list[TranscriptCandidate]:
        q = f'{event.ticker} Q{event.fiscal_quarter} {event.fiscal_year} earnings call transcript'
        url = f'{self.HOST}/search/?q={quote(q)}'
        html = _http_get(url)
        if not html:
            return []
        return self._parse_search_html(html, host_required='fool.com')

    # ─── DuckDuckGo HTML 검색 (폴백) ───
    def _search_ddg(self, event: EarningsEvent) -> list[TranscriptCandidate]:
        q = f'site:fool.com {event.ticker} Q{event.fiscal_quarter} {event.fiscal_year} earnings call transcript'
        url = f'https://html.duckduckgo.com/html/?q={quote(q)}'
        html = _http_get(url)
        if not html:
            return []
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        for a in soup.select('a.result__a')[:15]:
            href = a.get('href') or ''
            if 'fool.com/earnings' not in href:
                continue
            title = a.get_text(strip=True)
            results.append(TranscriptCandidate(
                url=href,
                title=title,
                snippet='',
                source=self.name,
            ))
        return results

    # ─── 검색 결과 HTML 파서 (fool.com 공통) ───
    def _parse_search_html(self, html: str, host_required: str) -> list[TranscriptCandidate]:
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        for a in soup.select('a[href]'):
            href = a.get('href') or ''
            if host_required not in href:
                continue
            if '/earnings/call-transcripts/' not in href and '/earnings-call-transcripts/' not in href:
                continue
            title = a.get_text(strip=True)
            if not title:
                continue
            if not href.startswith('http'):
                href = self.HOST + href
            results.append(TranscriptCandidate(
                url=href,
                title=title,
                snippet='',
                source=self.name,
            ))
            if len(results) >= 15:
                break
        # 중복 제거 (URL 기준)
        seen = set()
        unique = []
        for c in results:
            n = normalize_url(c.url)
            if n in seen:
                continue
            seen.add(n)
            unique.append(c)
        return unique

    # ─── transcript 본문 파싱 ───
    def parse(self, candidate: TranscriptCandidate, event: EarningsEvent) -> ParsedTranscript | None:
        html = _http_get(candidate.url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')

        # 본문 영역 — fool.com 실측: <div class="article-body transcript-content">
        # (article 태그는 사이드바라 무시. 실측 검증: 2026-05 AAPL Q2 transcript)
        article = (
            soup.find('div', class_='transcript-content')
            or soup.find('div', class_='article-body')
            or soup.find('main')
            or soup.body
        )
        if not article:
            return None

        # 발표일 추출 (메타 태그 우선)
        published_at = self._extract_published_at(soup) or candidate.published_at

        # 본문 텍스트 + 섹션 구조
        text = article.get_text('\n', strip=True)
        prepared_remarks, qa = self._split_sections(text)
        if not prepared_remarks and not qa:
            # 섹션 분리 실패 — 폴백: 전체 본문을 prepared_remarks로
            prepared_remarks = text[:50000]
            qa = ''

        # 신뢰도는 호출자(transcript_watch)가 matcher.py로 산출. 여기선 placeholder.
        from ..matcher import score_parsed
        candidate.published_at = published_at
        body_first_2k = (prepared_remarks or '')[:2000]
        # fall back: candidate-level score until full ParsedTranscript exists
        from ..matcher import score_candidate
        confidence_estimate = score_candidate(candidate, event, body_first_2k=body_first_2k)

        parsed = ParsedTranscript(
            source_url=candidate.url,
            normalized_url=normalize_url(candidate.url),
            prepared_remarks=prepared_remarks,
            qa=qa,
            content_hash=content_hash(text),
            parser_version=self.parser_version,
            match_confidence=confidence_estimate,
            metadata={'published_at': published_at.isoformat() if published_at else None},
        )
        return parsed

    def _extract_published_at(self, soup: BeautifulSoup) -> datetime | None:
        # fool.com은 article:published_time meta 태그 사용
        for sel, attr in [
            ('meta[property="article:published_time"]', 'content'),
            ('meta[name="article:published_time"]', 'content'),
            ('time[datetime]', 'datetime'),
        ]:
            el = soup.select_one(sel)
            if el:
                v = el.get(attr)
                if v:
                    try:
                        return datetime.fromisoformat(v.replace('Z', '+00:00'))
                    except Exception:
                        continue
        return None

    def _split_sections(self, text: str) -> tuple[str, str]:
        """Prepared Remarks / Q&A / Closing 분리.

        실제 fool.com 패턴: "PREPARED REMARKS" / "QUESTIONS AND ANSWERS" / "Operator" 헤더 다양.
        Operator 첫 등장 위치를 Q&A 시작으로 추정 (가장 안정적인 신호).
        """
        # 끝 잘라내기 (Safe Harbor / Closing)
        for end_marker in [
            'Forward-Looking Statements',
            'This concludes today\'s conference',
            'Duration:',
        ]:
            idx = text.find(end_marker)
            if idx > 0:
                text = text[:idx]
                break

        prepared, qa = '', ''
        # 1차: 명시적 Q&A 헤더
        m_qa = re.search(
            r'\b(Questions? and Answers?|Q&A Session|Q\s*&\s*A|Analyst Q&A|QUESTIONS AND ANSWERS)\b',
            text, flags=re.IGNORECASE,
        )
        # 2차: Operator 첫 발화 (실측 fool.com 패턴: "\nOperator:\n" 형태)
        # — Suhasini "Operator, may we..." 같은 IR 인용은 제외하기 위해 newline 직후 패턴만 매치
        m_operator = None
        if not m_qa:
            m_operator = re.search(r'(?:^|\n)Operator\s*:\s*\n', text)
            if not m_operator:
                m_operator = re.search(
                    r'\bOperator\b\s*[:\-]?\s*(?:Thank you|Thanks|Ladies and gentlemen|Welcome|At this time)',
                    text, flags=re.IGNORECASE,
                )

        # Prepared / Q&A 분할
        m_prep = re.search(r'\bPREPARED REMARKS\b|\bPrepared Remarks\b', text)

        split_idx = None
        if m_qa:
            split_idx = m_qa.start()
        elif m_operator:
            split_idx = m_operator.start()

        if split_idx is not None:
            prep_start = m_prep.end() if m_prep and m_prep.end() < split_idx else 0
            prepared = text[prep_start:split_idx].strip()
            qa = text[split_idx:].strip()
        else:
            # Q&A 시작점을 못 찾음 — 전체를 prepared로
            prep_start = m_prep.end() if m_prep else 0
            prepared = text[prep_start:].strip()
            qa = ''

        return prepared[:50000], qa[:50000]
