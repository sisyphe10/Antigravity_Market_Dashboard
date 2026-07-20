# -*- coding: utf-8 -*-
"""미국 FRED 시계열 수집 → dataset.csv

36종: 일별 금리·스프레드·달러·역레포 12 (FRED_RATE), 주간 5 (FRED_RATE),
월별 매크로 13 + 분기 GDPNow 1 (FRED_MACRO), 신용·부동산 5 + 분기 SLOOS 1 (FRED_SECTOR).

- ★매 run 전체 재조회: 증분 lookback 없음. 모든 시리즈를 start부터 끝까지 받아
  전 구간 (날짜, 제품명) upsert-heal. (FRED는 NFCI 전 역사 재추정, 고용 벤치마크
  5년 소급 등 개정이 깊어 증분으로는 회수 불가 → 매 run이 곧 백필.)
- 키: env FRED_API_KEY 우선, 없으면 로컬 .secrets 파일 폴백.
  둘 다 없으면 graceful skip (exit 0). 호출 간 0.5s sleep.
- --use-fredgraph: 무키 fredgraph.csv 경로. 호출 간 2.0s sleep, timeout 45s,
  실패 시 5s 후 1회 재시도 (burst 시 tarpit 지연 실측). CSV 헤더명 비의존
  (0열=날짜, 1열=값). 멀티 id 호출 금지.
  ★fredgraph는 비브라우저 TLS 핑거프린트를 차단(plain urllib/curl은 ~19s 후
  connection reset, 2026-06-10 실측) → curl_cffi(chrome impersonate) 우선,
  미설치 시 urllib 폴백. 공식 API 호스트는 plain urllib 정상.
- ★키·URL은 어떤 경우에도 출력 금지 (에러는 타입명/HTTP 코드만).
- 결측값 '.'/빈 문자열은 행 미생성.
- 날짜 스탬프:
    D = 관측일 그대로 (주말 weekday>=5 드롭 — DFEDTARU가 365일 데이터라 필수)
    W = 관측일 + shift_days (ICSA/CCSA는 토요일 라벨 week ending Saturday → -1일
        금요일 재스탬프. NFCI 금/WALCL 수/MORTGAGE30US 목 라벨은 그대로)
    M = 관측월의 달력 말일
    Q = 관측일이 분기 첫날 → ★그 달의 말일 (예: 2026-04-01→2026-04-30.
        분기 말일 스탬프 절대 금지 — 미래 stamp 가드에 걸려 현재 분기 통째 누락)
  stamp가 미래면 skip (다음 run 자동 편입).
- yoy: 원지수에서 같은 달 전년 대비 % (base>0 가드), 결과만 등재(원지수 미등재).
  mom_diff(PAYEMS): 전월차, 직전월 부재 시 skip.
- HTTP 일시 오류는 재시도 1회, 실패 시 해당 시리즈 skip.
- 키가 있는데 전 시리즈 실패 시에만 exit 1 (부분 실패는 exit 0, 다음 run이 회수).

사용:
  python execution/fetch_fred_data.py                  # FRED API (GHA daily_fred.yml)
  python execution/fetch_fred_data.py --use-fredgraph  # 무키 fredgraph.csv 경로
"""
import calendar
import csv
import io
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
SECRET_FILE = r'C:\Users\user\.secrets\fred_api_keys.env'
API_BASE = 'https://api.stlouisfed.org/fred/series/observations'
FREDGRAPH_BASE = 'https://fred.stlouisfed.org/graph/fredgraph.csv'

API_SLEEP = 0.5
FREDGRAPH_SLEEP = 2.0
FREDGRAPH_TIMEOUT = 45
FREDGRAPH_RETRY_WAIT = 5

