"""신뢰도 점수 산출 — Codex Phase 2 v2 권고.

가중치:
- 회사명 유사도 (rapidfuzz token_sort_ratio)  : 0.30
- ticker 본문 언급                             : 0.20
- fiscal Q/Y 표현 매치 (expected_title_terms)  : 0.30
- 발표일 delta (≤ 1일)                          : 0.10
- "earnings call" / "transcript" 키워드        : 0.10

임계값 0.7 미만 → needs_review (transcript_watch가 격리).
"""
from __future__ import annotations

from datetime import datetime, timezone

from rapidfuzz import fuzz

from .transcript_sources import EarningsEvent, TranscriptCandidate, ParsedTranscript


# 가중치 (합 = 1.0)
W_COMPANY_NAME = 0.30
W_TICKER_MENTION = 0.20
W_FISCAL_TERM = 0.30
W_DATE_DELTA = 0.10
W_KEYWORD = 0.10

DEFAULT_THRESHOLD = 0.7


def _company_name_score(title: str, body_first_2k: str, company_names: list[str]) -> float:
    """token_set_ratio max — 0~1. 짧은 회사명이 긴 transcript 본문에 묻혀 점수가
    sort 기반에서 1% 이하로 떨어지던 문제 회피 (RDDT 'Reddit' 1.0% → 100%).
    set 기반이라 ticker 같은 단일 토큰 false positive는 ticker_mention 가중치로 분리 처리."""
    if not company_names:
        return 0.0
    text = f"{title} {body_first_2k}"
    scores = [fuzz.token_set_ratio(name.lower(), text.lower()) / 100.0 for name in company_names]
    return max(scores) if scores else 0.0


def _ticker_mention_score(title: str, body_first_2k: str, ticker: str) -> float:
    """1.0 (title+body 둘 다) / 0.5 (한 쪽만) / 0.0."""
    t = ticker.upper()
    in_title = t in title.upper()
    in_body = t in body_first_2k.upper()
    if in_title and in_body:
        return 1.0
    if in_title or in_body:
        return 0.5
    return 0.0


def _fiscal_term_score(title: str, body_first_2k: str, expected_terms: list[str]) -> float:
    """expected_title_terms 중 1개 이상 매치 시 1.0, 아니면 0.0."""
    if not expected_terms:
        return 0.0
    text = f"{title} {body_first_2k}".lower()
    return 1.0 if any(t.lower() in text for t in expected_terms) else 0.0


def _date_delta_score(published_at: datetime | None, expected_dt: datetime) -> float:
    """발표일 차이 — 1일 이내 1.0, 3일 이내 0.5, 그 외 0.0."""
    if published_at is None:
        return 0.5  # unknown은 중간값
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    if expected_dt.tzinfo is None:
        expected_dt = expected_dt.replace(tzinfo=timezone.utc)
    delta_h = abs((published_at - expected_dt).total_seconds()) / 3600.0
    if delta_h <= 24:
        return 1.0
    if delta_h <= 72:
        return 0.5
    return 0.0


def _keyword_score(title: str, body_first_2k: str) -> float:
    """'earnings call' 또는 'transcript' 키워드 포함 여부."""
    text = f"{title} {body_first_2k}".lower()
    if 'earnings call' in text or 'transcript' in text:
        return 1.0
    return 0.0


def score_candidate(candidate: TranscriptCandidate, event: EarningsEvent,
                    body_first_2k: str = '') -> float:
    """검색 단계의 후보 점수 — 본문 미확보 시 title + snippet 기반."""
    text_body = body_first_2k or candidate.snippet
    return (
        W_COMPANY_NAME * _company_name_score(candidate.title, text_body, event.company_names)
        + W_TICKER_MENTION * _ticker_mention_score(candidate.title, text_body, event.ticker)
        + W_FISCAL_TERM * _fiscal_term_score(candidate.title, text_body, event.expected_title_terms)
        + W_DATE_DELTA * _date_delta_score(candidate.published_at, event.expected_call_datetime)
        + W_KEYWORD * _keyword_score(candidate.title, text_body)
    )


def score_parsed(parsed: ParsedTranscript, candidate: TranscriptCandidate,
                 event: EarningsEvent) -> float:
    """파싱 후 본문 기반 정밀 점수. parse() 결과의 match_confidence로 저장."""
    body_first_2k = parsed.prepared_remarks[:2000] if parsed.prepared_remarks else ''
    return score_candidate(candidate, event, body_first_2k=body_first_2k)


def is_acceptable(confidence: float, threshold: float = DEFAULT_THRESHOLD) -> bool:
    return confidence >= threshold


# ─── 자가 테스트 ───
if __name__ == "__main__":
    from datetime import datetime, timezone
    event = EarningsEvent(
        ticker='ASML',
        fiscal_year=2026,
        fiscal_quarter=1,
        expected_call_datetime=datetime(2026, 4, 15, 13, 0, tzinfo=timezone.utc),
        company_names=['ASML Holding NV', 'ASML'],
        expected_title_terms=['Q1 2026', '1Q26', 'first quarter 2026'],
        filing_id=1,
    )
    cand = TranscriptCandidate(
        url='https://www.fool.com/earnings/call-transcripts/2026/04/16/asml-asml-q1-2026-earnings-call-transcript/',
        title='ASML Holding (ASML) Q1 2026 Earnings Call Transcript',
        snippet='ASML Holding NV (ASML) Q1 2026 earnings call dated April 15, 2026.',
        published_at=datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc),
    )
    score = score_candidate(cand, event)
    print(f"sample candidate score: {score:.3f}  (threshold={DEFAULT_THRESHOLD})")
    print(f"acceptable: {is_acceptable(score)}")
