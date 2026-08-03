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
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
)

REQ_TIMEOUT = 30
REQ_DELAY_SEC = 2.0  # 동일 호스트 호출 간 최소 간격


def _http_get(url: str, *, timeout: int = REQ_TIMEOUT) -> str | None:
    """간단 GET. 4xx 영구실패는 즉시 None, 5xx/429는 짧은 backoff 후 1회 retry.

    HTTPError.code로 분류:
    - 4xx (404/403/410 등 ≠ 408/429): 영구 실패 — 즉시 None
    - 408/429/5xx: 일시 장애 — 2초 backoff 후 1회 retry
    """
    import time
    from urllib.error import HTTPError

    for attempt in range(2):
        try:
            req = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'text/html'})
            with urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    logger.warning(f"GET {url} -> {resp.status}")
                    return None
                return resp.read().decode('utf-8', errors='ignore')
        except HTTPError as e:
            code = e.code
            transient = code >= 500 or code in (408, 429)
            if not transient:
                logger.warning(f"GET {url} -> {code} (4xx 영구실패)")
                return None
            if attempt == 0:
                logger.info(f"GET {url} -> {code} (일시 장애), 2s 후 retry")
                time.sleep(2.0)
                continue
            logger.warning(f"GET {url} -> {code} (retry 후에도 실패)")
            return None
        except Exception as e:
            msg = str(e).lower()
            if 'cloudflare' in msg or '403' in msg or 'blocked' in msg:
                logger.error(f"BLOCKED {url}: {e}")
                return None
            # socket timeout / URLError 등 일시 네트워크 장애는 1회 retry
            if attempt == 0 and ('timed out' in msg or 'timeout' in msg or 'urlerror' in msg or 'connection' in msg):
                logger.info(f"GET {url} 일시 네트워크 장애({e}), 2s 후 retry")
                time.sleep(2.0)
                continue
            logger.warning(f"GET fail {url}: {e}")
            return None
    return None


