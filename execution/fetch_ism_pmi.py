# -*- coding: utf-8 -*-
"""미국 ISM 제조업 PMI 수집 → dataset.csv

1종: `미 ISM 제조업지수` (월별, 확산지수 50 기준). dtype = ISM_MACRO.

## 원천 선정 (2026-08-05 전수 실측 — 다른 경로는 전부 사용 불가)
- **FRED 없음**: ISM이 2016년 재배포 라이선스를 회수 → `NAPM`/`NAPMPI` 시리즈는
  삭제됨(API 400 "series does not exist"). search 에도 ISM PMI 계열 0건.
- **DBnomics `ISM/pmi/pm` 사용 금지**: 2025-09 부터 값이 오염(11.1/10.0/10.0/10.3
  — 실제 PMI 는 48~49대)되어 있고 2025-12 에서 갱신이 멈춤. 절대 폴백으로 쓰지 말 것.
- **ismworld.org 직접 스크래핑 불가**: 전 경로 reCAPTCHA 챌린지 반환.
- **ECOS 9.1 주요국제통계**: PMI 계열 미수록. **Nasdaq Data Link**: Incapsula 차단.
- **ForexFactory 캘린더 JSON**: forecast/previous 만 있고 `actual` 이 없음(실측 0/99).
→ investing.com 이벤트 차트 엔드포인트(event 173)만이 **과거 전 이력과 최신치를
  같은 소스에서** 제공. 백필·라이브 소스 혼합 금지 원칙을 지킬 수 있는 유일한 경로.

## 날짜 규약 (★핵심)
엔드포인트의 timestamp 는 **관측월이 아니라 발표일(release date)** 이다.
ISM 은 매월 첫 영업일 10:00 ET 에 **전월치**를 발표하므로
    관측월 = 발표월 − 1개월,  dataset.csv 스탬프 = 그 관측월의 달력 말일
(FRED/ECOS 월별 규약과 동일). 2008-02 이전 구간은 발표시각 기록이 없어
매월 1일 09:00 UTC 로 근사돼 있지만 **발표일 기준인 것은 동일**하다.
검증: 2008-02-01 스탬프=50.7(=2008년 1월 PMI), 2008-03-03=48.3(2월),
2009-01-02=32.9(2008년 12월 금융위기 저점), 2020-05-01=41.5(2020년 4월 코로나 저점),
2021-04-01=64.7(2021년 3월 37년래 고점). 매핑 후 1969-12~2026-07 이 **결측 0의
연속 680개월**로 정확히 맞아떨어진다(중복·공백 0).

## 가드
- ANCHORS: 위 앵커 4건을 매 run 대조 → 하나라도 어긋나면 **쓰지 않고 exit 1**.
  (investing 이 스탬프 규약을 관측월 기준으로 바꾸면 전 계열이 1개월 밀리는데,
   중복·공백 검사로는 잡히지 않는다. 앵커가 유일한 방어선이다.)
- 값 범위 20~80 밖이면 실패(DBnomics 식 파싱 오염 조기 검출).
- 같은 스탬프에 다른 값이 두 번 오면 실패(발표일→관측월 매핑 붕괴 신호).
- 매 run 전 구간 upsert-heal: ISM 은 매년 1월 계절조정계수를 소급 개정한다.

## 접근
plain urllib/curl 은 403 — **curl_cffi(chrome impersonate) 필수**
(fetch_fred_data.py 의 fredgraph 경로와 같은 이유). 미설치면 graceful skip(exit 0).

사용:
  venv/bin/python3 execution/fetch_ism_pmi.py
  venv/bin/python3 execution/fetch_ism_pmi.py --dry-run   # dataset.csv 미변경
"""
import calendar
import csv
import os
import sys
from datetime import date, datetime, timezone

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CSV_PATH = 'dataset.csv'
URL = 'https://sbcharts.investing.com/events_charts/us/173.json'  # ISM Manufacturing PMI
SERIES_NAME = '미 ISM 제조업지수'
DTYPE = 'ISM_MACRO'
ND = 1
TIMEOUT = 30

VALID_LO, VALID_HI = 20.0, 80.0

# (관측월 스탬프, 값) — 규약이 바뀌면 즉시 깨지도록 고정
ANCHORS = {
    '2008-01-31': 50.7,   # 2008년 1월
    '2008-12-31': 32.9,   # 금융위기 저점
    '2020-04-30': 41.5,   # 코로나 저점
    '2021-03-31': 64.7,   # 37년래 고점
}


class IsmError(Exception):
    pass


def month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def fmt(v: float, nd: int) -> str:
    out = f'{v:.{nd}f}'
    if '.' in out:
        out = out.rstrip('0').rstrip('.')
    return '0' if out in ('-0', '') else out


