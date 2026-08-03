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
# 2026-08-03 승격: 분할기 v1.1로 오염을 걷어낸 건강 표본(n=40, 분할 불변·번역 존재)
# 실측 = min 0.284 / p10 0.411 / 중앙 0.472 / p90 0.545 / max 0.602.
# CCJ 사고에서 0.19가 '경고만 내고 발행'된 것이 사용자 노출 원인 → 하드 승격.
# (구 기준 주석 "정상 106건 최저 0.134"는 오염 시대 표본 — 그 0.134들이 바로 오염이었다)
MIN_TRANSLATION_RATIO = 0.25          # 한국어 길이 / 원문 길이 (하드 차단)
WARN_TRANSLATION_RATIO = 0.40         # 이하면 경고 + 구조 검사 필수 구간
MAX_TRANSLATION_RATIO = 0.85          # 초과 시 하드 차단 (날조·중복 팽창 신호, 건강 max 0.602)
# 섹션별 비율 하한 — 전체 비율은 한 섹션의 탈락을 긴 다른 섹션이 가릴 수 있다
MIN_SECTION_RATIO = 0.20
# 결정적 섹션 헤더 (translator가 코드로 조립 — 모델 출력 변형 무관)
PREP_HEADER = '## 경영진 발표'
QA_HEADER = '## Q&A (애널리스트 질의응답)'
MIN_PREPARED_FOR_HEADER = 1_500       # translator.MIN_PREPARED_CHARS와 동일해야 함
# 숫자 정합성 — 자릿수 이동 보정 후 실측(살아있는 95건):
#   중앙 0% / 90분위 0% / 95분위 3.6% / 최대 32%
#   상위 2건(RGTI 32%, CEG 32%)은 발표 섹션이 통째로 날조된 것으로 실물 확인됨.
NUMERIC_MIN_SAMPLE = 10               # 번역본 수치가 이보다 적으면 판단 보류
NUMERIC_ORPHAN_WARN = 0.05
NUMERIC_ORPHAN_REJECT = 0.20
SENTINEL = 'NOT_A_TRANSCRIPT'

REFUSAL_MARKERS = (
    '포함되어 있지 않습니다', '죄송하지만', '제공해주시면', '원문을 제공',
    '포함하지 않습니다', '본문 미제공', '전문이 아닙니다',
    # 영어 거부문 (2026-08-03 UMAC 실사고: 정크 청크에 모델이 영어로 거부 →
    # 한국어 마커만으로는 미검출, md 꼬리로 유출)
    'please paste', 'Please provide the actual', 'I cannot translate',
    "I'm unable to translate", 'not a transcript translation',
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
# 화자 라인 뒤에 붙는 직함 — 로스터형("Name\nChief Executive Officer") 판별용
_RE_PCT_NUM = re.compile(r'(\d{1,3}(?:\.\d+)?)\s?%')
_RE_DEC_NUM = re.compile(r'(\d{1,3}(?:,\d{3})*\.\d+)')
_RE_ANY_NUM = re.compile(r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?)')   # 원문 대조용(정수 포함)
_RE_TITLE_WORD = re.compile(
    r'\s*(?:Chief|Chairman|President|Founder|Head of|Executive|Senior|Vice|Managing|'
    r'Director|Officer|CEO|CFO|COO|CTO|EVP|SVP|VP|General Manager|Treasurer|'
    r'Analyst|Investor Relations|Corporate|Interim|Co-)', re.I)


def _months(y: int, m: int) -> int:
    return y * 12 + m


def _daynum(y: int, m: int, d: int) -> int:
    return y * 372 + m * 31 + d


@dataclass
class GateResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)     # 하드 차단 사유
    warnings: list[str] = field(default_factory=list)    # 기록만 (차단 아님)
    info: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.ok


def _fail(reasons, info=None, warnings=None) -> GateResult:
    return GateResult(ok=not reasons, reasons=reasons,
                      warnings=warnings or [], info=info or {})


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


