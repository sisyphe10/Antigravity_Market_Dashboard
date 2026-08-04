"""
KRX 거래일 판별 — 주말 + 법정공휴일 + 근로자의날(5/1) + 연말휴장(12/31).

★함정: `holidays.KR`은 근로자의날(5/1)·연말휴장(12/31)을 포함하지 않는다.
  둘 다 법정공휴일은 아니지만 KRX는 휴장이므로 명시적으로 더해야 판별이 완전해진다.
  (선거일·대체공휴일은 holidays.KR이 포함한다.)

holidays 미설치 환경에서는 주말만으로 판정하고 경고를 남긴다(fail-open).
가드를 fail-closed 로 두면 라이브러리 사고 하나로 수집 전체가 영구 정지하는데,
fail-open 은 최악이어도 '가드 도입 이전과 동일한 동작'이라 회귀가 아니다.
"""
import logging
from datetime import date, timedelta, timezone

KST = timezone(timedelta(hours=9))

# KRX 휴장이지만 holidays.KR에 없는 날 (월, 일)
EXTRA_CLOSED = ((5, 1), (12, 31))

_HOLIDAY_CACHE = {}
_WARNED = False


def _kr_holidays(year):
    global _WARNED
    if year in _HOLIDAY_CACHE:
        return _HOLIDAY_CACHE[year]
    try:
        import holidays
        _HOLIDAY_CACHE[year] = holidays.KR(years=[year])
    except Exception as e:
        if not _WARNED:
            logging.warning('holidays 로드 실패(%s) — 주말만으로 거래일 판정한다', e)
            _WARNED = True
        _HOLIDAY_CACHE[year] = None
    return _HOLIDAY_CACHE[year]


def as_date(d):
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d)[:10])


def is_session(d):
    """d(‘YYYY-MM-DD’ 또는 date)가 KRX 거래일이면 True."""
    try:
        d = as_date(d)
    except Exception:
        return False
    if d.weekday() >= 5:
        return False
    if (d.month, d.day) in EXTRA_CLOSED:
        return False
    hol = _kr_holidays(d.year)
    if hol is not None and d in hol:
        return False
    return True


def previous_session(d, max_back=15):
    """d 직전(미포함)의 거래일. 못 찾으면 None."""
    d = as_date(d)
    for back in range(1, max_back + 1):
        cand = d - timedelta(days=back)
        if is_session(cand):
            return cand
    return None


def sessions_only(dates):
    """날짜 문자열 iterable에서 거래일만 정렬해 반환."""
    return sorted(s for s in dates if is_session(s))


def today_kst():
    from datetime import datetime
    return datetime.now(tz=KST).date()
