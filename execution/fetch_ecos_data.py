# -*- coding: utf-8 -*-
"""한국은행 ECOS 시계열 수집 → dataset.csv

34종: 일별 금리 6 + 파생 2 (ECOS_RATE), 월별 매크로 14 (ECOS_MACRO),
신용·부동산 11 + 파생 1 (ECOS_SECTOR).

- 키: env ECOS_API_KEY 우선, 없으면 로컬 .secrets 파일 폴백.
  둘 다 없으면 graceful skip (exit 0).
- ★키·URL은 어떤 경우에도 출력 금지 (에러는 타입명/HTTP 코드만).
- ★ECOS 인자 순서: 조회건수(start/end row)가 통계코드보다 먼저 (ERROR-301 함정).
- 증분: 시리즈별 기존 max 날짜 - lookback(D 21일 / M 14개월 / Q 6분기)부터
  재조회 후 (날짜, 제품명) upsert. 값이 개정된 기존 행은 덮어씀(self-heal).
- 날짜 스탬프: D=YYYY-MM-DD(주말 제외), M=달력 말일, Q실적=분기 말일,
  Q전망(대출행태서베이)=분기 첫 달 말일. stamp가 미래면 skip (다음 run 자동 편입).
- 지수형(CPI/PPI/M2/수출)은 원지수를 12개월 선행 fetch 후 전년동월비(%)만 저장.
- HTTP 일시 오류(타임아웃/5xx/429)는 2초 후 1회 재시도, 실패 시 해당 시리즈 skip.
- 키가 있는데 전 시리즈 실패 시에만 exit 1 (부분 실패는 exit 0, 다음 run이 회수).

사용:
  python execution/fetch_ecos_data.py             # 증분 (GHA daily_ecos.yml)
  python execution/fetch_ecos_data.py --backfill  # 레지스트리 backfill 시작일부터 전체
"""
import calendar
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CSV_PATH = 'dataset.csv'
SECRET_FILE = r'C:\Users\user\.secrets\ecos_api_keys.env'
API_BASE = 'https://ecos.bok.or.kr/api'

LOOKBACK_D_DAYS = 21      # 일별: 휴일 공백 + T+1 지연 + 개정 회수
LOOKBACK_M_MONTHS = 14    # 월별: 1~2개월 발표 지연 + 소급 개정 회수
LOOKBACK_Q_QUARTERS = 6   # 분기: 개정 회수
YOY_EXTRA_MONTHS = 12     # YoY 베이스 확보용 선행 fetch