# ── L4b: 섹션 구조 정합 (2026-08-03 신설) ─────────────────────────
def check_structure(prepared: str, qa: str, translated_kr: str) -> GateResult:
    """번역본의 섹션 구조가 원문 분할과 정합하는지 검사.

    CCJ 2Q26 사고 유형(발표부가 번역에서 통째로 탈락했는데 전체 비율 경고만 내고
    발행)의 직접 검출기. translator가 헤더를 코드로 조립하므로(canonical),
    헤더는 정확 문자열·정확 횟수·순서까지 요구한다.
    """
    import re as _re
    prepared = (prepared or '').strip()
    qa = (qa or '').strip()
    kr = translated_kr or ''
    reasons: list[str] = []
    warnings: list[str] = []
    info: dict = {}

    prep_hits = [m.start() for m in _re.finditer(
        r'^' + _re.escape(PREP_HEADER) + r'[ \t]*$', kr, _re.MULTILINE)]
    qa_hits = [m.start() for m in _re.finditer(
        r'^' + _re.escape(QA_HEADER) + r'[ \t]*$', kr, _re.MULTILINE)]
    info['prep_headers'] = len(prep_hits)
    info['qa_headers'] = len(qa_hits)

    if qa:
        if len(qa_hits) != 1:
            reasons.append(f'qa_header_count:{len(qa_hits)}')
    elif qa_hits:
        reasons.append('qa_header_hallucinated')  # 원문 Q&A 없는데 헤더 생성

    if len(prepared) >= MIN_PREPARED_FOR_HEADER:
        if len(prep_hits) != 1:
            reasons.append(f'prep_header_count:{len(prep_hits)}')
    elif prep_hits and not prepared:
        reasons.append('prep_header_hallucinated')

    if prep_hits and qa_hits and prep_hits[0] > qa_hits[0]:
        reasons.append('section_order_inverted')

    # 섹션별 분량 비율 — 헤더가 정상일 때만 산출 가능
    if len(prep_hits) == 1 and len(qa_hits) == 1 and prep_hits[0] < qa_hits[0]:
        prep_kr = kr[prep_hits[0] + len(PREP_HEADER):qa_hits[0]]
        qa_kr = kr[qa_hits[0] + len(QA_HEADER):]
        if prepared:
            rp = len(prep_kr.strip()) / len(prepared)
            info['prep_ratio'] = round(rp, 3)
            if rp < MIN_SECTION_RATIO:
                reasons.append(f'prep_section_ratio_low:{rp:.2f}')
        if qa:
            rq = len(qa_kr.strip()) / len(qa)
            info['qa_ratio'] = round(rq, 3)
            if rq < MIN_SECTION_RATIO:
                reasons.append(f'qa_section_ratio_low:{rq:.2f}')

    return _fail(reasons, info, warnings)


# ── L4: 번역 결과 ─────────────────────────────────────────────────
def check_translation(raw_text: str, translated_kr: str,
                      prepared: str | None = None, qa: str | None = None) -> GateResult:
    """sentinel / 거부문구 / 분량비율 / 화자 귀속."""
    raw_text = raw_text or ''
    kr = translated_kr or ''
    reasons: list[str] = []
    info = {'kr_chars': len(kr), 'raw_chars': len(raw_text)}

    # sentinel 은 '번역 대신 단독 출력'이 규약 — 전체가 사실상 그 한 줄일 때만 거부.
    # 정상 번역 서두에 규칙 언급으로 문자열이 섞이는 경우가 실측됨(5건) → 경고로만.
    if kr.strip().startswith(SENTINEL) and len(kr.strip()) < 1200:
        return _fail([f'sentinel:{SENTINEL}'], info)
    warnings0 = [f'sentinel_mentioned_in_body'] if SENTINEL in kr else []
    warnings: list[str] = list(warnings0)
    ratio = (len(kr) / len(raw_text)) if raw_text else None
    if ratio is not None:
        info['ratio'] = round(ratio, 3)
        if ratio < MIN_TRANSLATION_RATIO:
            reasons.append(f'translation_ratio_low:{ratio:.2f}')
        elif ratio < WARN_TRANSLATION_RATIO:
            warnings.append(f'translation_ratio_thin:{ratio:.2f}')
        if ratio > MAX_TRANSLATION_RATIO:
            reasons.append(f'translation_ratio_high:{ratio:.2f}')

    # 거부문구 — 진짜 거부 출력은 짧거나 얇다. 건강한 분량의 번역 서두에 나오는
    # Safe Harbor 문구("...전망 정보를 포함하지 않습니다" 류)가 걸리는 오탐이
    # 실측됨(2026-08-03 TLN: ratio 0.49·구조 정상인데 하드 차단) → 분량이 정상이면
    # 경고로 강등, 짧거나 얇을 때만 하드 차단.
    # ★머리+꼬리 양쪽 검사 (UMAC 실사고: 마지막 정크 청크의 거부문이 md 꼬리로 유출
    #  — 머리만 보면 놓친다). 꼬리 거부문은 분량 무관 하드 차단.
    head = kr[:1500]
    tail = kr[-1500:]
    for mk in REFUSAL_MARKERS:
        if mk in tail and mk not in head:
            reasons.append(f'refusal_marker_tail:{mk}')
            break
    for mk in REFUSAL_MARKERS:
        if mk in head:
            if len(kr.strip()) < 5000 or (ratio is not None
                                          and ratio < WARN_TRANSLATION_RATIO):
                reasons.append(f'refusal_marker:{mk}')
            else:
                warnings.append(f'refusal_marker_in_healthy_body:{mk}')
            break

    # 섹션 구조 정합 — 호출자가 prepared/qa를 넘기면 검사 (translator·publish 경유)
    if prepared is not None or qa is not None:
        st = check_structure(prepared or '', qa or '', kr)
        reasons.extend(st.reasons)
        warnings.extend(st.warnings)
        info.update(st.info)

    # ★ 화자 귀속은 '경고'다 — 하드 차단이 아니다.
    #   실측: 정상 106건 중 19건(18%)이 화자근거 0%. 원문에 화자 라벨이 아예 없고
    #   IR 인사말("joined today by Elon Musk, ...")만 있는 소스가 흔하기 때문이다.
    #   이걸로 막으면 정상 문서 22%가 사라진다. 대신 md 프론트매터·다이제스트에 남긴다.
    sp = check_speaker_attribution(raw_text, kr)
    if not sp.ok:
        warnings.extend(sp.reasons)
    info.update(sp.info)

    # 숫자 정합성 — 이건 하드 차단이다. 수치 조작은 조용히 투자판단을 망친다.
    nf = check_numeric_fidelity(raw_text, kr)
    reasons.extend(nf.reasons)
    warnings.extend(nf.warnings)
    info.update(nf.info)
    return _fail(reasons, info, warnings)


