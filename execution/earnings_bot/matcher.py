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

import re
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


def _company_name_score(title: str, body_first_2k: str, company_names: list[str],
                        ticker: str = '') -> float:
    """token_set_ratio max — 0~1. 짧은 회사명이 긴 transcript 본문에 묻혀 점수가
    sort 기반에서 1% 이하로 떨어지던 문제 회피 (RDDT 'Reddit' 1.0% → 100%).
    set 기반이라 ticker 같은 단일 토큰 false positive는 ticker_mention 가중치로 분리 처리.

    ★2026-07-15: company_names에 폴백으로 섞인 bare ticker는 제외하고 채점.
    'ERIC'이 HEICO 콜의 인명 'Eric Mendelson'과 token_set 100% 매칭돼 타사 transcript가
    0.8로 통과한 사고 — 티커 자체 언급은 ticker_mention 축이 이미 담당."""
    if not company_names:
        return 0.0
    names = [n for n in company_names if n.strip().upper() != ticker.strip().upper()]
    if not names:
        return 0.0
    text = f"{title} {body_first_2k}"
    scores = [fuzz.token_set_ratio(name.lower(), text.lower()) / 100.0 for name in names]
    return max(scores) if scores else 0.0


def _ticker_mention_score(title: str, body_first_2k: str, ticker: str) -> float:
    """1.0 (title+body 둘 다) / 0.5 (한 쪽만) / 0.0.

    ★2026-07-15: substring → 단어 경계 매칭. 'ERIC' in 'AMERICAN' 같은 FP 차단."""
    t = ticker.upper()
    pattern = re.compile(rf'\b{re.escape(t)}\b')
    in_title = bool(pattern.search(title.upper()))
    in_body = bool(pattern.search(body_first_2k.upper()))
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


def score_candidate_breakdown(candidate: TranscriptCandidate, event: EarningsEvent,
                              body_first_2k: str = '') -> dict:
    """후보 점수 + 컴포넌트 breakdown. low_confidence 진단용.

    반환 키:
      - total: float (가중 합산, score_candidate와 동일)
      - scores: dict[str, float] 5개 raw sub-score (0.0~1.0)
      - weighted: dict[str, float] 5개 가중 적용 (sum == total)
    """
    text_body = body_first_2k or candidate.snippet
    raw = {
        'company_name': _company_name_score(candidate.title, text_body, event.company_names,
                                            ticker=event.ticker),
        'ticker_mention': _ticker_mention_score(candidate.title, text_body, event.ticker),
        'fiscal_term': _fiscal_term_score(candidate.title, text_body, event.expected_title_terms),
        'date_delta': _date_delta_score(candidate.published_at, event.expected_call_datetime),
        'keyword': _keyword_score(candidate.title, text_body),
    }
    weighted = {
        'company_name': W_COMPANY_NAME * raw['company_name'],
        'ticker_mention': W_TICKER_MENTION * raw['ticker_mention'],
        'fiscal_term': W_FISCAL_TERM * raw['fiscal_term'],
        'date_delta': W_DATE_DELTA * raw['date_delta'],
        'keyword': W_KEYWORD * raw['keyword'],
    }
    # FP 노이즈 정리 (DB/CLI 가독성). threshold 비교 결과는 round 전후 동일.
    raw = {k: round(v, 6) for k, v in raw.items()}
    weighted = {k: round(v, 6) for k, v in weighted.items()}
    return {
        'total': round(sum(weighted.values()), 6),
        'scores': raw,
        'weighted': weighted,
    }


def score_candidate(candidate: TranscriptCandidate, event: EarningsEvent,
                    body_first_2k: str = '') -> float:
    """검색 단계의 후보 점수 — 본문 미확보 시 title + snippet 기반.

    backward-compatible 얇은 wrapper. 진단이 필요하면 score_candidate_breakdown() 사용.
    """
    return score_candidate_breakdown(candidate, event, body_first_2k)['total']


def score_parsed_breakdown(parsed: ParsedTranscript, candidate: TranscriptCandidate,
                           event: EarningsEvent) -> dict:
    """파싱 후 본문 기반 정밀 점수 + breakdown. transcript_watch가 last_error에 dump."""
    body_first_2k = parsed.prepared_remarks[:2000] if parsed.prepared_remarks else ''
    return score_candidate_breakdown(candidate, event, body_first_2k=body_first_2k)