class MotleyFoolSource(TranscriptSource):
    name = 'motley_fool'
    parser_version = '1.1'  # 2026-08-03: 문맥 기반 Q&A 경계 (CCJ 2Q26 오분할 fix)

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
            # 2026-07-31: marketbeat.py 와 동일한 무검증 폴백 — 구조 확인 후에만 사용.
            from ..transcript_gate import check_body
            if not check_body(text[:100000], '', '').ok:
                return None
            prepared_remarks = text[:100000]
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

    # ─── Q&A 분할 신호 (parser 1.1, 2026-08-03) ───
    # 문장 속 "Q&A" 언급은 분할 신호가 아니다 — Operator 오프닝("wait until the
    # Q&A session")·IR 안내멘트("During the Q&A session, please limit...")에서
    # 오분할된 실사고(CCJ 2Q26)가 있다. 신호 2종만 인정:
    #  ① 독립 줄 섹션 헤더 (fool.com "QUESTIONS AND ANSWERS" 등)
    #  ② Operator 발화 블록 안의 Q&A 개시 선언 (marketbeat/Quartr verbatim 전문)
    # 확신할 경계가 없으면 분할하지 않는다 (전체 prepared — translator가 전량 번역).
    _QA_HEADER_LINE_RE = re.compile(
        r'^[ \t]*(?:questions?\s+(?:and|&)\s+answers?|q\s*&\s*a(?:\s+session)?'
        r'|analyst\s+q\s*&\s*a)[ \t]*[:.]?[ \t]*$',
        re.IGNORECASE | re.MULTILINE,
    )
    _QA_TRANSITION_RE = re.compile(
        r"(?:(?:will\s+)?now\s+(?:begin|start)|beginning)\s+the\s+"
        r"question[\s\-‐-―]+and[\s\-‐-―]+answer\s+(?:session|period|portion)"
        r"|open\s+(?:up\s+)?the\s+(?:call|lines?|floor)\s+(?:up\s+)?for\s+questions"
        r"|(?:our|the|your)\s+first\s+question\s+(?:today\s+)?(?:comes|is)\s+from"
        r"|take\s+(?:our|the)\s+first\s+question",
        re.IGNORECASE,
    )
    # 화자 헤더: fool.com "Operator:" / Quartr(marketbeat) "Operator\n00:13:09" / "Operator --"
    _OPERATOR_HEADER_RE = re.compile(r'(?:^|\n)Operator\s*(?::|\n|--)')

    def _split_sections(self, text: str) -> tuple[str, str]:
        """Prepared Remarks / Q&A / Closing 분리 (문맥 기반, parser 1.1).

        구버전(≤1.0)은 루즈한 `Q&A` 정규식의 첫 매치에서 잘라 Operator 오프닝
        boilerplate에 걸리는 오분할이 있었다 (CCJ 2Q26: 경영진 발표 전체가 qa로
        들어가고 번역에서 유실). 이제 독립 헤더/Operator 개시 선언만 신뢰하고,
        페이지 크롬 대비 절대 오프셋 가드는 쓰지 않는다 (본문 시작 이후 여부로 판정).
        """
        # 끝 잘라내기 (Safe Harbor / Closing) — 후반부(len//2 이후)에서만.
        # 오프닝 Safe Harbor에 "Forward-Looking Statements"가 나오는 전문에서
        # 본문 전체가 잘려나가는 것을 방지.
        end_candidates = []
        for end_marker in [
            'Forward-Looking Statements',
            'This concludes today\'s conference',
            'Duration:',
        ]:
            idx = text.find(end_marker, len(text) // 2)
            if idx > 0:
                end_candidates.append(idx)
        if end_candidates:
            text = text[:min(end_candidates)]

        m_prep = re.search(r'\bPREPARED REMARKS\b|\bPrepared Remarks\b', text)

        # 본문 시작 = 첫 화자 블록(또는 PREPARED REMARKS 헤더 끝).
        # marketbeat 페이지 크롬(주가·EPS 표·nav)이 그 앞에 붙는 경우,
        # 크롬 안의 nav 링크("Questions & Answers" 등)를 경계 후보에서 배제한다.
        first_speaker = self._OPERATOR_HEADER_RE.search(text)
        body_start = 0
        if m_prep:
            body_start = m_prep.end()
        elif first_speaker:
            body_start = first_speaker.start()

        candidates = []  # (split_idx, kind)
        # ① 독립 줄 섹션 헤더 — 본문 시작 이후만
        for m in self._QA_HEADER_LINE_RE.finditer(text):
            if m.start() > body_start:
                candidates.append((m.start(), 'header_line'))
        # ② Q&A 개시 선언 — Operator 발화 블록 안에서만 인정: 직전 300자 안에
        #    Operator 화자 헤더가 있어야 하고, 그 헤더 시작점으로 스냅.
        #    (경영진 IR 멘트 "we will open the call for questions" 오탐 차단.
        #    300자 = 개시 선언은 Operator 헤더 직후 문장이라는 실측 — CCJ 31자)
        for m in self._QA_TRANSITION_RE.finditer(text):
            if m.start() <= body_start:
                continue
            window_start = max(0, m.start() - 300)
            ops = list(self._OPERATOR_HEADER_RE.finditer(text, window_start, m.start()))
            if not ops:
                continue
            candidates.append((max(ops[-1].start(), body_start), 'operator_transition'))

        prepared, qa = '', ''
        prep_start = m_prep.end() if m_prep else 0
        if candidates:
            split_idx = min(c[0] for c in candidates)
            if prep_start >= split_idx:
                prep_start = 0
            prepared = text[prep_start:split_idx].strip()
            qa = text[split_idx:].strip()
        else:
            # 확신할 Q&A 경계 없음 — 오분할보다 무분할이 안전 (원문 손실 없음)
            logger.warning(
                '_split_sections: no confident Q&A boundary (len=%d) — 전체를 prepared로',
                len(text),
            )
            prepared = text[prep_start:].strip()
            qa = ''

        if len(prepared) > 100000 or len(qa) > 100000:
            logger.warning(
                '_split_sections: 100K 절단 발생 (prepared=%d, qa=%d)',
                len(prepared), len(qa),
            )
        return prepared[:100000], qa[:100000]
