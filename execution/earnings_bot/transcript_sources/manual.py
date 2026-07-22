"""ManualOverrideSource — 사용자가 직접 URL을 주입하는 소스.

자동 검색 실패 또는 needs_review 격리된 transcript를 사용자가 수동으로 해결할 때 사용.
신뢰도는 1.0으로 고정 (사용자 검증).
"""
from __future__ import annotations

from . import (EarningsEvent, ParsedTranscript, TranscriptCandidate,
               TranscriptSource, content_hash, normalize_url)
from .motley_fool import MotleyFoolSource, _http_get


class ManualOverrideSource(TranscriptSource):
    name = 'manual_override'
    parser_version = '1.0'

    def search(self, event: EarningsEvent) -> list[TranscriptCandidate]:
        # 수동 모드는 search 불가 — 호출자가 직접 candidate를 만들어 parse() 호출
        return []

    def parse(self, candidate: TranscriptCandidate, event: EarningsEvent) -> ParsedTranscript | None:
        html = _http_get(candidate.url)
        if not html:
            return None
        # 본문 추출 — fool.com transcript-content 우선, 그 외 도메인은 article/main 폴백
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        article = (
            soup.find('div', class_='transcript-content')
            or soup.find('div', class_='article-body')
            or soup.find('article')
            or soup.find('main')
            or soup.body
        )
        if not article:
            return None
        text = article.get_text('\n', strip=True)
        prepared, qa = MotleyFoolSource()._split_sections(text)
        if not prepared and not qa:
            prepared = text[:100000]

        return ParsedTranscript(
            source_url=candidate.url,
            normalized_url=normalize_url(candidate.url),
            prepared_remarks=prepared,
            qa=qa,
            content_hash=content_hash(text),
            parser_version=self.parser_version,
            match_confidence=1.0,  # 사용자가 수동 승인 → 신뢰도 만점
            metadata={'manual': True},
        )