def score_parsed(parsed: ParsedTranscript, candidate: TranscriptCandidate,
                 event: EarningsEvent) -> float:
    """파싱 후 본문 기반 정밀 점수. parse() 결과의 match_confidence로 저장.

    backward-compatible wrapper. 진단이 필요하면 score_parsed_breakdown() 사용.
    """
    return score_parsed_breakdown(parsed, candidate, event)['total']


def is_acceptable(confidence: float, threshold: float = DEFAULT_THRESHOLD) -> bool:
    return confidence >= threshold


# ─── 자가 테스트 ───
if __name__ == "__main__":
    import json
    from datetime import datetime, timezone

    # ── case 1: pass — ASML 풀 회사명 매칭 ──
    event_pass = EarningsEvent(
        ticker='ASML',
        fiscal_year=2026,
        fiscal_quarter=1,
        expected_call_datetime=datetime(2026, 4, 15, 13, 0, tzinfo=timezone.utc),
        company_names=['ASML Holding NV', 'ASML'],
        expected_title_terms=['Q1 2026', '1Q26', 'first quarter 2026'],
        filing_id=1,
    )
    cand_pass = TranscriptCandidate(
        url='https://www.fool.com/earnings/call-transcripts/2026/04/16/asml-asml-q1-2026-earnings-call-transcript/',
        title='ASML Holding (ASML) Q1 2026 Earnings Call Transcript',
        snippet='ASML Holding NV (ASML) Q1 2026 earnings call dated April 15, 2026.',
        published_at=datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc),
    )
    bd_pass = score_candidate_breakdown(cand_pass, event_pass)
    print(f'[PASS case] ASML total={bd_pass["total"]:.3f}')
    print(f'  scores={bd_pass["scores"]}')
    print(f'  weighted={bd_pass["weighted"]}')
    assert bd_pass['total'] >= DEFAULT_THRESHOLD, f'expected pass, got {bd_pass["total"]}'
    assert abs(bd_pass['total'] - sum(bd_pass['weighted'].values())) < 1e-9, \
        'total mismatch with weighted sum'

    # ── case 2: fail — RDDT-like 짧은 회사명 + ticker_registry 미등록 합성 케이스 ──
    # 짧은 ticker(단일 토큰)만 company_names에 있으면 본문에 묻혀 회사명 점수가 떨어짐.
    # 후보 제목이 정식 회사명만 적고 ticker 안 적는 marketbeat 패턴을 재현.
    # production breakdown 로깅이 실제 진단 동선 — fixture는 의도 명시용.
    event_fail = EarningsEvent(
        ticker='RDDT',
        fiscal_year=2026,
        fiscal_quarter=1,
        expected_call_datetime=datetime(2026, 5, 6, 0, 0, tzinfo=timezone.utc),
        company_names=['RDDT'],  # ticker_registry 미등록 시 fallback
        expected_title_terms=['Q1 2026', '1Q26', 'first quarter 2026', 'Q1 FY26'],
        filing_id=999,
    )
    cand_fail = TranscriptCandidate(
        url='https://www.marketbeat.com/earnings/transcripts/reddit-q1-2026/',
        title='Reddit Q1 2026 Earnings Conference Call',
        snippet='Reddit reported quarterly results.',
        published_at=datetime(2026, 5, 7, 0, 0, tzinfo=timezone.utc),
    )
    bd_fail = score_candidate_breakdown(cand_fail, event_fail)
    print(f'[FAIL case] RDDT-like total={bd_fail["total"]:.3f}')
    print(f'  scores={bd_fail["scores"]}')
    print(f'  weighted={bd_fail["weighted"]}')
    print(f'  last_error_dump={json.dumps(bd_fail)}')
    assert bd_fail['total'] < DEFAULT_THRESHOLD, f'expected fail, got {bd_fail["total"]}'
    assert abs(bd_fail['total'] - sum(bd_fail['weighted'].values())) < 1e-9, \
        'total mismatch with weighted sum'

    # backward compat — score_candidate() / score_parsed() 시그니처 그대로 동작
    assert score_candidate(cand_pass, event_pass) == bd_pass['total']
    print('\nself-test OK (PASS + FAIL + backward-compat)')