def _digits(n: str) -> str:
    """자릿수 이동·구분자를 무시한 유효숫자 표현. 1.34 / 134 / 1,340 → '134'."""
    d = n.replace(',', '').replace('.', '').lstrip('0').rstrip('0')
    return d or '0'


def check_numeric_fidelity(raw_text: str, translated_kr: str) -> GateResult:
    """번역본에만 있고 원문에 없는 수치(고아 수치)를 잡는다.

    ★ 방향이 중요하다. "원문 수치가 번역본에 다 남아있는가"는 못 쓴다 —
      단위 환산($19.1 billion → 191억 달러) 때문에 정상 문서 보존율이 33~100% 로
      흩어진다(실측 12건). 반대로 **번역본에만 있는 수치**는 정상 문서에서 거의 0 이다
      (실측: 퍼센트·소수 고아율 중앙 0%, 최대 7%).

      숫자가 조작되면($2.93 → $3.93) 원문에 없는 값이 생기므로 이 방향에서 잡힌다.
      화자 날조보다 조용하고 위험한 유형이라 별도 계층으로 둔다.
    """
    src = (raw_text or '').replace(' ', '')
    kr = (translated_kr or '').replace(' ', '')
    kp = {m.group(1) for m in _RE_PCT_NUM.finditer(kr)}
    sp = {m.group(1) for m in _RE_PCT_NUM.finditer(src)}
    kd = {m.group(1) for m in _RE_DEC_NUM.finditer(kr)}
    sd = {m.group(1) for m in _RE_DEC_NUM.finditer(src)}
    # ★ 단위 환산 보정: 원문 "$134 million" → 번역 "$1.34억" 처럼 자릿수가 이동한다.
    #   보정 없이 보면 정상 문서가 고아 40%대로 잡힌다(ALV·SN 실측).
    #   원문 쪽은 정수까지 모은다 — '$134 million' 은 소수점이 없어 sd 에 안 잡힌다.
    src_digits = {_digits(m.group(1)) for m in _RE_ANY_NUM.finditer(src)}
    orphan = sorted({n for n in (kp - sp) | (kd - sd) if _digits(n) not in src_digits})
    total = len(kp) + len(kd)
    info = {'numeric_total': total, 'numeric_orphan': len(orphan),
            'numeric_orphan_sample': orphan[:6]}
    if total < NUMERIC_MIN_SAMPLE:
        return _fail([], info)          # 표본이 적으면 판단 보류
    rate = len(orphan) / total
    info['numeric_orphan_rate'] = round(rate, 3)
    if rate > NUMERIC_ORPHAN_REJECT:
        return _fail([f'numeric_orphan:{rate:.0%}({",".join(orphan[:4])})'], info)
    if rate > NUMERIC_ORPHAN_WARN:
        return _fail([], info, [f'numeric_orphan_elevated:{rate:.0%}'])
    return _fail([], info)


