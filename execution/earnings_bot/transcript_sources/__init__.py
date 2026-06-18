"""TranscriptSource ABC + canonical EarningsEvent / Candidate / Parsed dataclass.

설계: Codex Phase 2 v2 권고
- Search-first: search() → URL 후보 리스트 (검색 결과에서 추출)
- Pattern-based URL 직접 생성은 폴백으로만
- parse(): URL 받아 본문 추출 + 신뢰도 점수 산출
- name 속성: 'motley_fool' / 'marketbeat' / 'manual_override'
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EarningsEvent:
    """canonical 발표 이벤트 — transcript 매칭의 단일 진실 소스."""
    ticker: str
    fiscal_year: int
    fiscal_quarter: int                  # 회사 fiscal Q (calendar Q와 다를 수 있음)
    expected_call_datetime: datetime     # AMC=시장종료+1h / BMO=시장개장-1h (UTC)
    company_names: list[str]             # ['ASML Holding NV', 'ASML', 'ASML Holdings']
    expected_title_terms: list[str]      # ['Q1 2026', '1Q26', 'first quarter 2026', 'Q1 FY26']
    filing_id: int                       # filings.id FK


@dataclass
class TranscriptCandidate:
    """search()의 결과 — 후보 URL + 매칭 신호."""
    url: str
    title: str
    snippet: str = ''
    published_at: datetime | None = None  # 검색 결과에서 알 수 있으면 채움
    source: str = ''                       # source.name


@dataclass
class ParsedTranscript:
    """parse()의 결과 — DB insert 가능한 형태."""
    source_url: str
    normalized_url: str
    prepared_remarks: str
    qa: str
    content_hash: str
    parser_version: str
    match_confidence: float                # 0.0~1.0 (matcher.py 산출)
    metadata: dict = field(default_factory=dict)


class TranscriptSource(ABC):
    """모든 transcript 소스의 공통 인터페이스."""
    name: str = ''
    parser_version: str = '1.0'

    @abstractmethod
    def search(self, event: EarningsEvent) -> list[TranscriptCandidate]:
        """이벤트에 매칭되는 transcript URL 후보 검색. 빈 리스트 가능."""
        ...

    @abstractmethod
    def parse(self, candidate: TranscriptCandidate, event: EarningsEvent) -> ParsedTranscript | None:
        """URL fetch + HTML 파싱 + 신뢰도 산출. 실패 시 None.

        실패 사유 구분이 필요하면 self.last_failure_reason 같은 attribute로 노출.
        호출자(transcript_watch)가 status를 'not_found'/'blocked'/'parse_failed' 등으로 분류.
        """
        ...


# ─── 공용 헬퍼 ───
def normalize_url(url: str) -> str:
    """쿼리 파라미터 제거 + trailing slash 통일 + 소문자 호스트."""
    from urllib.parse import urlparse, urlunparse
    p = urlparse(url)
    netloc = p.netloc.lower()
    path = p.path.rstrip('/')
    return urlunparse((p.scheme.lower() or 'https', netloc, path, '', '', ''))


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8', errors='ignore')).hexdigest()


def make_event_from_filing(filing_row: dict, ticker_meta: dict | None = None) -> EarningsEvent:
    """filings 테이블 row + 메타에서 EarningsEvent 생성.

    filing_row: db.get_conn().execute('SELECT * FROM filings WHERE id=?').fetchone() dict
    ticker_meta: ticker_registry.get_issuer_meta(ticker) (외국 발행인 표시용)
    """
    from datetime import timezone

    ticker = filing_row['ticker']
    filed_at = filing_row.get('filed_at') or ''
    try:
        # ISO8601 가정. fallback으로 단순 date 처리
        if 'T' in filed_at:
            event_dt = datetime.fromisoformat(filed_at.replace('Z', '+00:00'))
        else:
            event_dt = datetime.fromisoformat(filed_at + 'T13:30:00+00:00')
    except Exception:
        event_dt = datetime.now(tz=timezone.utc)

    # AMC/BMO 보정 — filed_at은 SEC 접수 시각이라 발표시각과 다를 수 있음
    amc_or_bmo = filing_row.get('amc_or_bmo')
    if amc_or_bmo == 'amc':
        # 미국 ET 16:00 종료 → +1h (콜 시간) → UTC 21:00
        event_dt = event_dt.replace(hour=21, minute=0, second=0)
    elif amc_or_bmo == 'bmo':
        # 미국 ET 09:30 개장 - 1h (콜 시간) → UTC 13:30
        event_dt = event_dt.replace(hour=13, minute=30, second=0)

    # fiscal_year / quarter — earnings_calendar에서 lookup, 없으면 filed_at에서 추정
    from . import _calendar_lookup  # type: ignore  # 순환 회피용 stub (아래 정의)
    fy, fq = _calendar_lookup(ticker, filed_at[:10] if filed_at else '')
    if not fy or not fq:
        # 발표일에서 약 45일 lag를 빼면 직전 분기 종료점 (= 발표 대상 분기 종료일).
        # 비-캘린더 FY 기업 (TPR=June, AAPL=Sep 등)은 FY end month 기준으로 환산.
        # 예: TPR 5/7 filing → period_end ≒ 3/23 → FY end June → FQ3 FY26.
        from datetime import timedelta
        period_end = event_dt - timedelta(days=45)
        p_month = period_end.month
        p_year = period_end.year
        try:
            from .. import ticker_registry as _tr
            fy_end_month = _tr.get_fiscal_year_end_month(ticker)
        except Exception:
            fy_end_month = 12
        fy_start_month = (fy_end_month % 12) + 1  # FY 시작 월
        month_in_fy = (p_month - fy_start_month) % 12 + 1  # 1..12 (FY 내 월 순서)
        computed_fq = (month_in_fy - 1) // 3 + 1
        # FY: period end month가 FY end month 초과 시 다음 FY (예: AAPL Dec → FY+1)
        computed_fy = p_year + 1 if p_month > fy_end_month else p_year
        fy = fy or computed_fy
        fq = fq or computed_fq

    company_names = [ticker]
    if ticker_meta and ticker_meta.get('note'):
        company_names.append(ticker_meta['note'])
    try:
        from .. import ticker_registry as _tr
        sec_name = _tr.get_company_name(ticker)
        if sec_name:
            company_names.append(sec_name)
            # 'Reddit, Inc.' → 'Reddit' 같은 단축형도 fuzzy 매치 풀에 추가
            core = sec_name.split(',')[0].strip()
            if core and core not in company_names:
                company_names.append(core)
    except Exception:
        pass

    expected_title_terms = []
    if fy and fq:
        ordinal = ["first", "second", "third", "fourth"][fq - 1]
        expected_title_terms.extend([
            f'Q{fq} {fy}',
            f'{fq}Q{fy % 100:02d}',
            f'{ordinal} quarter {fy}',
            f'Q{fq} FY{fy % 100:02d}',
            f'Q{fq} FY{fy}',            # 4자리 FY 표기 ("Q1 FY2026") substring 매칭용
        ])
        # 비-캘린더 FY 기업(LULU=1월, TPR=6월 등)은 transcript 소스가 회사 FY를
        # 다르게 표기할 수 있음(우리 fy=2027인데 소스는 "Q1 FY2026"). fy±1 변형 추가로
        # 연도 표기 컨벤션 불일치를 흡수. date_delta(±1일) 가중치가 엉뚱한 연도
        # transcript fetch를 막아 회귀 위험은 낮음.
        try:
            from .. import ticker_registry as _tr
            _fy_end_month = _tr.get_fiscal_year_end_month(ticker)
        except Exception:
            _fy_end_month = 12
        if _fy_end_month != 12:
            for alt_fy in (fy - 1, fy + 1):
                expected_title_terms.extend([
                    f'Q{fq} {alt_fy}',
                    f'Q{fq} FY{alt_fy}',
                    f'Q{fq} FY{alt_fy % 100:02d}',
                    f'{fq}Q{alt_fy % 100:02d}',
                ])

    return EarningsEvent(
        ticker=ticker,
        fiscal_year=fy or event_dt.year,
        fiscal_quarter=fq or ((event_dt.month - 1) // 3 + 1),
        expected_call_datetime=event_dt,
        company_names=company_names,
        expected_title_terms=expected_title_terms,
        filing_id=filing_row['id'],
    )


def _calendar_lookup(ticker: str, event_date: str) -> tuple[int | None, int | None]:
    """earnings_calendar에서 fiscal year/quarter 조회. 없으면 (None, None)."""
    if not event_date:
        return (None, None)
    from .. import db  # 지연 import (순환 회피)
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT year, quarter FROM earnings_calendar WHERE ticker=? AND event_date=?",
            (ticker, event_date),
        ).fetchone()
        if row:
            return (row['year'], row['quarter'])
    except Exception:
        pass
    finally:
        conn.close()
    return (None, None)
