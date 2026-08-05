# -*- coding: utf-8 -*-
"""미국 ISM 서베이 8종 수집 → dataset.csv

제조업 4종(헤드라인·신규주문·고용·가격) + 서비스업 4종(헤드라인·기업활동·신규주문·가격).
전부 확산지수(50 기준). dtype = ISM_MACRO.

## ★원천 — investing 이벤트차트 외에는 전부 막혀 있다 (2026-08-05 전수 실측)
- **FRED**: ISM이 2016년 재배포 라이선스 회수 → `NAPM` 등 삭제(API 400). 검색 0건.
- **DBnomics `ISM/pmi/pm`**: 2025-09부터 값 오염(11.1·10.0 — 실제는 48~49대), 2025-12 정지.
- **ismworld.org**: 전 경로 reCAPTCHA. **ECOS 국제통계**: PMI 미수록.
- **Nasdaq Data Link**: 차단. **EconDB**: 인증 필요.
- **ForexFactory 캘린더 JSON**: `actual` 필드 자체가 없음(실측 0/99). 단 `previous`
  값은 **최신월 교차검증용**으로 유효 — 실제로 제조업 53.3 / 가격 73.0 / 서비스업
  54.0 이 본 수집분과 일치함을 확인했다.
plain urllib/curl 은 403 → **curl_cffi(chrome impersonate) 필수**.

## ★★관측월 배정 = 인덱스 기반 (release stamp 직접 사용 금지)
엔드포인트 timestamp 는 관측월이 아니라 **발표일**이다(ISM은 전월치를 다음 달
첫 영업일에 공표). 그런데 발표가 밀려 **한 달에 두 번 발표되거나 stamp 자체가
어긋난 달**이 있어 `발표월−1` 을 그대로 쓰면 그 구간이 통째로 밀린다.
  예) 제조업 가격(174): 2008-09-02 발표분이 2008-10-01 로 잘못 찍혀 8월/9월 값이 뒤섞임.

→ 배정 규칙:
  first_ref = 첫 발표월 − 1,  last_ref = 마지막 발표월 − 1
  span = first_ref~last_ref 개월 수
  ★ span == 관측 수 일 때만 **i번째 관측 = first_ref + i개월** 로 배정(결측 0 확인).
  불일치하면 결측/중복이 있다는 뜻이므로 **그 시리즈는 쓰지 않고 건너뛴다.**
dataset.csv 스탬프 = 그 관측월의 달력 말일(FRED/ECOS 월별 규약과 동일).

검증: 8종 전부 span==n 통과. 값 앵커도 공표 실적과 일치 —
제조업 2008-12=32.9·2020-04=41.5·2021-03=64.7, 신규주문 2021-03=68.0,
고용 2020-04=27.5, 가격 2008-12=18.0·2021-03=85.6,
서비스업 2020-04=41.8·2021-03=63.7, 기업활동 2020-04=26.0, 서비스 가격 2021-03=74.0.

## ★알려진 원천 결함
- 제조업 가격(174) **2008-07 = 49.9 는 원천 오류**(실제 88.5대). 전후 월과 총 개수는
  정상이라 배정은 안 밀린다. 5년 임베드 창 밖이라 화면에는 안 나온다. 교체 가능한
  대체 원천이 없어 그대로 둔다 — RoC²·datalake 백필에 쓸 때만 유의.

## 가드
- ANCHORS: 시리즈별 실적 앵커 대조 → 하나라도 어긋나면 **그 시리즈 쓰지 않음**.
  ★규약이 뒤집히면 전 계열이 조용히 밀리는데 개수 검사로는 못 잡는다. 앵커가 방어선.
- 값 범위 이탈·span 불일치 시 해당 시리즈 skip. 다른 시리즈는 정상 진행.
- 매 run 전 구간 upsert-heal — ISM은 매년 1월 계절조정계수를 소급 개정한다.

사용:
  venv/bin/python3 execution/fetch_ism_pmi.py
  venv/bin/python3 execution/fetch_ism_pmi.py --dry-run
"""
import calendar
import csv
import os
import sys
import time
from datetime import date, datetime, timezone

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CSV_PATH = 'dataset.csv'
CHART_BASE = 'https://sbcharts.investing.com/events_charts/us/{}.json'
DTYPE = 'ISM_MACRO'
ND = 1
TIMEOUT = 30
SLEEP = 1.2

