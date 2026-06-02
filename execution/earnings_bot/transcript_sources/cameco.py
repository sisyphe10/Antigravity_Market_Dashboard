"""Cameco transcript source — 자사 IR이 cameco.com에 직접 호스팅하는 PDF transcript.

Cameco(CCJ/CCO)는 캐나다 기업이라 컨퍼런스콜 transcript가 Motley Fool 등 일반
소스에 올라오지 않고 **자사 웹사이트 PDF로만** 제공된다. 그래서 기존 자동 소스
(q4cdn/motley_fool/marketbeat 등)는 CCJ를 못 잡고, 1Q26은 manual_override로 수동 주입됐다.

이 소스는 결정적(deterministic) URL 패턴으로 CCJ를 자동 수집한다:
    https://www.cameco.com/sites/default/files/documents/CCO-transcript-{YEAR}-Q{N}-call.pdf
실측(2026-06-02): 2026-Q1 / 2025-Q4 / 2025-Q3 모두 200 application/pdf 응답.

설계:
- search(): ticker가 Cameco일 때만 (1) 결정적 URL 후보 + (2) site:cameco.com web_search 폴백.
  다른 ticker는 즉시 빈 리스트 → 다음 소스로 폴백 (q4cdn과 동일 패턴).
- parse(): q4cdn의 PDF fetch/extract/split 헬퍼 재사용 (동일 Q4 PDF 처리 로직).
- 결정적 URL은 분기(fy/fq)가 파일명에 인코딩돼 있어 200 = 해당 분기 PDF 확정.
  synthetic title("Cameco (CCJ) Q{fq} {fy} Earnings Call Transcript")로 matcher의
  fiscal_term/keyword/ticker 점수를 확보 → 0.7 임계값 안정 통과.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from . import (EarningsEvent, ParsedTranscript, TranscriptCandidate,
               TranscriptSource, content_hash, normalize_url)
from .search_provider import anthropic_web_search
# q4cdn과 동일한 Q4 PDF 처리 — 공용 PDF 헬퍼 재사용 (중복 회피).
from .q4cdn import (_extract_published_at, _extract_text, _http_get_pdf,
                    _split_sections)

logger = logging.getLogger(__name__)

SITE_DOMAIN = 'cameco.com'
# 자사 공식 IR PDF + 결정적 URL(분기 인코딩) → q4cdn 동급 신뢰. parse() 레벨 floor용.
SOURCE_TRUST_BOOST = 0.15

# Cameco 발행 ticker — 이 소스가 활성화되는 종목.
CAMECO_TICKERS = {'CCJ', 'CCO'}

# 결정적 transcript PDF URL 템플릿 (회계연도=캘린더연도).
URL_TEMPLATE = (
    'https://www.cameco.com/sites/default/files/documents/'
    'CCO-transcript-{fy}-Q{fq}-call.pdf'
)


class CamecoSource(TranscriptSource):
    """Cameco 자사 호스팅 PDF transcript source (CCJ/CCO 전용)."""
    name = 'cameco'
    parser_version = '1.0'

    def search(self, event: EarningsEvent) -> list[TranscriptCandidate]:
        if event.ticker.upper() not in CAMECO_TICKERS:
            return []  # Cameco 외 종목은 즉시 폴백

        fy = event.fiscal_year
        fq = event.fiscal_quarter
        candidates: list[TranscriptCandidate] = []

        if fy and fq:
            # synthetic title로 matcher 점수 확보 (fiscal_term/keyword/ticker).
            candidates.append(TranscriptCandidate(
                url=URL_TEMPLATE.format(fy=fy, fq=fq),
                title=f'Cameco ({event.ticker}) Q{fq} {fy} Earnings Call Transcript',
                snippet='',
                source=self.name,
            ))

        # 폴백: 파일명 변형(과거 분기 등) 대비 site:cameco.com web_search.
        try:
            query = f'Cameco Q{fq} {fy} earnings call transcript pdf'
            for c in anthropic_web_search(query, site=SITE_DOMAIN, max_results=5):
                if not c.url.lower().endswith('.pdf'):
                    continue
                if SITE_DOMAIN not in c.url.lower():
                    continue
                candidates.append(TranscriptCandidate(
                    url=c.url, title=c.title or '', snippet=c.snippet or '',
                    source=self.name,
                ))
        except Exception as e:
            logger.warning(f'cameco web_search 폴백 실패: {e}')

        # URL dedup (결정적 URL과 검색 결과 중복 제거)
        seen = set()
        unique = []
        for c in candidates:
            n = normalize_url(c.url)
            if n in seen:
                continue
            seen.add(n)
            unique.append(c)
        return unique[:5]

    def parse(self, candidate: TranscriptCandidate, event: EarningsEvent) -> ParsedTranscript | None:
        pdf_bytes = _http_get_pdf(candidate.url)
        if not pdf_bytes:
            return None
        text = _extract_text(pdf_bytes)
        if len(text) < 2000:
            logger.warning(f'cameco PDF 텍스트 너무 짧음 ({len(text)} chars): {candidate.url}')
            return None

        prepared_remarks, qa = _split_sections(text)

        # PDF 본문에서 발표일 추출 → matcher의 date_delta 정확도 향상
        published_at = _extract_published_at(text)
        if published_at:
            candidate.published_at = published_at

        from ..matcher import DEFAULT_THRESHOLD, score_candidate
        body_first_2k = (prepared_remarks or text)[:2000]
        confidence = score_candidate(candidate, event, body_first_2k=body_first_2k)
        # 자사 공식 source prior (q4cdn과 동일 패턴). transcript_watch가 본문 기반으로
        # 재계산하므로 임계값 판정엔 영향 적지만, 소스 단독 사용 시 floor 보장.
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
                'pdf_size_bytes': len(pdf_bytes),
                'text_chars': len(text),
                'qa_split_found': bool(qa),
                'published_at': published_at.isoformat() if published_at else None,
                'source_trust_boost': SOURCE_TRUST_BOOST,
                'fetched_at': datetime.now(tz=timezone.utc).isoformat(timespec='seconds'),
            },
        )
