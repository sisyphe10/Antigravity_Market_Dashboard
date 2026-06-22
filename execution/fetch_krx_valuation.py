# -*- coding: utf-8 -*-
"""KOSPI/KOSDAQ 지수 밸류에이션(후행 PER/PBR/배당수익률) → dataset.csv

pykrx(data.krx 로그인 패치판) get_index_fundamental 사용. 6개 시리즈:
코스피/코스닥 × PER/PBR/배당수익률 (모두 후행 trailing 기준 — 선행/forward 없음).

- 로그인: 이 pykrx는 import 시 os.environ['KRX_ID']/['KRX_PW']로 data.krx에 로그인한다.
  → import 전에 env 설정 필수. 자격증명 우선순위:
    1) env KRX_ID/KRX_PW
    2) secret 파일 (기본 secrets/data.krx.txt, env KRX_LOGIN_FILE로 경로 override)
       형식 자동 판별: `KRX_ID=..\nKRX_PW=..` / `id:pw` / 두 줄 / 공백구분
    3) 둘 다 없으면 graceful skip (exit 0)
- ★자격증명 값은 어떤 경우에도 출력 금지. pykrx 로그인 시 ID를 stdout에 찍으므로 import 출력은 억제.
- 증분: 시리즈별 기존 max 날짜 - lookback(10일)부터 재조회 후 (날짜, 제품명) upsert(self-heal).
- 백필: --backfill → 2024-01-01부터 전체.
- 거래일 스탬프(YYYY-MM-DD), 미래일 skip, NaN 값 skip, PER/PBR/배당 2자리 반올림.
- 일부 지수 실패는 exit 0(다음 run 회수), 자격증명 있는데 전부 실패 시에만 exit 1.

사용:
  python execution/fetch_krx_valuation.py            # 증분
  python execution/fetch_krx_valuation.py --backfill  # 2024-01-01부터 전체
"""
import contextlib
import csv
import io
import math
import os
import re
import sys
from datetime import date, timedelta

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CSV_PATH = 'dataset.csv'
DTYPE = 'KRX_VALUATION'
BACKFILL_START = date(2024, 1, 1)
LOOKBACK_DAYS = 10
SECRET_FILE_DEFAULT = 'secrets/data.krx.txt'

# (지수 표시명, pykrx 코드) — INDEX_KOREA 그룹 관례에 맞춰 영문 KOSPI/KOSDAQ 사용
INDICES = [('KOSPI', '1001'), ('KOSDAQ', '2001')]
# (pykrx 컬럼명, 시리즈명 접미사)
METRICS = [('PER', 'PER'), ('PBR', 'PBR'), ('배당수익률', '배당수익률')]

KNOWN_ID = {'krx_id', 'id', 'user', 'username', 'userid', 'login', 'loginid'}
KNOWN_PW = {'krx_pw', 'pw', 'pass', 'password', 'passwd', 'pwd', 'krx_pwd'}


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


def fmt(v, nd=2):
    out = f'{v:.{nd}f}'
    if '.' in out:
        out = out.rstrip('0').rstrip('.')
    if out in ('-0', ''):
        out = '0'
    return out