# ---------------------------------------------------------------
# 시리즈 레지스트리 (36종, 2026-06-10 실측 앵커 검증)
# scale: 저장 전 곱셈 (단위 환산), nd: 반올림 자릿수
# transform: yoy=전년동월비 % / mom_diff=전월차 (원계열 미등재)
# shift_days: W 라벨 재스탬프 (ICSA/CCSA week ending Saturday → 금요일)
# 표시명은 ECOS 컨벤션 준수: 단위 괄호 없음, 괄호는 한정자만 (광의/C&I 등)
# ---------------------------------------------------------------
SERIES = [
    # ---- 일별 (FRED_RATE) → INTEREST RATES / EXCHANGE RATE / MACRO US ----
    dict(fred_id='DFEDTARU',     name='미 기준금리 상단',          cycle='D', dtype='FRED_RATE', start='2025-01-01', nd=2),
    dict(fred_id='DGS2',         name='US 2 Year Treasury Yield',  cycle='D', dtype='FRED_RATE', start='2025-01-01', nd=2),
    dict(fred_id='T10Y2Y',       name='미 장단기 금리차 10Y-2Y',   cycle='D', dtype='FRED_RATE', start='2025-01-01', nd=2),
    dict(fred_id='T10Y3M',       name='미 장단기 금리차 10Y-3M',   cycle='D', dtype='FRED_RATE', start='2025-01-01', nd=2),
    dict(fred_id='BAMLC0A4CBBB', name='미 BBB 스프레드',           cycle='D', dtype='FRED_RATE', start='2025-01-01', nd=2),
    dict(fred_id='BAMLH0A0HYM2', name='미 하이일드 스프레드',      cycle='D', dtype='FRED_RATE', start='2025-01-01', nd=2),
    dict(fred_id='DFII10',       name='미 실질금리 10Y',           cycle='D', dtype='FRED_RATE', start='2025-01-01', nd=2),
    dict(fred_id='T10YIE',       name='미 기대인플레 BEI 10Y',     cycle='D', dtype='FRED_RATE', start='2025-01-01', nd=2),
    dict(fred_id='T5YIFR',       name='미 기대인플레 5Y5Y',        cycle='D', dtype='FRED_RATE', start='2025-01-01', nd=2),
    dict(fred_id='SOFR',         name='SOFR',                      cycle='D', dtype='FRED_RATE', start='2025-01-01', nd=2),
    dict(fred_id='DTWEXBGS',     name='달러인덱스 (광의)',         cycle='D', dtype='FRED_RATE', start='2025-01-01', nd=2),
    dict(fred_id='RRPONTSYD',    name='미 역레포 잔고',            cycle='D', dtype='FRED_RATE', start='2025-01-01', nd=2),  # 십억달러
    # ---- 주간 (FRED_RATE) → MACRO US / CREDIT & HOUSING US ----
    dict(fred_id='ICSA',         name='미 신규 실업수당청구',      cycle='W', dtype='FRED_RATE', start='2025-01-01', scale=1e-4, nd=1, shift_days=-1),  # 만건, week ending Saturday
    dict(fred_id='CCSA',         name='미 연속 실업수당청구',      cycle='W', dtype='FRED_RATE', start='2025-01-01', scale=1e-4, nd=1, shift_days=-1),  # 만건
    dict(fred_id='NFCI',         name='미 금융여건지수 NFCI',      cycle='W', dtype='FRED_RATE', start='2025-01-01', nd=3),  # 금요일 라벨 그대로
    dict(fred_id='WALCL',        name='미 연준 총자산',            cycle='W', dtype='FRED_RATE', start='2025-01-01', scale=1e-6, nd=3),  # 백만달러→조달러, 수요일 라벨
    dict(fred_id='MORTGAGE30US', name='미 모기지 30년 금리',       cycle='W', dtype='FRED_RATE', start='2025-01-01', nd=2),  # 목요일 라벨
    # ---- 월별 매크로 (FRED_MACRO) → MACRO US ----
    dict(fred_id='CPIAUCSL',      name='미 CPI 전년동월비',             cycle='M', dtype='FRED_MACRO', start='2020-01-01', transform='yoy', nd=2),
    dict(fred_id='CPILFESL',      name='미 근원 CPI 전년동월비',        cycle='M', dtype='FRED_MACRO', start='2020-01-01', transform='yoy', nd=2),
    dict(fred_id='PCEPILFE',      name='미 근원 PCE 전년동월비',        cycle='M', dtype='FRED_MACRO', start='2020-01-01', transform='yoy', nd=2),
    dict(fred_id='PPIFIS',        name='미 PPI 전년동월비',             cycle='M', dtype='FRED_MACRO', start='2020-01-01', transform='yoy', nd=2),
    dict(fred_id='CES0500000003', name='미 시간당임금 전년동월비',      cycle='M', dtype='FRED_MACRO', start='2020-01-01', transform='yoy', nd=2),
    dict(fred_id='PAYEMS',        name='미 비농업고용 증감',            cycle='M', dtype='FRED_MACRO', start='2020-12-01', transform='mom_diff', nd=0),  # 천명
    dict(fred_id='UNRATE',        name='미 실업률',                     cycle='M', dtype='FRED_MACRO', start='2021-01-01', nd=1),
    dict(fred_id='JTSJOL',        name='미 JOLTS 구인',                 cycle='M', dtype='FRED_MACRO', start='2021-01-01', scale=1e-1, nd=1),  # 천건→만건
    dict(fred_id='RSAFS',         name='미 소매판매 전년동월비',        cycle='M', dtype='FRED_MACRO', start='2020-01-01', transform='yoy', nd=2),
    dict(fred_id='INDPRO',        name='미 산업생산 전년동월비',        cycle='M', dtype='FRED_MACRO', start='2020-01-01', transform='yoy', nd=2),
    dict(fred_id='NEWORDER',      name='미 근원자본재 수주 전년동월비', cycle='M', dtype='FRED_MACRO', start='2020-01-01', transform='yoy', nd=2),
    dict(fred_id='UMCSENT',       name='미시간 소비자심리',             cycle='M', dtype='FRED_MACRO', start='2021-01-01', nd=1),  # FRED 반영 1~2개월 지연 정상
    dict(fred_id='SAHMREALTIME',  name='미 Sahm Rule 침체지표',         cycle='M', dtype='FRED_MACRO', start='2021-01-01', nd=2),
    # ---- 월별 신용·부동산 (FRED_SECTOR) → CREDIT & HOUSING US ----
    dict(fred_id='HOUST',         name='미 주택착공',                   cycle='M', dtype='FRED_SECTOR', start='2021-01-01', scale=1e-1, nd=1),  # 천호→만호
    dict(fred_id='PERMIT',        name='미 건축허가',                   cycle='M', dtype='FRED_SECTOR', start='2021-01-01', scale=1e-1, nd=1),  # 천호→만호
    dict(fred_id='EXHOSLUSM495S', name='미 기존주택판매',               cycle='M', dtype='FRED_SECTOR', start='2021-01-01', scale=1e-4, nd=1),  # 호→만호
    dict(fred_id='CSUSHPINSA',    name='미 케이스-실러 주택가격 전년동월비', cycle='M', dtype='FRED_SECTOR', start='2020-01-01', transform='yoy', nd=2),
    # ---- 분기 (관측일=분기 첫날 → 그 달 말일 재스탬프) ----
    dict(fred_id='GDPNOW',        name='미 GDPNow 성장률',              cycle='Q', dtype='FRED_MACRO',  start='2021-01-01', nd=2),  # 같은 분기 수시 개정 → upsert-heal
    dict(fred_id='DRTSCILM',      name='미 은행 대출태도 (C&I)',        cycle='Q', dtype='FRED_SECTOR', start='2021-01-01', nd=1),
]


