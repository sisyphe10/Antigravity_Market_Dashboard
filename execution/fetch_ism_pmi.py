# -*- coding: utf-8 -*-
"""미국 ISM 서베이 8종 수집 → dataset.csv

제조업 4종(헤드라인·신규주문·고용·가격) + 서비스업 4종(헤드라인·기업활동·신규주문·가격).
전부 확산지수(50 기준). dtype = ISM_MACRO. 이름에 국가 접두 없음(Country 칼럼이 표시).

## ★원천 — investing 이벤트차트 외에는 전부 막혀 있다 (2026-08-05 전수 실측)
- **FRED**: ISM이 2016년 재배포 라이선스 회수 → `NAPM` 등 삭제(API 400). 검색 0건.
- **DBnomics `ISM/pmi/pm`**: 2025-09부터 값 오염(11.1·10.0 — 실제는 48~49대), 2025-12 정지.
- **ismworld.org**: 전 경로 reCAPTCHA. **ECOS 국제통계**: PMI 미수록.
- **Nasdaq Data Link**: 차단. **EconDB**: 인증 필요.
- **ForexFactory 캘린더 JSON**: `actual` 필드가 없음(실측 0/99). 단 `previous` 는
  **최신월 교차검증용**으로 유효 — 제조업 53.3 / 가격 73.0 / 서비스업 54.0 일치 확인.
plain urllib/curl 은 403 → **curl_cffi(chrome impersonate) 필수**.

## ★★관측월 배정 = 인덱스 기반 (release stamp 직접 사용 금지)
timestamp 는 관측월이 아니라 **발표일**이다(ISM은 전월치를 다음 달 첫 영업일 공표).
그런데 발표 지연·스탬프 오류로 **한 달에 두 번 찍힌 달**이 있어 `발표월−1` 을 그대로
쓰면 그 구간이 밀린다(가격 174: 2008-09-02 발표분이 2008-10-01 로 찍힘).
→ first_ref = 첫 발표월−1, span == 관측수 일 때만 **i번째 관측 = first_ref + i개월**.

### ★span==n 만으로는 부족하다 (2026-08-05 코덱스 지적 반영)
결측 1건과 중복 1건이 서로 상쇄되면 개수가 맞으면서 **그 사이 구간만 통째로 한 달씩
밀린다.** 값 앵커는 듬성듬성해서 앵커 사이 구간이 밀리면 못 잡는다.
→ **드리프트 런 검사** 추가: 각 관측의 (발표월−1) 과 배정된 관측월의 차이를 구하고,
  **0이 아닌 값이 연속으로 이어지는 최대 길이**가 MAX_DRIFT_RUN 을 넘으면 그 시리즈는
  쓰지 않는다. 정상 = 전부 0. 알려진 2008 스탬프 오류 = 런 1(통과). 구간 밀림 = 긴 런(차단).

## ★앵커는 허용오차 방식
ISM 은 **매년 1월 계절조정계수를 소급 개정**하므로 과거 값이 소폭(보통 ≤0.3) 바뀐다.
앵커를 완전일치로 두면 매년 1월에 전 시리즈가 거짓 실패로 멈춘다 → `ANCHOR_TOL` 허용.
한 달 밀림은 값이 이보다 훨씬 크게 벌어지고, 구조적 밀림은 위 드리프트 런이 먼저 잡는다.

## ★알려진 원천 결함
제조업 가격 **2008-07 = 49.9 는 원천 오류**(실제 88.5대, 같은 레코드 forecast 88 과 대조 시 명백).
개수·전후월 정상이라 배정은 안 밀리고 5년 임베드 창 밖이라 화면 미노출. 대체 원천 없음.

## 실패 처리
시리즈 단위로 격리(어떤 예외든 그 시리즈만 skip)하고, **하나라도 실패하면 exit 1**
(dry-run 포함). 러너에서 `|| echo` 로 tolerate 되더라도 종료코드가 감시의 신호가 된다.

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

ANCHOR_TOL = 0.5     # 연례 계절조정 소급 개정 흡수 (실측 개정폭 ≤0.3)
MAX_DRIFT_RUN = 2    # 발표월↔배정월 불일치가 연속 3개월 이상이면 구간 밀림으로 간주

# eid: investing economic-calendar 이벤트 번호 / lo·hi: 허용 값 범위
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


def months_between(a, b):
    """(y,m) 튜플 a → b 개월 수."""
    return (b[0] - a[0]) * 12 + (b[1] - a[1])


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
    """attr[] → {관측월 말일: 값}. 인덱스 기반 배정 + 드리프트 런 검사 + 앵커."""
    rows = payload.get('attr') if isinstance(payload, dict) else None
    if not rows:
        raise IsmError('attr 비어 있음')

    obs = []
    for it in rows:
        if not isinstance(it, dict):
            raise IsmError('attr 원소가 dict 아님 (스키마 변경 의심)')
        ts, v = it.get('timestamp'), it.get('actual')
        if ts is None or v in (None, ''):
            continue
        try:
            obs.append((int(ts), float(v)))
        except (TypeError, ValueError):
            raise IsmError('timestamp/actual 파싱 실패 (스키마 변경 의심)')
    if not obs:
        raise IsmError('유효 관측 0건')
    obs.sort(key=lambda x: x[0])

    def rel_ref(ts):
        d = datetime.fromtimestamp(ts / 1000, timezone.utc)
        return add_months(d.year, d.month, -1)

    first = rel_ref(obs[0][0])
    last = rel_ref(obs[-1][0])
    span = months_between(first, last) + 1
    if span != len(obs):
        raise IsmError(f'월 배정 불가: 구간 {span}개월 ≠ 관측 {len(obs)}건 (결측·중복)')

    # 드리프트 런 — 발표월 기준과 인덱스 배정이 연속으로 어긋나는 최대 길이
    run = worst = 0
    drift_at = []
    pts = {}
    for i, (ts, val) in enumerate(obs):
        assigned = add_months(first[0], first[1], i)
        d = months_between(assigned, rel_ref(ts))
        if d:
            run += 1
            worst = max(worst, run)
            if len(drift_at) < 5:
                drift_at.append('%04d-%02d(%+d)' % (assigned[0], assigned[1], d))
        else:
            run = 0
        if not (spec['lo'] <= val <= spec['hi']):
            raise IsmError(f'값 범위 이탈 {assigned[0]}-{assigned[1]:02d} → {val}')
        pts[month_end(*assigned)] = val

    if worst > MAX_DRIFT_RUN:
        raise IsmError(f'발표월↔배정월 불일치 {worst}개월 연속 (허용 {MAX_DRIFT_RUN}) '
                       f'— 구간 밀림 의심 {", ".join(drift_at)}')
    if drift_at:
        print(f'    · 스탬프 드리프트 {len(drift_at)}건(최대 연속 {worst}): {", ".join(drift_at)}')

    for iso, want in spec['anchors'].items():
        got = pts.get(date.fromisoformat(iso))
        if got is None or abs(got - want) > ANCHOR_TOL:
            raise IsmError(f'앵커 불일치 {iso}: 기대 {want}±{ANCHOR_TOL}, 실제 {got} '
                           '→ 규약 변경 의심')
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
        except Exception as e:      # ★어떤 예외든 그 시리즈만 격리 (스키마 드리프트 포함)
            failed.append(name)
            print(f'  ⚠️ {name}: {type(e).__name__ if not isinstance(e, IsmError) else ""}{e}')
            continue

        added = 0
        for stamp in sorted(pts):
            if stamp > today:       # 미래 스탬프 방어 (발표일 구조상 발생 불가)
                continue
            s = fmt(pts[stamp], ND)
            k = (stamp.isoformat(), name)
            if k in index:
                row = all_rows[index[k]]
                if row[2] != s:
                    try:
                        same = abs(float(row[2].replace(',', '')) - float(s)) < 1e-9
                    except ValueError:
                        same = False
                    if not same:
                        row[2] = s
                        healed += 1
                # dtype 도 치유 (값만 고치면 잘못된 타입 행이 영구히 남아
                #  5년 임베드 창·PNG 제외에서 빠진다)
                while len(row) < 4:
                    row.append('')
                if row[3] != DTYPE:
                    row[3] = DTYPE
                    healed += 1
            else:
                row = [k[0], name, s, DTYPE]
                all_rows.append(row)
                index[k] = len(all_rows) - 1
                new_rows.append(row)
                added += 1
        ok += 1
        shown = [d for d in pts if d <= today]
        last = max(shown) if shown else max(pts)
        print(f'  ✓ {name}: {len(pts)}건 ({min(pts)}~{last}), 최신 {fmt(pts[last], ND)}, 신규 {added}')

    print(f'\nISM 수집: {ok}/{len(SERIES)} 성공, 신규 {len(new_rows)}건, 개정 {healed}건'
          + (' [dry-run, 미기록]' if dry else ''))
    if failed:
        print(f'실패 시리즈: {", ".join(failed)}')

    if not dry:
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

    return 1 if failed else 0     # ★부분 실패도 실패 (dry-run 포함) — 감시 신호


if __name__ == '__main__':
    sys.exit(main())