# event_id: investing economic-calendar 이벤트 번호
# lo/hi: 허용 값 범위 (가격지수는 원자재 급등락으로 18~98 까지 벌어진다)
# anchors: {관측월 말일 ISO: 값} — 공표 실적과 대조 확인된 것만
SERIES = [
    dict(eid=173,  name='ISM 제조업지수',        lo=20, hi=80,
         anchors={'2008-12-31': 32.9, '2020-04-30': 41.5, '2021-03-31': 64.7}),
    dict(eid=1483, name='ISM 제조업 신규주문',   lo=15, hi=85,
         anchors={'2008-12-31': 23.2, '2021-03-31': 68.0}),
    dict(eid=1046, name='ISM 제조업 고용',       lo=15, hi=85,
         anchors={'2020-04-30': 27.5, '2021-03-31': 59.6}),
    dict(eid=174,  name='ISM 제조업 가격',       lo=10, hi=100,
         anchors={'2008-12-31': 18.0, '2021-03-31': 85.6, '2026-06-30': 73.0}),
    dict(eid=176,  name='ISM 서비스업지수',      lo=25, hi=80,
         anchors={'2020-04-30': 41.8, '2021-03-31': 63.7, '2026-06-30': 54.0}),
    dict(eid=1484, name='ISM 서비스업 기업활동', lo=20, hi=85,
         anchors={'2020-04-30': 26.0, '2021-03-31': 69.4}),
    dict(eid=1050, name='ISM 서비스업 신규주문', lo=20, hi=85,
         anchors={'2020-04-30': 32.9, '2021-03-31': 67.2}),
    dict(eid=1049, name='ISM 서비스업 가격',     lo=25, hi=95,
         anchors={'2021-03-31': 74.0, '2026-06-30': 67.7}),
]


class IsmError(Exception):
    pass


def month_end(y, m):
    return date(y, m, calendar.monthrange(y, m)[1])


def add_months(y, m, k):
    m = m + k
    y += (m - 1) // 12
    return y, (m - 1) % 12 + 1


def fmt(v, nd):
    out = f'{v:.{nd}f}'
    if '.' in out:
        out = out.rstrip('0').rstrip('.')
    return '0' if out in ('-0', '') else out


def fetch(eid):
    try:
        from curl_cffi import requests as creq
    except ImportError:
        raise IsmError('curl_cffi 미설치')
    try:
        r = creq.get(CHART_BASE.format(eid), impersonate='chrome', timeout=TIMEOUT)
    except Exception as e:                       # ★URL·응답 본문은 로그에 남기지 않음
        raise IsmError(f'요청 실패: {type(e).__name__}')
    if r.status_code != 200:
        raise IsmError(f'HTTP {r.status_code}')
    try:
        return r.json()
    except Exception:
        raise IsmError('JSON 파싱 실패')


def to_points(payload, spec):
    """attr[] → {관측월 말일: 값}. ★인덱스 기반 배정 (docstring 참조)."""
    rows = payload.get('attr') if isinstance(payload, dict) else None
    if not rows:
        raise IsmError('attr 비어 있음')
    obs = sorted((it for it in rows if it.get('actual') not in (None, '')),
                 key=lambda it: it['timestamp'])
    if not obs:
        raise IsmError('유효 관측 0건')

    def rel_ref(it):
        d = datetime.fromtimestamp(it['timestamp'] / 1000, timezone.utc)
        return add_months(d.year, d.month, -1)

    fy, fm = rel_ref(obs[0])
    ly, lm = rel_ref(obs[-1])
    span = (ly - fy) * 12 + (lm - fm) + 1
    if span != len(obs):
        raise IsmError(f'월 배정 불가: 구간 {span}개월 ≠ 관측 {len(obs)}건 (결측·중복)')

    pts = {}
    for i, it in enumerate(obs):
        try:
            val = float(it['actual'])
        except (TypeError, ValueError):
            raise IsmError(f'{i}번째 관측 값 파싱 실패')
        if not (spec['lo'] <= val <= spec['hi']):
            raise IsmError(f'값 범위 이탈 idx{i} → {val}')
        y, m = add_months(fy, fm, i)
        pts[month_end(y, m)] = val

    for iso, want in spec['anchors'].items():
        got = pts.get(date.fromisoformat(iso))
        if got is None or abs(got - want) > 1e-9:
            raise IsmError(f'앵커 불일치 {iso}: 기대 {want}, 실제 {got} → 규약 변경 의심')
    return pts


def main():
    dry = '--dry-run' in sys.argv
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

    new_rows, healed, ok, failed = [], 0, 0, []

    for si, spec in enumerate(SERIES):
        if si:
            time.sleep(SLEEP)
        name = spec['name']
        try:
            pts = to_points(fetch(spec['eid']), spec)
        except IsmError as e:
            failed.append(name)
            print(f'  ⚠️ {name}: {e}')
            continue

        added = 0
        for stamp in sorted(pts):
            if stamp > today:
                continue
            s = fmt(pts[stamp], ND)
            k = (stamp.isoformat(), name)
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
                row = [k[0], name, s, DTYPE]
                all_rows.append(row)
                index[k] = len(all_rows) - 1
                new_rows.append(row)
                added += 1
        ok += 1
        last = max(pts)
        print(f'  ✓ {name}: {len(pts)}건 ({min(pts)}~{last}), 최신 {fmt(pts[last], ND)}, 신규 {added}')

    print(f'\nISM 수집 완료: {ok}/{len(SERIES)} 성공, 신규 {len(new_rows)}건, 개정 {healed}건'
          + (' [dry-run, 미기록]' if dry else ''))
    if failed:
        print(f'실패 시리즈: {", ".join(failed)}')
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

    return 1 if ok == 0 else 0


if __name__ == '__main__':
    sys.exit(main())