class FredError(Exception):
    pass


def load_key() -> str:
    key = os.environ.get('FRED_API_KEY', '').strip()
    if key:
        return key
    try:
        with open(SECRET_FILE, encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if line.startswith('FRED_API_KEY'):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ''


def _parse_obs_date(s: str) -> date:
    return date(int(s[:4]), int(s[5:7]), int(s[8:10]))


def api_fetch(key: str, fred_id: str, start: str) -> list:
    """FRED 공식 API observations → [(date, float)] (오름차순). 일시 오류 1회 재시도."""
    url = (f'{API_BASE}?series_id={fred_id}&api_key={key}'
           f'&file_type=json&observation_start={start}')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
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
            raise FredError(f'HTTP {e.code}') from None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            last_err = type(e).__name__
            if attempt == 0:
                time.sleep(2)
            continue
    if payload is None:
        raise FredError(f'transient failure after retry ({last_err})')
    out = []
    for o in payload.get('observations', []):
        d, v = o.get('date'), o.get('value')
        if not d or v in (None, '', '.'):   # 결측 '.'/빈 문자열 → 행 미생성
            continue
        try:
            out.append((_parse_obs_date(d), float(str(v).replace(',', ''))))
        except ValueError:
            continue
    out.sort(key=lambda x: x[0])
    return out


def _fredgraph_get(url: str) -> str:
    """fredgraph 1회 GET → CSV 텍스트. curl_cffi(chrome impersonate) 우선
    (★plain urllib/curl은 TLS 핑거프린트 차단으로 connection reset), 미설치 시 urllib."""
    try:
        from curl_cffi import requests as creq
    except ImportError:
        creq = None
    if creq is not None:
        r = creq.get(url, impersonate='chrome', timeout=FREDGRAPH_TIMEOUT)
        if r.status_code != 200:
            raise FredError(f'HTTP {r.status_code}')
        return r.content.decode('utf-8-sig')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=FREDGRAPH_TIMEOUT) as r:
        return r.read().decode('utf-8-sig')


