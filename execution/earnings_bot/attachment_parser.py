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

# AGM (정기/임시 주주총회) 키워드 (6-K 분류용 — 외국 발행인이 분기실적 외 거버넌스 발표에 사용)
# Codex 보완: shareholders' meeting / annual meeting of shareholders 변형도 포함
AGM_KEYWORDS = (
    'annual general meeting', 'agm', 'shareholders meeting',
    "shareholders' meeting", 'shareholder meeting',
    'annual meeting of shareholders', 'general meeting of shareholders',
)

# 분기 실적 재무 신호 (보도자료 본문). EX-99 첨부가 있어도 이 신호가 없으면 분기실적이
# 아니라 M&A·운영공시 같은 주요사항(6-K_EVENT)으로 분류. 단순 본문 길이만으론 비-실적
# 보도자료가 분기실적으로 오분류됨 (CCJ Cigar Lake 지분인수·McArthur 홍수 6-K 사례).
EARNINGS_SIGNAL_KEYWORDS = (
    'net earnings', 'net income', 'net loss', 'net sales',
    'earnings per share', 'per share', 'diluted',
    'gross profit', 'gross margin', 'operating income', 'operating margin',
    'adjusted ebitda', 'adjusted net', 'results of operations',
    'three months ended', 'six months ended', 'nine months ended', 'quarter ended',
    'total revenue', 'revenue of', 'revenues of', 'net revenue',
)

# ★2026-07-15: 자사주매입 정형공시 네거티브 가드 (홍콩거래소 FF305 등).
# BABA 'Next Day Disclosure Return'(매입 단가 per share 표 포함)이 EARNINGS_SIGNAL에 걸려
# 6-K_QUARTERLY/HIGH 오분류 + transcript 잡 생성된 사고. 실적 보도자료가 자사주매입을
# '언급'하는 것과 달리 아래 문구는 정형 반환서식 제목이라 실적 문서에 등장하지 않음.
BUYBACK_FORM_KEYWORDS = (
    'next day disclosure return',
    'monthly return of equity issuer',
)

# 8-K item 번호 정규식 (예: "Item 2.02", "2.02,9.01", "2.02 / 9.01")
ITEM_RE = re.compile(r'(?:Item\s*)?(\d\.\d{2})', flags=re.IGNORECASE)


@dataclass
class ParsedFiling:
    accession_number: str
    form: str                     # '8-K' / '6-K' / 'NT 10-Q' / 'NT 10-K'
    items: tuple[str, ...]        # ('2.02', '7.01') for 8-K
    severity: Severity
    document_subtype: str         # '8-K_EARNINGS' / '6-K_QUARTERLY' / '6-K_MONTHLY' / '6-K_EVENT' / '8-K_IR_DAY' / 'NT_10' / 'OTHER'
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


def _normalize_items(raw) -> tuple[str, ...]:
    """edgartools Filing/EightK item 표현을 ('2.02', '9.01')로 정규화.

    edgartools v5는 items를 string("2.02,9.01"), list, tuple 등 여러 형태로 노출.
    str/iterable 모두 받아 ITEM_RE로 추출하고 중복 제거.
    """
    if raw is None:
        return ()
    if isinstance(raw, str):
        values = re.split(r'[,;]\s*', raw)
    else:
        try:
            values = list(raw)
        except TypeError:
            values = [raw]

    items: list[str] = []
    for value in values:
        for m in ITEM_RE.finditer(str(value)):
            code = m.group(1)
            if code not in items:
                items.append(code)
    return tuple(items)