def main():
    backfill = '--backfill' in sys.argv

    kid, kpw = load_krx_creds()
    if not (kid and kpw):
        print('KRX 자격증명 없음 (env KRX_ID/KRX_PW 또는 secrets/data.krx.txt) - skip (no failure)')
        return 0
    os.environ['KRX_ID'] = kid
    os.environ['KRX_PW'] = kpw

    today = date.today()

    # 기존 dataset.csv 로드
    header = ['날짜', '제품명', '가격', '데이터 타입']
    all_rows = []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            h = next(reader, None)
            if h:
                header = h
            all_rows = [r for r in reader if r]

    our_names = {f'{idx} {suf}' for idx, _ in INDICES for _, suf in METRICS}
    index = {}
    max_stamp = {}
    for i, r in enumerate(all_rows):
        if len(r) >= 2:
            index[(r[0], r[1])] = i
            if r[1] in our_names:
                try:
                    st = date.fromisoformat(r[0])
                except ValueError:
                    continue
                if r[1] not in max_stamp or st > max_stamp[r[1]]:
                    max_stamp[r[1]] = st

    healed = 0
    new_rows = []

    def upsert(stamp_iso, name, val):
        nonlocal healed
        new_s = fmt(val)
        k = (stamp_iso, name)
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
            return 0
        row = [stamp_iso, name, new_s, DTYPE]
        all_rows.append(row)
        index[k] = len(all_rows) - 1
        new_rows.append(row)
        return 1

    # pykrx import (env 설정 후). 로그인 시 ID를 찍으므로 import 출력 억제.
    _buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(_buf), contextlib.redirect_stderr(_buf):
            from pykrx import stock
    except Exception as e:
        print(f'pykrx import 실패: {type(e).__name__}')
        return 1
    print('pykrx 로드 완료 (data.krx 로그인 시도됨)')

    ok = 0
    failed = []
    for idx, code in INDICES:
        try:
            if backfill:
                start = BACKFILL_START
            else:
                idx_names = [f'{idx} {suf}' for _, suf in METRICS]
                stamps = [max_stamp[n] for n in idx_names if n in max_stamp]
                start = (min(stamps) - timedelta(days=LOOKBACK_DAYS)) if stamps else BACKFILL_START
            df = stock.get_index_fundamental(start.strftime('%Y%m%d'),
                                             today.strftime('%Y%m%d'), code)
            if df is None or df.empty:
                print(f'  - {idx}: 데이터 없음 (로그인 실패 또는 휴장)')
                failed.append(idx)
                continue
            added = kept = 0
            for ts, row in df.iterrows():
                stamp = ts.date()
                if stamp > today:
                    continue
                stamp_iso = stamp.isoformat()
                for col, suf in METRICS:
                    v = row.get(col)
                    # 0/NaN = 미발표·데이터없음 (지수 PER/PBR/배당은 0이 될 수 없음) → skip
                    if v is None or (isinstance(v, float) and math.isnan(v)) or float(v) == 0:
                        continue
                    added += upsert(stamp_iso, f'{idx} {suf}', float(v))
                    kept += 1
            ok += 1
            print(f'  ✓ {idx}: rows {len(df)} → 유효 {kept}, 신규 {added}')
        except Exception as e:
            print(f'  ✗ {idx}: {type(e).__name__}')
            failed.append(idx)

    # 쓰기: 보정(값 개정) 발생 시에만 전체 재작성, 그 외 신규는 append (기존 바이트 보존 → diff 최소).
    # 원본 dataset.csv 포맷: UTF-8(BOM 없음) + LF (csv.writer 기본 CRLF 방지 위해 lineterminator 지정).
    if healed:
        with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f, lineterminator='\n')
            w.writerow(header)
            w.writerows(all_rows)
    elif new_rows:
        exists = os.path.exists(CSV_PATH) and os.path.getsize(CSV_PATH) > 0
        need_nl = False
        if exists:
            with open(CSV_PATH, 'rb') as f:
                f.seek(-1, os.SEEK_END)
                need_nl = f.read(1) != b'\n'   # 파일 끝 개행 없으면 마지막 줄에 붙는 것 방지
        with open(CSV_PATH, 'a', encoding='utf-8', newline='') as f:
            w = csv.writer(f, lineterminator='\n')
            if not exists:
                w.writerow(header)
            elif need_nl:
                f.write('\n')
            w.writerows(new_rows)

    print(f'완료: 신규 {len(new_rows)}행, 보정 {healed}행, 성공 {ok}/{len(INDICES)}'
          + (f', 실패 {failed}' if failed else ''))
    return 1 if ok == 0 else 0


if __name__ == '__main__':
    sys.exit(main())
