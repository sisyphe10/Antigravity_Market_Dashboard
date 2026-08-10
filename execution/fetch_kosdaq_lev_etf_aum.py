# -*- coding: utf-8 -*-
"""코스닥 레버리지 ETF 순자산총액(AUM) 합산 → dataset.csv

KRX 정보데이터시스템 MDCSTAT04301(ETF 전종목시세)을 날짜당 1콜 호출해
종목명 필터("코스닥"+"레버리지", 공백 정규화)로 대상을 고른 뒤
INVSTASST_NETASST_TOTAMT(순자산총액, 원)를 정수 합산한다. 시리즈 1개:
  코스닥 레버리지 ETF AUM  (dtype ETF_AUM, 값=원 단위 정수)

- 날짜별 이름 필터라서 상장·상폐·브랜드 개명(KBSTAR→RISE 등)이 자동 반영된다.
  구성 변동으로 생기는 점프는 신호의 일부 — 보정·평활화하지 않는다.
- 로그인: fetch_krx_valuation.py와 동일 (pykrx 패치판이 import 시 env KRX_ID/KRX_PW로
  로그인). 로그인된 세션은 pykrx.website.comm.get_auth_session()으로 얻는다.
  ★로그인은 프로세스당 1회 — 실패해도 재시도하지 않는다(5회 잠금).
- ★자격증명 값은 어떤 경우에도 출력 금지. pykrx import 출력은 억제.
- 엄격 합산: 대상 종목 중 하나라도 AUM 파싱 불가면 그 날짜는 통째로 미적재
  (조용한 과소계상 방지). 전 종목이 '-'면 비거래일로 보고 skip.
- 증분: 기존 max 날짜 - lookback(10일)부터 재조회 후 (날짜, 제품명) upsert.
- 백필: --backfill → 2015-12-17(KODEX 233740 상장일)부터 어제까지 평일 순회.
  콜 간 0.5~0.8초 랜덤 sleep, 신규 50행마다 체크포인트 append(중단 재개 가능).

사용:
  python execution/fetch_kosdaq_lev_etf_aum.py                 # 증분
  python execution/fetch_kosdaq_lev_etf_aum.py --backfill      # 전체 백필
  python execution/fetch_kosdaq_lev_etf_aum.py --csv <경로>    # 대상 csv 변경(백필 격리용)
"""
import contextlib
import csv
import io
import os
import random
import re
import sys
import time
import unicodedata
from datetime import date, timedelta

import requests

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CSV_PATH_DEFAULT = 'dataset.csv'
DTYPE = 'ETF_AUM'
SERIES = '코스닥 레버리지 ETF AUM'
BACKFILL_START = date(2015, 12, 17)   # KODEX 코스닥150레버리지 상장일
LOOKBACK_DAYS = 10
SECRET_FILE_DEFAULT = 'secrets/data.krx.txt'

URL = 'http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd'
BLD = 'dbms/MDC/STAT/standard/MDCSTAT04301'
HDR = {'Referer': 'http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201040101',
       'User-Agent': 'Mozilla/5.0'}

KNOWN_ID = {'krx_id', 'id', 'user', 'username', 'userid', 'login', 'loginid'}
KNOWN_PW = {'krx_pw', 'pw', 'pass', 'password', 'passwd', 'pwd', 'krx_pwd'}


class AuthError(Exception):
    """로그인 만료/차단 등 — 재시도 없이 전체 중단."""


class FetchError(Exception):
    """일시 오류(429/5xx/네트워크) — 해당 날짜만 실패 처리."""


def load_krx_creds():
    """(id, pw) 또는 (None, None). 값은 절대 출력하지 않는다."""
    kid = os.environ.get('KRX_ID', '').strip()
    kpw = os.environ.get('KRX_PW', '').strip()
    if kid and kpw:
        return kid, kpw
    path = os.environ.get('KRX_LOGIN_FILE', SECRET_FILE_DEFAULT)
    if not os.path.exists(path):
        return None, None
    try:
        raw = open(path, encoding='utf-8-sig').read()
    except OSError:
        return None, None
    fid = fpw = None
    for line in raw.splitlines():
        m = re.match(r'\s*([A-Za-z_][\w]*)\s*[=:]\s*(.+?)\s*$', line)
        if not m:
            continue
        k = m.group(1).strip().lower()
        v = m.group(2).strip().strip('"').strip("'")
        if k in KNOWN_PW:
            fpw = v
        elif k in KNOWN_ID:
            fid = v
    if not (fid and fpw):
        toks = [t.strip().strip('"').strip("'")
                for t in re.split(r'[\s:,\r\n\t]+', raw.strip()) if t.strip()]
        if len(toks) >= 2:
            fid, fpw = toks[0], toks[1]
    return (fid, fpw) if (fid and fpw) else (None, None)