def _extract_items(filing, form: str) -> tuple[str, ...]:
    """3단 폴백 — Filing.items → Filing.obj().items/item_numbers/item_codes → filing.text() 본문."""
    items = _normalize_items(getattr(filing, 'items', None))
    if items or form != '8-K':
        return items

    try:
        obj = filing.obj()
    except Exception:
        obj = None
    if obj is not None:
        for attr in ('items', 'item_numbers', 'item_codes'):
            items = _normalize_items(getattr(obj, attr, None))
            if items:
                return items

    try:
        return _normalize_items((filing.text() or '')[:5000])
    except Exception:
        return ()


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
    """6-K는 items 없음 → 첨부 패턴 + 본문 내용으로 분류.

    실측 발견:
    - ASML 2026-04-15: 분기실적 보도자료에도 AGM 안내 문구 포함.
    - CCJ 2026: Cigar Lake 지분인수·McArthur 홍수 6-K가 단일 EX-99.1 + 긴 본문이라
      구(舊) 길이-기반 규칙에서 분기실적으로 오분류됨 → "실적" 제목 + transcript 시도.

    핵심: 분기실적 판정은 **본문 재무 실적 신호(EARNINGS_SIGNAL_KEYWORDS)** 를 요구.
    EX-99 첨부가 있어도 실적 신호가 없으면 M&A·운영공시 = 6-K_EVENT (컨퍼런스콜 없음).

    분류 순서:
    1) 월별 매출 키워드 ('revenue'가 실적신호와 겹치므로 먼저 분기)
    2) EX-99 + 실적 재무 신호 → 분기실적 (단일/다중 무관)
    3) AGM 키워드 → AGM
    4) EX-99 보도자료지만 실적 신호 없음 → 6-K_EVENT (긴 본문) / 6-K_OTHER (짧음)
    5) EX-99 없음 → OTHER
    """
    meta_text = ' '.join(str(meta.get('document', '')) for meta in attachments_meta).lower()
    body_text = ' '.join(text[:8000] for text in exhibits.values()).lower()
    ex99_count = sum(1 for k in exhibits if k.startswith('EX-99'))
    has_earnings = any(k in body_text for k in EARNINGS_SIGNAL_KEYWORDS)

    # 1) 월별 매출 (가장 구체적 — 'revenue'가 실적신호와 겹치므로 먼저 처리)
    if any(meta.get('is_monthly_revenue') for meta in attachments_meta):
        return 'NORMAL', '6-K_MONTHLY'

    # 1.5) 자사주매입 정형공시 (HK FF305 Next Day Disclosure Return 등) — 매입단가
    #      'per share' 표가 실적신호에 걸리므로 분기실적 판정보다 먼저 EVENT로 분기.
    if any(k in body_text for k in BUYBACK_FORM_KEYWORDS):
        return 'NORMAL', '6-K_EVENT'

    # 2) 분기 실적 = EX-99 첨부 + 본문 재무 실적 신호. ASML(다중)·TSM/Cameco(단일) 모두 해당.
    if ex99_count >= 1 and has_earnings:
        return 'HIGH', '6-K_QUARTERLY'

    # 3) AGM — 첨부 파일명 또는 본문 키워드.
    agm_in_filename = any(k in meta_text for k in AGM_KEYWORDS)
    agm_in_body = any(k in body_text for k in AGM_KEYWORDS)
    if agm_in_filename or agm_in_body:
        return 'INFO', '6-K_AGM'

    # 4) 실적 신호 없는 EX-99 보도자료 = 주요사항(M&A/자산인수/운영) 이벤트.
    #    실적이 아니므로 컨퍼런스콜·transcript 없음 → NORMAL + 별도 타입.
    if ex99_count >= 1:
        longest = max((len(t) for t in exhibits.values()), default=0)
        if longest > 1500:
            return 'NORMAL', '6-K_EVENT'
        return 'NORMAL', '6-K_OTHER'

    # 5) EX-99 첨부 없음
    return 'INFO', '6-K_OTHER'


def parse_filing(filing) -> ParsedFiling:
    """edgartools Filing 객체를 받아 분류 + 첨부 텍스트 추출."""
    form = (getattr(filing, 'form', '') or '').upper()
    accession = getattr(filing, 'accession_no', None) or getattr(filing, 'accession_number', '')
    items = _extract_items(filing, form)

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