def check_speaker_attribution(raw_text: str, translated_kr: str) -> GateResult:
    """번역본 화자 헤더의 인물이 원문에서 '화자로' 등장하는지 확인.

    ★ 설계 주의 (2026-07-31 1차 구현 실패에서 배운 것)
      1차 구현은 "이름 주변에 인용부호나 발화동사(said/noted)가 있는가"를 봤다. 이건
      **기사 판별 논리를 전문에 잘못 적용한 것**이다 — 진짜 전문은 전부 직접 발화라
      인용부호가 없다. 실측 결과 GOOGL·TSLA·MU·ADBE·VZ 등 정상 문서가 무더기로 걸렸다.

      올바른 기준은 **화자 라인 등장 여부**다. 전문에서 발화자는 항상 줄머리에
      `Name:` / `Name --` / `Name - 직함` / `Name\\n직함`(로스터형) 형태로 나온다.
      기사에서 언급되는 이름은 문장 한가운데에만 나온다 — 이 차이가 판별점이다.

      IBM 날조 케이스: "praising CEO Arvind Krishna's execution" 처럼 문장 중간에만
      존재 → 화자 라인 0건 → reject.

    ★ 판정: 화자 라인 근거가 있는 이름의 비율이 절반 미만이면 reject.
      "한 명이라도 있으면 통과" 는 진짜 화자 1명 + 날조 3명 조합을 통과시킨다.

    번역 프롬프트 규칙상 임원 이름은 영문 그대로 출력되므로 음차 문제는 없다.
    """
    raw_text = raw_text or ''
    kr = translated_kr or ''
    names = []
    for m in _RE_KR_SPEAKER.finditer(kr):
        n = m.group(1).strip()
        if n and n.lower() not in ('operator', 'analyst') and n not in names:
            names.append(n)
    info = {'kr_speakers': names[:8], 'kr_speaker_count': len(names)}
    if not names:
        return _fail([], info)          # 화자 헤더가 없으면 이 검사는 판단 보류

    attributed, unattributed = 0, []
    for n in names:
        if _is_speaker_line(raw_text, n):
            attributed += 1
        else:
            unattributed.append(n)
    info['attributed'] = attributed
    info['unattributed'] = unattributed[:5]
    if attributed * 2 < len(names):
        return _fail([f'speaker_not_in_source:{",".join(unattributed[:3])}'
                      f'({attributed}/{len(names)})'], info)
    return _fail([], info)


def _is_speaker_line(raw_text: str, name: str) -> bool:
    """원문에서 name 이 '화자 라인'으로 등장하는가."""
    for m in re.finditer(re.escape(name), raw_text):
        # 줄머리(또는 마크업 직후)에서 시작하는가
        prefix = raw_text[max(0, m.start() - 40):m.start()]
        at_line_start = ('\n' in prefix[-3:] or m.start() == 0
                         or prefix.rstrip().endswith(('*', '>', '|', '.', '?')))
        tail = raw_text[m.end():m.end() + 90]
        # Name:  /  Name --  /  Name - 직함  /  Name \n 직함
        if re.match(r'\s*(?::|--|—|–|-\s)', tail):
            return True
        if at_line_start and _RE_TITLE_WORD.match(tail.lstrip('\n\r \t')):
            return True
        if at_line_start and re.match(r'\s*\n\s*\S', tail) and _RE_TITLE_WORD.search(tail[:90]):
            return True
    return False


# ── 통합 ──────────────────────────────────────────────────────────
def check_collect(url: str, prepared: str, qa: str, filed_at: str) -> GateResult:
    """수집(insert) 직전 게이트 = L1 + L2."""
    a = check_source(url, filed_at)
    b = check_body(prepared, qa, filed_at)
    return _fail(a.reasons + b.reasons, {**a.info, **b.info},
                 a.warnings + b.warnings)


def check_publish(url: str, prepared: str, qa: str, filed_at: str,
                  translated_kr: str) -> GateResult:
    """md 발행 직전 최종 게이트 = 수집 게이트 + 번역 검증."""
    c = check_collect(url, prepared, qa, filed_at)
    t = check_translation((prepared or '') + '\n' + (qa or ''), translated_kr,
                          prepared=prepared, qa=qa)
    return _fail(c.reasons + t.reasons, {**c.info, **t.info},
                 c.warnings + t.warnings)
