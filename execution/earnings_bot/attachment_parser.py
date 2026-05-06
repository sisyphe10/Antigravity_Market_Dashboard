"""edgartools Filing → 첨부 추출 + 분류.

Codex BLOCKER #1 대응: 8-K Item 2.02 본문은 "첨부 참조"만 있고 실제 데이터는
EX-99.1/99.2에 있음. 6-K도 동일.

분류 규칙 (Phase 0 dry-fetch 기반):
- ASML 분기 실적: 6-K + EX-99.1(보도자료) + EX-99.2(presentation) + EX-99.3(재무) → HIGH
- TSM 분기 실적: 6-K + EX-99.1(통합) + EX-99.2(presentation) → HIGH
- TSM 월별 매출: 6-K, attachment 1개, 키워드 'monthend'/'revenue' → NORMAL
- TSM 이사회: 6-K, attachment 1개 → INFO
- 8-K Item 2.02 (US 실적 속보) → HIGH
- 8-K Item 7.01 (Reg FD, IR Day 흔히 여기) → INFO~NORMAL (별도 키워드 검사)
- NT 10-Q/NT 10-K (지연 제출) → CRITICAL
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

Severity = str  # 'CRITICAL' / 'HIGH' / 'NORMAL' / 'INFO'

# EX-99.x attachment의 document_type prefix (edgartools)
EX99_PREFIXES = ('EX-99', 'EX99')

# TSM 월별 매출 식별 키워드
MONTHLY_REVENUE_KEYWORDS = ('monthend', 'monthly revenue', 'revenue 20', 'monthly net revenue')

# IR Day 키워드 (8-K Item 7.01 본문 또는 첨부 제목)
IR_DAY_KEYWORDS = ('investor day', 'analyst day', 'capital markets day', 'investor presentation',
                   'investor briefing')


@dataclass
class ParsedFiling:
    accession_number: str
    form: str                     # '8-K' / '6-K' / 'NT 10-Q' / 'NT 10-K'
    items: tuple[str, ...]        # ('2.02', '7.01') for 8-K
    severity: Severity
    document_subtype: str         # '8-K_EARNINGS' / '6-K_QUARTERLY' / '6-K_MONTHLY' / '8-K_IR_DAY' / 'NT_10' / 'OTHER'
    exhibits: dict[str, str]      # {'EX-99.1': cleaned_text, ...}
    primary_text: str             # 주 본문 (EX-99.1 우선, 없으면 form 본문)
    attachment_count: int = 0
    has_presentation: bool = False
    metadata: dict = field(default_factory=dict)


def _attachment_doctype(att) -> str:
    return (getattr(att, 'document_type', None) or '').upper()


def _attachment_doc(att) -> str:
    return (getattr(att, 'document', None) or str(att) or '').lower()


def _is_ex99(att) -> bool:
    dt = _attachment_doctype(att)
    return any(dt.startswith(p) for p in EX99_PREFIXES)


def _looks_like_presentation(att) -> bool:
    dt = _attachment_doctype(att)
    doc = _attachment_doc(att)
    return dt in ('EX-99.2', 'EX99.2') or 'presentation' in doc or 'slides' in doc


def _looks_like_monthly_revenue(att) -> bool:
    doc = _attachment_doc(att)
    return any(k in doc for k in MONTHLY_REVENUE_KEYWORDS)


def _attachment_text(att) -> str:
    """edgartools Attachment에서 본문 텍스트 추출. HTML이면 태그 제거."""
    try:
        # edgartools v5 attachment.text() 또는 .markdown()
        if hasattr(att, 'text'):
            t = att.text()
            if t:
                return t
        if hasattr(att, 'markdown'):
            t = att.markdown()
            if t:
                return t
        # fallback: download raw + 단순 HTML 제거
        if hasattr(att, 'download'):
            raw = att.download()
            if isinstance(raw, bytes):
                raw = raw.decode('utf-8', errors='ignore')
            return _strip_html(raw)
    except Exception:
        pass
    return ''


def _strip_html(html: str) -> str:
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _classify_8k(items: tuple[str, ...], primary_text: str) -> tuple[Severity, str]:
    if '2.02' in items:
        return 'HIGH', '8-K_EARNINGS'
    if '7.01' in items:
        # IR Day 흔히 여기. 키워드 매칭으로 등급 분리
        text_lower = primary_text.lower()[:5000]
        if any(k in text_lower for k in IR_DAY_KEYWORDS):
            return 'NORMAL', '8-K_IR_DAY'
        return 'INFO', '8-K_REG_FD'
    return 'INFO', '8-K_OTHER'


def _classify_6k(exhibits: dict[str, str], attachments_meta: list[dict]) -> tuple[Severity, str]:
    """6-K는 items 없음 → 첨부 패턴으로 분류."""
    ex99_count = sum(1 for k in exhibits if k.startswith('EX-99'))
    if ex99_count >= 2:
        # 분기 실적 패턴 (ASML/TSM 모두 EX-99.1 + EX-99.2 이상)
        return 'HIGH', '6-K_QUARTERLY'
    if ex99_count == 1:
        # EX-99.1만 있음 — 분기 실적일 수도 있고 다른 발표일 수도. 본문 텍스트 길이로 추정
        first_text = next(iter(exhibits.values()), '')
        if len(first_text) > 3000:
            return 'HIGH', '6-K_QUARTERLY'
        return 'NORMAL', '6-K_OTHER'
    # 첨부 EX-99.x 없음
    if any(meta.get('is_monthly_revenue') for meta in attachments_meta):
        return 'NORMAL', '6-K_MONTHLY'
    return 'INFO', '6-K_OTHER'


def parse_filing(filing) -> ParsedFiling:
    """edgartools Filing 객체를 받아 분류 + 첨부 텍스트 추출."""
    form = (getattr(filing, 'form', '') or '').upper()
    accession = getattr(filing, 'accession_no', None) or getattr(filing, 'accession_number', '')
    items = tuple(getattr(filing, 'items', ()) or ())

    # NT 10-Q/K 우선 처리 (지연 제출 → 즉시 CRITICAL)
    if form in ('NT 10-Q', 'NT 10-K', 'NT-10-Q', 'NT-10-K'):
        return ParsedFiling(
            accession_number=accession,
            form=form,
            items=items,
            severity='CRITICAL',
            document_subtype='NT_10',
            exhibits={},
            primary_text=_strip_html(str(getattr(filing, 'text', lambda: '')() or '')),
            attachment_count=0,
        )

    # 첨부 추출
    exhibits: dict[str, str] = {}
    attachments_meta: list[dict] = []
    has_presentation = False

    try:
        atts = list(filing.attachments)
    except Exception:
        atts = []

    for att in atts:
        meta = {
            'document_type': _attachment_doctype(att),
            'document': _attachment_doc(att),
            'is_monthly_revenue': _looks_like_monthly_revenue(att),
        }
        attachments_meta.append(meta)

        if _is_ex99(att):
            key = _attachment_doctype(att)  # 'EX-99.1' 등 그대로
            text = _attachment_text(att)
            if text:
                exhibits[key] = text
            if _looks_like_presentation(att):
                has_presentation = True

    # 주 본문 결정
    if 'EX-99.1' in exhibits:
        primary_text = exhibits['EX-99.1']
    elif exhibits:
        primary_text = next(iter(exhibits.values()))
    else:
        # form 본문 fallback
        try:
            primary_text = filing.text()
        except Exception:
            primary_text = ''
        primary_text = _strip_html(primary_text or '')

    # 분류
    if form == '8-K':
        severity, subtype = _classify_8k(items, primary_text)
    elif form == '6-K':
        severity, subtype = _classify_6k(exhibits, attachments_meta)
    else:
        severity, subtype = 'INFO', 'OTHER'

    return ParsedFiling(
        accession_number=accession,
        form=form,
        items=items,
        severity=severity,
        document_subtype=subtype,
        exhibits=exhibits,
        primary_text=primary_text,
        attachment_count=len(atts),
        has_presentation=has_presentation,
        metadata={'attachments': attachments_meta[:20]},  # raw 아카이브용 메타 일부
    )