def normalize_name(value):
    value = unicodedata.normalize('NFKC', str(value))
    return re.sub(r'\s+', '', value)


def is_target(name):
    n = normalize_name(name)
    return '코스닥' in n and '레버리지' in n


def fetch_day(session, trd_dd):
    """해당 일자 ETF 전종목 행 리스트. 일시 오류는 3회 재시도, 인증 이상은 AuthError."""
    payload = {'bld': BLD, 'locale': 'ko_KR', 'trdDd': trd_dd,
               'share': '1', 'money': '1', 'csvxls_isNo': 'false'}
    last_err = None
    for attempt in range(3):
        try:
            r = session.post(URL, data=payload, headers=HDR, timeout=(5, 30))
        except requests.RequestException as e:
            last_err = f'net:{type(e).__name__}'
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            last_err = f'http:{r.status_code}'
            ra = r.headers.get('Retry-After', '')
            time.sleep(min(float(ra), 30.0) if ra.isdigit() else 2 * (attempt + 1))
            continue
        if r.status_code != 200:
            raise AuthError(f'HTTP {r.status_code}')
        try:
            j = r.json()
        except ValueError:
            hint = ' (LOGOUT/로그인 페이지 의심)' if ('LOGOUT' in r.text[:500] or 'login' in r.text[:500].lower()) else ''
            raise AuthError('비JSON 응답' + hint)
        if 'output' not in j:
            raise AuthError(f'output 키 없음: {sorted(j.keys())[:5]}')
        return j['output']
    raise FetchError(last_err or 'unknown')


def aggregate(rows):
    """(합계_원, 티커집합, None) 또는 (None, None, 사유). 부분 결측이면 미적재(엄격)."""
    targets = [r for r in rows if is_target(r.get('ISU_ABBRV', ''))]
    if not targets:
        return None, None, 'no-target'
    seen, total, dashes = set(), 0, 0
    for r in targets:
        t = r.get('ISU_SRT_CD', '')
        if t in seen:
            return None, None, f'dup:{t}'
        seen.add(t)
        raw = str(r.get('INVSTASST_NETASST_TOTAMT', '')).replace(',', '').strip()
        if raw in ('', '-'):
            dashes += 1
            continue
        try:
            v = int(raw)
        except ValueError:
            return None, None, f'parse:{t}'
        if v < 0:
            return None, None, f'neg:{t}'
        total += v
    if dashes == len(targets):
        return None, None, 'holiday'          # 전 종목 미표시 = 비거래일
    if dashes:
        return None, None, f'partial:{dashes}/{len(targets)}'  # 과소계상 방지
    return total, seen, None


