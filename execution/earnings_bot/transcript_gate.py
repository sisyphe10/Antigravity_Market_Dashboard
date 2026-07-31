"""전문 오매칭·날조 차단 게이트 (2026-07-31 사고 대응).

배경
----
matcher.py 의 5개 점수 항목(회사명/티커/분기표현/날짜/키워드)에는 **"이 문서가 실제 발화
기록인가"를 재는 항목이 없다.** 가이던스 예고 기사는 정의상 회사명·티커·분기표현을 모두
포함하므로 제목만으로 0.80 을 얻어 임계값 0.70 을 통과했다. 그 결과:

  - 기사/요약페이지가 전문으로 수집됨 (22건 발행)
  - 번역 프롬프트에 "전문이 아닐 때" 지시가 없어, 같은 입력에서 어떤 건 거부하고
    어떤 건 **CEO 발언을 날조**했다 (IBM id=134)
  - 소스가 올해 전문을 아직 안 올렸을 때 **작년 같은 분기 전문**이 수집됨 (11건)

이 모듈은 점수(soft)가 아니라 **하드 veto** 다. 통과 못 하면 수집·번역·발행 어느 단계든
진행하지 않는다. "못 구한 것"은 빈칸으로 남지만 "만들어낸 것"은 남기지 않는다.

임계값 근거 (2026-07-31 실측, transcripts 199건)
-----------------------------------------------
  정상 153건 원문 길이 최솟값      21,237자
  의심 46건 중 41건                14,816자 이하
  → MIN_RAW_CHARS=18000 이면 정상 오탐 0건 / 의심 89% 차단

  ★ "prepared 또는 qa 가 0이면 불량" 규칙은 쓰지 않는다 —
    정상 153건 중 24건(16%)이 qa=0 이다 (소스가 Prepared 만 확보하는 경우).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── 임계값 ────────────────────────────────────────────────────────
MIN_RAW_CHARS = 18_000
URL_BLOCKLIST = ('instant-alerts/',)
URL_DATE_TOLERANCE_DAYS = 25
VINTAGE_TOLERANCE_MONTHS = 4          # 본문/URL 연월이 공시월과 이만큼 벌어지면 다른 분기
MIN_TRANSLATION_RATIO = 0.25          # 한국어 길이 / 원문 길이
SENTINEL = 'NOT_A_TRANSCRIPT'

REFUSAL_MARKERS = (
    '포함되어 있지 않습니다', '죄송하지만', '제공해주시면', '원문을 제공',
    '포함하지 않습니다', '본문 미제공', '전문이 아닙니다',
)

_MONTHS = ('january february march april may june july august september '
           'october november december').split()
_MONTH_IDX = {m: i + 1 for i, m in enumerate(_MONTHS)}

_RE_BODY_DATE = re.compile(r'\b(%s)\s+(\d{1,2}),?\s+(20\d{2})\b' % '|'.join(_MONTHS), re.I)
_RE_URL_DATE = re.compile(r'/(20\d{2})-(\d{1,2})-(\d{1,2})')
_RE_URL_QY = re.compile(r'q[1-4][-_/](20\d{2})', re.I)
_RE_URL_YMD = re.compile(r'/(20\d{2})/(\d{2})/(\d{2})/')
_RE_OPERATOR = re.compile(r'\bOperator\b')
_RE_SPEAKER_COLON = re.compile(r'(?:^|\n)\s*([A-Z][A-Za-z.\'-]+(?:\s+[A-Z][A-Za-z.\'-]+){0,3})\s*:')
_RE_QA_HEADER = re.compile(r'question[- ]and[- ]answer|questions?\s+and\s+answers?', re.I)
# 전문 특유의 발화 관용구 — 보도자료/IR 슬라이드에는 거의 나오지 않는다.
#   실측: SYK/PYPL 보도자료·IONQ 슬라이드 = 0~1종 / ADBE 실제 전문(Q&A 없이 잘린 것) = 2종 이상
_RE_CALL_PHRASE = re.compile(
    r'turn the call over|turn it over to|thank you for joining|thanks for joining|'
    r'ladies and gentlemen|prepared remarks|opening remarks|our first question|'
    r'next question comes from|you may (?:now )?disconnect|this concludes', re.I)
# 번역본 화자 헤더:  **Satya Nadella - 최고경영자**
_RE_KR_SPEAKER = re.compile(r'\*\*\s*([A-Z][A-Za-z.\'-]+(?:\s+[A-Z][A-Za-z.\'-]+){0,3})\s*[-–—]')
_RE_QUOTE_CTX = re.compile(r'["“”‘’]|\b(said|says|noted|stated|added|'
                           r'according to|commented|explained|continued)\b', re.I)


def _months(y: int, m: int) -> int:
    return y * 12 + m


def _daynum(y: int, m: int, d: int) -> int:
    return y * 372 + m * 31 + d


@dataclass
class GateResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    info: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.ok


def _fail(reasons, info=None) -> GateResult:
    return GateResult(ok=not reasons, reasons=reasons, info=info or {})


# ── L1: 소스 URL ──────────────────────────────────────────────────
def check_source(url: str, filed_at: str) -> GateResult:
    """URL 만으로 판정 가능한 것 — 기사 블랙리스트 + URL 에 박힌 날짜/분기."""
    url = (url or '')
    low = url.lower()
    reasons = []
    for bad in URL_BLOCKLIST:
        if bad in low:
            reasons.append(f'url_blocklist:{bad}')
    if not filed_at:
        return _fail(reasons)
    fy, fm, fd = int(filed_at[:4]), int(filed_at[5:7]), int(filed_at[8:10])

    m = _RE_URL_DATE.search(url) or _RE_URL_YMD.search(url)
    if m:
        uy, um, ud = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if abs(_daynum(uy, um, ud) - _daynum(fy, fm, fd)) > URL_DATE_TOLERANCE_DAYS:
            reasons.append(f'url_date_mismatch:{uy}-{um:02d}-{ud:02d}')
    for qm in _RE_URL_QY.finditer(low):
        qy = int(qm.group(1))
        if abs(qy - fy) >= 1 and qy < fy:
            reasons.append(f'url_quarter_year_stale:{qy}')
            break
    return _fail(reasons)


# ── L2: 본문 ──────────────────────────────────────────────────────
def check_body(prepared: str, qa: str, filed_at: str) -> GateResult:
    """길이 / vintage(작년 전문) / 발화 구조."""
    prepared, qa = prepared or '', qa or ''
    body = prepared + '\n' + qa
    raw = len(prepared) + len(qa)
    reasons: list[str] = []
    info = {'raw_chars': raw}

    if raw < MIN_RAW_CHARS:
        reasons.append(f'raw_too_short:{raw}')

    # vintage — 본문 앞부분의 명시 날짜가 공시월과 크게 어긋나면 다른 분기 콜
    if filed_at:
        fy, fm = int(filed_at[:4]), int(filed_at[5:7])
        diffs = []
        for m in _RE_BODY_DATE.finditer(body[:1500]):
            mo = _MONTH_IDX[m.group(1).lower()]
            yr = int(m.group(3))
            diffs.append((abs(_months(yr, mo) - _months(fy, fm)),
                          f'{m.group(1)} {m.group(2)}, {yr}'))
        if diffs:
            best, label = min(diffs)
            info['body_date'] = label
            info['body_date_diff_months'] = best
            if best >= VINTAGE_TOLERANCE_MONTHS:
                reasons.append(f'vintage_mismatch:{label}({best}m)')

    # 발화 구조 — OR 조합 (정상이라도 Operator 0 인 소스가 있음)
    n_op = len(_RE_OPERATOR.findall(body))
    n_sp = len(_RE_SPEAKER_COLON.findall(body))
    qa_hdr = bool(_RE_QA_HEADER.search(body))
    n_ph = len({m.group(0).lower() for m in _RE_CALL_PHRASE.finditer(body)})
    info.update(operator=n_op, speaker_colon=n_sp, qa_header=qa_hdr, call_phrases=n_ph)
    if not (qa_hdr or n_op >= 3 or n_sp >= 8 or n_ph >= 2):
        reasons.append(f'no_speech_structure(op={n_op},sp={n_sp},qa={qa_hdr},ph={n_ph})')

    return _fail(reasons, info)


# ── L4: 번역 결과 ─────────────────────────────────────────────────
def check_translation(raw_text: str, translated_kr: str) -> GateResult:
    """sentinel / 거부문구 / 분량비율 / 화자 귀속."""
    raw_text = raw_text or ''
    kr = translated_kr or ''
    reasons: list[str] = []
    info = {'kr_chars': len(kr), 'raw_chars': len(raw_text)}

    if SENTINEL in kr[:400]:
        return _fail([f'sentinel:{SENTINEL}'], info)
    head = kr[:1500]
    for mk in REFUSAL_MARKERS:
        if mk in head:
            reasons.append(f'refusal_marker:{mk}')
            break
    if raw_text:
        ratio = len(kr) / len(raw_text)
        info['ratio'] = round(ratio, 3)
        if ratio < MIN_TRANSLATION_RATIO:
            reasons.append(f'translation_ratio_low:{ratio:.2f}')

    sp = check_speaker_attribution(raw_text, kr)
    if not sp.ok:
        reasons.extend(sp.reasons)
    info.update(sp.info)
    return _fail(reasons, info)


def check_speaker_attribution(raw_text: str, translated_kr: str) -> GateResult:
    """번역본 화자 헤더의 인물이 원문에서 '실제로 말했는지' 확인.

    ★ 이름 존재 여부만 보면 안 된다 — IBM 날조 케이스에서 "Arvind Krishna" 는 원문(기사)에
      3번 나오지만 전부 "praising CEO Arvind Krishna's execution" 같은 3인칭 서술이었다.
      이름 등장 지점 주변에 발화 근거(`이름:` 패턴 또는 인용부호/발화동사)가 있어야 한다.

    번역 프롬프트 규칙상 임원 이름은 영문 그대로 출력되므로 음차 문제는 없다.
    """
    raw_text = raw_text or ''
    kr = translated_kr or ''
    names = []
    for m in _RE_KR_SPEAKER.finditer(kr):
        n = m.group(1).strip()
        if n and n.lower() not in ('operator',) and n not in names:
            names.append(n)
    info = {'kr_speakers': names[:8], 'kr_speaker_count': len(names)}
    if not names:
        return _fail([], info)          # 화자 헤더가 없으면 이 검사는 판단 보류

    attributed = 0
    unattributed = []
    for n in names:
        ok = False
        for m in re.finditer(re.escape(n), raw_text):
            after = raw_text[m.end():m.end() + 3]
            if after.lstrip().startswith(':'):
                ok = True
                break
            win = raw_text[max(0, m.start() - 150):m.end() + 150]
            if _RE_QUOTE_CTX.search(win):
                ok = True
                break
        if ok:
            attributed += 1
        else:
            unattributed.append(n)
    info['attributed'] = attributed
    info['unattributed'] = unattributed[:5]
    # 한 명도 발화 근거가 없으면 = 원문에 발언이 존재하지 않음 → 날조
    if attributed == 0:
        return _fail([f'no_speaker_attribution:{",".join(names[:3])}'], info)
    return _fail([], info)


# ── 통합 ──────────────────────────────────────────────────────────
def check_collect(url: str, prepared: str, qa: str, filed_at: str) -> GateResult:
    """수집(insert) 직전 게이트 = L1 + L2."""
    a = check_source(url, filed_at)
    b = check_body(prepared, qa, filed_at)
    return _fail(a.reasons + b.reasons, {**a.info, **b.info})


def check_publish(url: str, prepared: str, qa: str, filed_at: str,
                  translated_kr: str) -> GateResult:
    """md 발행 직전 최종 게이트 = 수집 게이트 + 번역 검증."""
    c = check_collect(url, prepared, qa, filed_at)
    t = check_translation((prepared or '') + '\n' + (qa or ''), translated_kr)
    return _fail(c.reasons + t.reasons, {**c.info, **t.info})