# ---------------------------------------------------------------
# 시리즈 레지스트리 (전 코드 2026-06-10 StatisticItemList/Search 실호출 검증)
# items: StatisticSearch 경로의 ITEM_CODE1[/ITEM_CODE2]
# scale: 저장 전 곱셈 (단위 환산), nd: 반올림 자릿수
# date_rule: Q_END=분기 말일(실적형) / Q_FIRST=분기 첫 달 말일(전망형)
# ---------------------------------------------------------------
SERIES = [
    # ---- 일별 금리 (ECOS_RATE) → 기존 INTEREST RATES 그룹 합류 ----
    dict(name='한국 기준금리',    stat='722Y001', cycle='D', items=('0101000',),   dtype='ECOS_RATE', backfill='20250101', nd=3),
    dict(name='국고채 3년',       stat='817Y002', cycle='D', items=('010200000',), dtype='ECOS_RATE', backfill='20250101', nd=3),
    dict(name='국고채 10년',      stat='817Y002', cycle='D', items=('010210000',), dtype='ECOS_RATE', backfill='20250101', nd=3),
    dict(name='CD 91일',          stat='817Y002', cycle='D', items=('010502000',), dtype='ECOS_RATE', backfill='20250101', nd=3),
    dict(name='CP 91일',          stat='817Y002', cycle='D', items=('010503000',), dtype='ECOS_RATE', backfill='20250101', nd=3),
    dict(name='회사채 3년 AA-',   stat='817Y002', cycle='D', items=('010300000',), dtype='ECOS_RATE', backfill='20250101', nd=3),
    # ---- 월별 매크로 (ECOS_MACRO) → MACRO KOREA ----
    dict(name='CPI 전년동월비',        stat='901Y009', cycle='M', items=('0',),      dtype='ECOS_MACRO', backfill='202101', transform='yoy', nd=2),
    dict(name='PPI 전년동월비',        stat='404Y014', cycle='M', items=('*AA',),    dtype='ECOS_MACRO', backfill='202101', transform='yoy', nd=2),
    dict(name='기대인플레이션 1년',    stat='511Y003', cycle='M', items=('FMB',),    dtype='ECOS_MACRO', backfill='202101', nd=2),
    dict(name='M2 전년동월비',         stat='161Y006', cycle='M', items=('BBHA00',), dtype='ECOS_MACRO', backfill='202101', transform='yoy', nd=2),
    dict(name='BSI 업황실적 (전산업)', stat='512Y013', cycle='M', items=('99988', 'AA'), dtype='ECOS_MACRO', backfill='202101', nd=1),
    dict(name='BSI 업황전망 (전산업)', stat='512Y014', cycle='M', items=('99988', 'BA'), dtype='ECOS_MACRO', backfill='202101', nd=1),
    dict(name='소비자심리지수 CSI',    stat='511Y002', cycle='M', items=('FME', '99988'), dtype='ECOS_MACRO', backfill='202101', nd=1),
    dict(name='경제심리지수 ESI',      stat='513Y001', cycle='M', items=('E2000',),  dtype='ECOS_MACRO', backfill='202101', nd=1),
    dict(name='선행지수 순환변동치',   stat='901Y067', cycle='M', items=('I16E',),   dtype='ECOS_MACRO', backfill='202101', nd=1),
    dict(name='제조업 가동률',         stat='901Y025', cycle='M', items=('I31A',),   dtype='ECOS_MACRO', backfill='202101', nd=1),
    dict(name='수출금액 전년동월비',   stat='901Y118', cycle='M', items=('T002',),   dtype='ECOS_MACRO', backfill='202101', transform='yoy', nd=2),
    dict(name='경상수지',              stat='301Y013', cycle='M', items=('000000',), dtype='ECOS_MACRO', backfill='202101', scale=0.01, nd=1),   # 백만달러→억달러
    dict(name='외환보유액',            stat='732Y001', cycle='M', items=('99',),     dtype='ECOS_MACRO', backfill='202101', scale=1e-5, nd=1),   # 천달러→억달러
    dict(name='정기예금 잔액',         stat='104Y015', cycle='M', items=('BDAA31',), dtype='ECOS_MACRO', backfill='202101', scale=0.001, nd=1),  # 예금은행 말잔, 십억원→조원
    # ---- 신용·부동산 (ECOS_SECTOR) → CREDIT & HOUSING ----
    dict(name='은행 대출금리 (신규취급)',       stat='121Y006', cycle='M', items=('BECBLA01',), dtype='ECOS_SECTOR', backfill='202101', nd=2),
    dict(name='은행 저축성수신금리 (신규취급)', stat='121Y002', cycle='M', items=('BEABAA2',),  dtype='ECOS_SECTOR', backfill='202101', nd=2),
    dict(name='가계대출 잔액',          stat='151Y002', cycle='M', items=('1110000',), dtype='ECOS_SECTOR', backfill='202101', scale=1e-3, nd=1),  # 십억원→조원
    dict(name='가계신용',               stat='151Y001', cycle='Q', items=('1000000',), dtype='ECOS_SECTOR', backfill='2021Q1', scale=1e-3, nd=1, date_rule='Q_END'),
    dict(name='은행 대출태도지수 (종합)', stat='514Y001', cycle='Q', items=('AA',),   dtype='ECOS_SECTOR', backfill='2021Q1', nd=1, date_rule='Q_FIRST'),
    dict(name='은행 신용위험지수 (종합)', stat='514Y002', cycle='Q', items=('BB',),   dtype='ECOS_SECTOR', backfill='2021Q1', nd=1, date_rule='Q_FIRST'),
    dict(name='은행 대출수요지수 (종합)', stat='514Y003', cycle='Q', items=('CC',),   dtype='ECOS_SECTOR', backfill='2021Q1', nd=1, date_rule='Q_FIRST'),
    dict(name='KB 주택매매지수 (전국)',  stat='901Y062', cycle='M', items=('P63A',),   dtype='ECOS_SECTOR', backfill='202101', nd=2),
    dict(name='KB 아파트지수 (서울)',    stat='901Y062', cycle='M', items=('P63ACA',), dtype='ECOS_SECTOR', backfill='202101', nd=2),
    dict(name='아파트 실거래지수 (전국)', stat='901Y089', cycle='M', items=('100',),   dtype='ECOS_SECTOR', backfill='202101', nd=1),
    dict(name='아파트 실거래지수 (서울)', stat='901Y089', cycle='M', items=('200',),   dtype='ECOS_SECTOR', backfill='202101', nd=1),
]

# 파생 시리즈 (API 호출 없음, 양 다리 모두 존재하는 날짜만 = inner join)
DERIVED = [
    dict(name='장단기 스프레드 10Y-3Y', a='국고채 10년', b='국고채 3년', dtype='ECOS_RATE', nd=3),
    dict(name='신용 스프레드 AA-3Y',    a='회사채 3년 AA-', b='국고채 3년', dtype='ECOS_RATE', nd=3),
    dict(name='예대금리차 (신규)',      a='은행 대출금리 (신규취급)', b='은행 저축성수신금리 (신규취급)', dtype='ECOS_SECTOR', nd=2),
]