def main():
    backfill = '--backfill' in sys.argv
    csv_path = CSV_PATH_DEFAULT
    if '--csv' in sys.argv:
        csv_path = sys.argv[sys.argv.index('--csv') + 1]

    kid, kpw = load_krx_creds()
    if not (kid and kpw):
        print('KRX 자격증명 없음 (env KRX_ID/KRX_PW 또는 secrets/data.krx.txt) - skip (no failure)')
        return 0
    os.environ['KRX_ID'] = kid
    os.environ['KRX_PW'] = kpw

    today = date.today()

    # 기존 csv 로드
    header = ['날짜', '제품명', '가격', '데이터 타입']
    all_rows = []
    if os.path.exists(csv_path):
        with open(csv_path, encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            h = next(reader, None)
            if h:
                header = h
            all_rows = [r for r in reader if r]

    index = {}
    max_stamp = None
    for i, r in enumerate(all_rows):
        if len(r) >= 2:
            index[(r[0], r[1])] = i
            if r[1] == SERIES:
                try:
                    st = date.fromisoformat(r[0])
                except ValueError:
                    continue
                if max_stamp is None or st > max_stamp:
                    max_stamp = st

    # pykrx import (env 설정 후 — import 시 data.krx 로그인). 출력 억제(ID 노출 방지).
    _buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(_buf), contextlib.redirect_stderr(_buf):
            from pykrx import stock  # noqa: F401  (import 자체가 로그인 트리거)
            from pykrx.website.comm import get_auth_session
        session = get_auth_session()
    except Exception as e:
        print(f'pykrx 로그인/세션 획득 실패: {type(e).__name__}')
        return 1
    print('pykrx 로드 완료 (data.krx 로그인 세션 확보)')

    # 대상 날짜: 평일 순회(휴장은 응답으로 판별)
    if backfill:
        start, end = BACKFILL_START, today - timedelta(days=1)
    else:
        start = (max_stamp - timedelta(days=LOOKBACK_DAYS)) if max_stamp else BACKFILL_START
        end = today
    dates = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            dates.append(d)
        d += timedelta(days=1)

    healed = 0
    pending = []       # 아직 파일에 안 쓴 신규 행
    n_new = n_ok = n_err = 0
    prev_set = None
    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0

    def flush_pending():
        """신규 행 append (체크포인트). 값 개정(healed)은 마지막에 전체 재작성으로 처리."""
        nonlocal pending, file_exists
        if not pending:
            return
        need_nl = False
        if file_exists:
            with open(csv_path, 'rb') as f:
                f.seek(-1, os.SEEK_END)
                need_nl = f.read(1) != b'\n'
        with open(csv_path, 'a', encoding='utf-8', newline='') as f:
            w = csv.writer(f, lineterminator='\n')
            if not file_exists:
                f.write(chr(0xFEFF))  # 원본 관례: 헤더에 BOM
                w.writerow(header)
                file_exists = True
            elif need_nl:
                f.write('\n')
            w.writerows(pending)
        pending = []

    for d in dates:
        stamp_iso = d.isoformat()
        try:
            rows = fetch_day(session, d.strftime('%Y%m%d'))
        except AuthError as e:
            flush_pending()
            print(f'  ✗ 인증 이상({stamp_iso}): {e} — 전체 중단 (로그인 재시도 금지)')
            return 1
        except FetchError as e:
            n_err += 1
            print(f'  ✗ {stamp_iso}: {e}')
            continue
        finally:
            time.sleep(random.uniform(0.5, 0.8) if backfill else 0.3)

        if not rows:
            continue                        # 휴장/미발표 — 조용히 skip
        total, tickers, reason = aggregate(rows)
        if reason == 'holiday':
            continue
        if reason is not None:
            n_err += 1
            print(f'  W {stamp_iso}: 미적재 ({reason})')
            continue

        if prev_set is not None and tickers != prev_set:
            print(f'  i {stamp_iso}: 구성 변동 {len(prev_set)}→{len(tickers)}종 '
                  f'+{sorted(tickers - prev_set)} -{sorted(prev_set - tickers)}')
        prev_set = tickers

        new_s = str(total)
        k = (stamp_iso, SERIES)
        if k in index:
            if all_rows[index[k]][2] != new_s:
                all_rows[index[k]][2] = new_s
                healed += 1
        else:
            row = [stamp_iso, SERIES, new_s, DTYPE]
            all_rows.append(row)
            index[k] = len(all_rows) - 1
            pending.append(row)
            n_new += 1
        n_ok += 1
        if len(pending) >= 50:
            flush_pending()
            print(f'  … 체크포인트 {stamp_iso} (누적 신규 {n_new})')

    flush_pending()
    if healed:
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f, lineterminator='\n')
            w.writerow(header)
            w.writerows(all_rows)

    if n_ok:
        last = max((r[0] for r in all_rows if len(r) >= 4 and r[1] == SERIES), default='')
        if last:
            v = next(r[2] for r in all_rows if r[0] == last and r[1] == SERIES)
            print(f'  최신 {last}: {int(v) / 1e8:,.0f}억원'
                  + (f' ({len(prev_set)}종)' if prev_set else ''))
    print(f'완료: 신규 {n_new}행, 보정 {healed}행, 적재일 {n_ok}, 실패일 {n_err}')
    return 1 if (n_ok == 0 and n_err > 0) else 0


if __name__ == '__main__':
    sys.exit(main())