def fetch_payload():
    """curl_cffi 로 이벤트 차트 JSON 취득. 미설치면 None (graceful skip)."""
    try:
        from curl_cffi import requests as creq
    except ImportError:
        return None
    try:
        r = creq.get(URL, impersonate='chrome', timeout=TIMEOUT)
    except Exception as e:                      # ★URL·응답 본문은 로그에 남기지 않음
        raise IsmError(f'요청 실패: {type(e).__name__}')
    if r.status_code != 200:
        raise IsmError(f'HTTP {r.status_code}')
    try:
        return r.json()
    except Exception:
        raise IsmError('JSON 파싱 실패')


def to_points(payload) -> dict:
    """attr[] → {관측월 말일 date: PMI}. 발표일 → 전월 매핑."""
    rows = payload.get('attr') if isinstance(payload, dict) else None
    if not rows:
        raise IsmError('attr 비어 있음')
    pts = {}
    for it in rows:
        ts, v = it.get('timestamp'), it.get('actual')
        if ts is None or v is None or v == '':
            continue
        rel = datetime.fromtimestamp(ts / 1000, timezone.utc)
        y, m = rel.year, rel.month - 1          # 발표월 − 1 = 관측월
        if m == 0:
            y, m = y - 1, 12
        try:
            val = float(v)
        except (TypeError, ValueError):
            continue
        if not (VALID_LO <= val <= VALID_HI):
            raise IsmError(f'값 범위 이탈 {rel:%Y-%m} → {val}')
        stamp = month_end(y, m)
        if stamp in pts and abs(pts[stamp] - val) > 1e-9:
            raise IsmError(f'{stamp} 중복 관측월에 다른 값 ({pts[stamp]} vs {val})')
        pts[stamp] = val
    if not pts:
        raise IsmError('유효 관측 0건')
    return pts


def check(pts: dict) -> None:
    """앵커 + 월 연속성 검사. 어긋나면 쓰지 않는다."""
    for iso, want in ANCHORS.items():
        got = pts.get(date.fromisoformat(iso))
        if got is None or abs(got - want) > 1e-9:
            raise IsmError(f'앵커 불일치 {iso}: 기대 {want}, 실제 {got} '
                           '→ 발표일 규약 변경 의심, 쓰기 중단')
    ks = sorted(pts)
    span = (ks[-1].year - ks[0].year) * 12 + (ks[-1].month - ks[0].month) + 1
    if span != len(ks):
        print(f'  ⚠️ 월 연속성 경고: 구간 {span}개월 / 관측 {len(ks)}건 (결측 존재)')


def main() -> int:
    dry = '--dry-run' in sys.argv

    payload = fetch_payload()
    if payload is None:
        print('curl_cffi 미설치 → skip')
        return 0
    try:
        pts = to_points(payload)
        check(pts)
    except IsmError as e:
        print(f'ISM 수집 실패: {e}')
        return 1

    today = date.today()

    header = ['날짜', '제품명', '가격', '데이터 타입']
    all_rows = []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            h = next(reader, None)
            if h:
                header = h
            all_rows = [row for row in reader if row]

    index = {}
    for i, row in enumerate(all_rows):
        if len(row) >= 2:
            index[(row[0], row[1])] = i

    new_rows, healed = [], 0
    for stamp in sorted(pts):
        if stamp > today:                        # 미래 스탬프 방어 (발표일 구조상 발생 불가)
            continue
        s = fmt(pts[stamp], ND)
        k = (stamp.isoformat(), SERIES_NAME)
        if k in index:
            old = all_rows[index[k]][2]
            if old != s:
                try:
                    same = abs(float(old.replace(',', '')) - float(s)) < 1e-9
                except ValueError:
                    same = False
                if not same:
                    all_rows[index[k]][2] = s
                    healed += 1
        else:
            row = [k[0], SERIES_NAME, s, DTYPE]
            all_rows.append(row)
            index[k] = len(all_rows) - 1
            new_rows.append(row)

    last = max(pts)
    print(f'ISM 제조업 PMI: 관측 {len(pts)}건 ({min(pts)}~{last}), '
          f'최신 {fmt(pts[last], ND)} / 신규 {len(new_rows)}건, 개정 {healed}건'
          + (' [dry-run, 미기록]' if dry else ''))
    if dry:
        return 0

    if healed:
        with open(CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(all_rows)
    elif new_rows:
        write_header = not os.path.exists(CSV_PATH)
        with open(CSV_PATH, 'a', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(header)
            w.writerows(new_rows)
    return 0


if __name__ == '__main__':
    sys.exit(main())