def fredgraph_fetch(fred_id: str, start: str) -> list:
    """무키 fredgraph.csv → [(date, float)]. 헤더명 비의존(0열=날짜, 1열=값).
    timeout 45s, 실패 시 5s 후 1회 재시도 (burst tarpit 실측 대응)."""
    url = f'{FREDGRAPH_BASE}?id={fred_id}&cosd={start}'
    text = None
    last_err = ''
    for attempt in range(2):
        try:
            text = _fredgraph_get(url)
            break
        except FredError as e:
            last_err = str(e)
            if attempt == 0:
                time.sleep(FREDGRAPH_RETRY_WAIT)
            continue
        except urllib.error.HTTPError as e:
            last_err = f'HTTP {e.code}'
            if attempt == 0:
                time.sleep(FREDGRAPH_RETRY_WAIT)
            continue
        except Exception as e:
            # curl_cffi/urllib 공통: 타입명만 출력 (URL·키 노출 금지)
            last_err = type(e).__name__
            if attempt == 0:
                time.sleep(FREDGRAPH_RETRY_WAIT)
            continue
    if text is None:
        raise FredError(f'transient failure after retry ({last_err})')
    out = []
    reader = csv.reader(io.StringIO(text))
    next(reader, None)   # 헤더 1행 스킵 (이름 하드코딩 금지)
    for row in reader:
        if len(row) < 2:
            continue
        d, v = row[0].strip(), row[1].strip()
        if not d or v in ('', '.'):         # 결측 '.'/빈 문자열 → 행 미생성
            continue
        try:
            out.append((_parse_obs_date(d), float(v.replace(',', ''))))
        except ValueError:
            continue
    out.sort(key=lambda x: x[0])
    return out


# ----------------------------- 날짜 유틸 -----------------------------

def month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def stamp_for(obs: date, cycle: str, shift_days: int) -> date:
    """FRED 관측일 → dataset.csv 날짜 스탬프."""
    if cycle == 'D':
        return obs
    if cycle == 'W':
        return obs + timedelta(days=shift_days)
    # M: 관측일=월 첫날 → 그 달 말일.
    # Q: 관측일=분기 첫날 → ★그 달 말일 (분기 말일 금지 — 미래 가드에 현재 분기 누락)
    return month_end(obs.year, obs.month)


def fmt(v: float, nd: int) -> str:
    out = f'{v:.{nd}f}'
    if '.' in out:
        out = out.rstrip('0').rstrip('.')
    if out in ('-0', ''):
        out = '0'
    return out


# ----------------------------- 메인 -----------------------------