class EcosError(Exception):
    pass


def load_key() -> str:
    key = os.environ.get('ECOS_API_KEY', '').strip()
    if key:
        return key
    try:
        with open(SECRET_FILE, encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if line.startswith('ECOS_API_KEY'):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ''


def api_fetch(key: str, stat: str, cycle: str, start: str, end: str, items: tuple) -> list:
    """StatisticSearch 호출 → [(TIME, float)] (오름차순). 일시 오류 1회 재시도."""
    path = '/'.join(['StatisticSearch', key, 'json', 'kr', '1', '10000',
                     stat, cycle, start, end] + list(items))
    req = urllib.request.Request(f'{API_BASE}/{path}',
                                 headers={'User-Agent': 'Mozilla/5.0'})
    payload = None
    last_err = ''
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                payload = json.loads(r.read().decode('utf-8'))
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                last_err = f'HTTP {e.code}'
                if attempt == 0:
                    time.sleep(2)
                continue
            raise EcosError(f'HTTP {e.code}') from None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            last_err = type(e).__name__
            if attempt == 0:
                time.sleep(2)
            continue
    if payload is None:
        raise EcosError(f'transient failure after retry ({last_err})')
    if 'RESULT' in payload:
        code = payload['RESULT'].get('CODE', '?')
        if code == 'INFO-200':   # 해당 데이터 없음 = 정상 빈값
            return []
        raise EcosError(f'API {code}')  # 메시지 본문은 출력하지 않음 (키 노출 가드)
    rows = payload.get('StatisticSearch', {}).get('row', [])
    out = []
    for r in rows:
        t, v = r.get('TIME'), r.get('DATA_VALUE')
        if not t or v in (None, ''):
            continue
        try:
            out.append((t, float(str(v).replace(',', ''))))
        except ValueError:
            continue
    return out


# ----------------------------- 날짜 유틸 -----------------------------

def month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def shift_ym(y: int, m: int, delta: int) -> tuple:
    t = y * 12 + (m - 1) + delta
    return t // 12, t % 12 + 1


def stamp_for(time_str: str, cycle: str, date_rule: str) -> date:
    """ECOS TIME → dataset.csv 날짜 스탬프."""
    if cycle == 'D':
        return date(int(time_str[:4]), int(time_str[4:6]), int(time_str[6:8]))
    if cycle == 'M':
        return month_end(int(time_str[:4]), int(time_str[4:6]))
    # Q: 'YYYYQn'
    y = int(time_str[:4])
    q = int(time_str.split('Q')[1])
    if date_rule == 'Q_FIRST':
        return month_end(y, q * 3 - 2)   # 전망형: 분기 첫 달 말일
    return month_end(y, q * 3)           # 실적형: 분기 말일


def ecos_end(cycle: str, today: date) -> str:
    if cycle == 'D':
        return today.strftime('%Y%m%d')
    if cycle == 'M':
        return today.strftime('%Y%m')
    return f'{today.year}Q{(today.month - 1) // 3 + 1}'


def fetch_start(s: dict, max_stamp: date, backfill_mode: bool) -> str:
    """증분 fetch 시작 TIME. 백필 모드/최초 수집이면 backfill(+YoY 선행)."""
    cycle = s['cycle']
    yoy = s.get('transform') == 'yoy'
    if backfill_mode or max_stamp is None:
        start = s['backfill']
        if yoy:
            y, m = shift_ym(int(start[:4]), int(start[4:6]), -YOY_EXTRA_MONTHS)
            start = f'{y:04d}{m:02d}'
        return start
    if cycle == 'D':
        return (max_stamp - timedelta(days=LOOKBACK_D_DAYS)).strftime('%Y%m%d')
    if cycle == 'M':
        back = LOOKBACK_M_MONTHS + (YOY_EXTRA_MONTHS if yoy else 0)
        y, m = shift_ym(max_stamp.year, max_stamp.month, -back)
        return f'{y:04d}{m:02d}'
    q = (max_stamp.month - 1) // 3 + 1 - LOOKBACK_Q_QUARTERS
    y = max_stamp.year
    while q <= 0:
        q += 4
        y -= 1
    return f'{y}Q{q}'


def floor_stamp(s: dict) -> date:
    """backfill 시작일보다 과거 행은 저장하지 않는 하한."""
    cycle, bf = s['cycle'], s['backfill']
    if cycle == 'D':
        return date(int(bf[:4]), int(bf[4:6]), int(bf[6:8]))
    return stamp_for(bf, cycle, s.get('date_rule', ''))


def fmt(v: float, nd: int) -> str:
    out = f'{v:.{nd}f}'
    if '.' in out:
        out = out.rstrip('0').rstrip('.')
    if out in ('-0', ''):
        out = '0'
    return out


# ----------------------------- 메인 -----------------------------

def main() -> int:
    backfill_mode = '--backfill' in sys.argv
    key = load_key()
    if not key:
        print('ECOS_API_KEY not set - skipping ECOS fetch (no failure)')
        return 0

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

    our_names = {s['name'] for s in SERIES} | {d['name'] for d in DERIVED}
    max_stamp = {}
    leg_names = set()
    for d in DERIVED:
        leg_names.update((d['a'], d['b']))
    series_values = {n: {} for n in leg_names}   # 파생 계산용 (날짜→값)
    for row in all_rows:
        if len(row) >= 3 and row[1] in our_names:
            try:
                st = date.fromisoformat(row[0])
            except ValueError:
                continue
            if row[1] not in max_stamp or st > max_stamp[row[1]]:
                max_stamp[row[1]] = st
            if row[1] in leg_names:
                try:
                    series_values[row[1]][row[0]] = float(row[2].replace(',', ''))
                except ValueError:
                    pass

    new_rows = []
    healed = 0

    def upsert(stamp_iso: str, name: str, val: float, nd: int, dtype: str) -> int:
        """기존 행과 다르면 갱신(heal), 없으면 추가. 신규 1건이면 1 반환."""
        nonlocal healed
        new_s = fmt(val, nd)
        k = (stamp_iso, name)
        added = 0
        if k in index:
            old_s = all_rows[index[k]][2]
            if old_s != new_s:
                try:
                    same = abs(float(old_s.replace(',', '')) - float(new_s)) < 1e-9
                except ValueError:
                    same = False
                if not same:
                    all_rows[index[k]][2] = new_s
                    healed += 1
        else:
            row = [stamp_iso, name, new_s, dtype]
            all_rows.append(row)
            index[k] = len(all_rows) - 1
            new_rows.append(row)
            added = 1
        if name in leg_names:
            series_values[name][stamp_iso] = float(new_s)
        return added

    ok = 0
    failed = []
    for s in SERIES:
        try:
            start = fetch_start(s, max_stamp.get(s['name']), backfill_mode)
            end = ecos_end(s['cycle'], today)
            raw = api_fetch(key, s['stat'], s['cycle'], start, end, s['items'])

            if s.get('transform') == 'yoy':
                by_time = dict(raw)
                pairs = []
                for t, v in raw:
                    y, m = shift_ym(int(t[:4]), int(t[4:6]), -12)
                    base = by_time.get(f'{y:04d}{m:02d}')
                    if base:
                        pairs.append((t, (v / base - 1.0) * 100.0))
            else:
                scale = s.get('scale', 1)
                pairs = [(t, v * scale) for t, v in raw]

            floor = floor_stamp(s)
            added = 0
            kept = 0
            for t, v in pairs:
                st = stamp_for(t, s['cycle'], s.get('date_rule', ''))
                if st > today:          # 전역 미래 stamp 가드
                    continue
                if st < floor:          # backfill 하한
                    continue
                if s['cycle'] == 'D' and st.weekday() >= 5:   # 주말 행 제외 (기준금리)
                    continue
                added += upsert(st.isoformat(), s['name'], v, s['nd'], s['dtype'])
                kept += 1
            ok += 1
            print(f"  ✓ {s['name']}: fetch {len(raw)} → 유효 {kept}, 신규 {added}")
        except EcosError as e:
            failed.append(s['name'])
            print(f"  ⚠️ {s['name']}: {e}")
        except Exception as e:
            failed.append(s['name'])
            print(f"  ⚠️ {s['name']}: {type(e).__name__}")
        time.sleep(0.3)

    # 파생 시리즈 (inner join, 매 run 전체 재계산 — 무변경이면 no-op)
    for d in DERIVED:
        a, b = series_values.get(d['a'], {}), series_values.get(d['b'], {})
        added = 0
        common = sorted(set(a) & set(b))
        for ds in common:
            added += upsert(ds, d['name'], a[ds] - b[ds], d['nd'], d['dtype'])
        print(f"  ✓ {d['name']}: 계산 {len(common)}, 신규 {added}")

    if healed:
        # 개정 반영은 전체 재작성 필요 (신규 행은 all_rows에 이미 포함)
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

    print(f"\nECOS 수집 완료: 시리즈 {ok}/{len(SERIES)} 성공, 신규 {len(new_rows)}건, 개정 {healed}건")
    if failed:
        print(f"실패 시리즈: {', '.join(failed)}")
    if ok == 0:
        print('전 시리즈 실패 — ECOS 장애 의심')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