def main() -> int:
    use_fredgraph = '--use-fredgraph' in sys.argv
    crack_only = '--crack-only' in sys.argv   # 파생 크랙스프레드만 백필 (원계열 재조회 churn 회피)
    key = ''
    if not use_fredgraph:
        key = load_key()
        if not key:
            print('FRED_API_KEY 미설정, skip')
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
        return added

    ok = 0
    failed = []
    for s in (SERIES if not crack_only else []):
        try:
            if use_fredgraph:
                raw = fredgraph_fetch(s['fred_id'], s['start'])
            else:
                raw = api_fetch(key, s['fred_id'], s['start'])

            transform = s.get('transform')
            if transform == 'yoy':
                # 같은 달 전년 대비 % (base>0 가드), 결과만 등재
                by_ym = {(d.year, d.month): v for d, v in raw}
                pairs = []
                for d, v in raw:
                    base = by_ym.get((d.year - 1, d.month))
                    if base is not None and base > 0:
                        pairs.append((d, (v / base - 1.0) * 100.0))
            elif transform == 'mom_diff':
                # 전월차 (직전월 부재 시 skip)
                by_ym = {(d.year, d.month): v for d, v in raw}
                pairs = []
                for d, v in raw:
                    pm = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
                    prev = by_ym.get(pm)
                    if prev is not None:
                        pairs.append((d, v - prev))
            else:
                scale = s.get('scale', 1)
                pairs = [(d, v * scale) for d, v in raw]

            shift_days = s.get('shift_days', 0)
            added = 0
            kept = 0
            last_stamp, last_val = None, None
            for d, v in pairs:
                st = stamp_for(d, s['cycle'], shift_days)
                if st > today:          # 전역 미래 stamp 가드
                    continue
                if s['cycle'] == 'D' and st.weekday() >= 5:   # 주말 행 드롭 (DFEDTARU 365일 데이터)
                    continue
                added += upsert(st.isoformat(), s['name'], v, s['nd'], s['dtype'])
                kept += 1
                if last_stamp is None or st > last_stamp:
                    last_stamp, last_val = st, v
            ok += 1
            latest = f"{last_stamp.isoformat()}={fmt(last_val, s['nd'])}" if last_stamp else '-'
            print(f"  ✓ {s['name']} [{s['fred_id']}]: fetch {len(raw)} → 유효 {kept}, 신규 {added}, 최신 {latest}")
        except FredError as e:
            failed.append(s['name'])
            print(f"  ⚠️ {s['name']} [{s['fred_id']}]: {e}")
        except Exception as e:
            failed.append(s['name'])
            print(f"  ⚠️ {s['name']} [{s['fred_id']}]: {type(e).__name__}")
        time.sleep(FREDGRAPH_SLEEP if use_fredgraph else API_SLEEP)

    # ----- 파생 계열: 3-2-1 크랙스프레드 (NY Harbor, WTI·휘발유·증류유) -----
    # (2×휘발유 + 1×증류유)×42 − 3×WTI, ÷3 → $/bbl. 원계열은 계산용으로만 fetch(dataset.csv 미등재).
    CRACK_NAME = '미 3-2-1 크랙스프레드'
    CRACK_IDS = {'wti': 'DCOILWTICO', 'gaso': 'DGASNYH', 'dist': 'DHOILNYH'}  # NY Harbor 스팟
    CRACK_START = '2025-01-01'
    try:
        comp = {}
        for slot, fid in CRACK_IDS.items():
            raw = fredgraph_fetch(fid, CRACK_START) if use_fredgraph else api_fetch(key, fid, CRACK_START)
            comp[slot] = {d: v for d, v in raw}
            time.sleep(FREDGRAPH_SLEEP if use_fredgraph else API_SLEEP)
        common = sorted(set(comp['wti']) & set(comp['gaso']) & set(comp['dist']))
        cadded = 0
        clast_stamp = clast_val = None
        for d in common:
            if d > today or d.weekday() >= 5:      # 미래·주말 가드 (원계열은 영업일이나 방어적)
                continue
            crack = (2 * comp['gaso'][d] * 42 + comp['dist'][d] * 42 - 3 * comp['wti'][d]) / 3
            cadded += upsert(d.isoformat(), CRACK_NAME, crack, 1, 'FRED_RATE')
            if clast_stamp is None or d > clast_stamp:
                clast_stamp, clast_val = d, crack
        latest = f"{clast_stamp.isoformat()}={fmt(clast_val, 1)}" if clast_stamp else '-'
        print(f"  ✓ {CRACK_NAME} [파생]: 공통일 {len(common)}, 신규 {cadded}, 최신 {latest}")
    except Exception as e:
        failed.append(CRACK_NAME)
        print(f"  ⚠️ {CRACK_NAME} [파생]: {type(e).__name__}")

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

    print(f"\nFRED 수집 완료: 시리즈 {ok}/{len(SERIES)} 성공, 신규 {len(new_rows)}건, 개정 {healed}건")
    if failed:
        print(f"실패 시리즈: {', '.join(failed)}")
    if ok == 0 and not crack_only:
        print('전 시리즈 실패 — FRED 장애 의심')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
