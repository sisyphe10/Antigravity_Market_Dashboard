# -*- coding: utf-8 -*-
"""DTCC SBSDR 단일명 CDS 수집 → 하이퍼스케일러 5Y 스프레드 → dataset.csv

JPAIHYRS(JPM AI 하이퍼스케일러 신용 스프레드 지수, 비공개 커스텀) 근사 프록시.
소스는 도드-프랭크 실시간 공시(DTCC PPD, 무료·무인증) 일별 누적 슬라이스:
  SEC(단일명):  https://pddata.dtcc.com/ppd/api/report/cumulative/sec/SEC_CUMULATIVE_CREDITS_YYYY_MM_DD.zip
  CFTC(지수):   .../cftc/CFTC_CUMULATIVE_CREDITS_YYYY_MM_DD.zip  (v1은 원본 보존만, 시리즈 미산출)

- ★공개창 ~2년 롤링 (2026-08-03 실측: 2024-09-03 OK / 2024-06-03 404) → 매 run 원본 zip을
  ~/datalake/raw/dtcc_sbsdr/ 에 영구 보존. zip이 정본, 파생은 전부 재생성 캐시.
- 매 run: 최근 14 ET일 멱등 다운로드 → 아카이브 전 기간 재계산 → dataset.csv (날짜,제품명) upsert-heal
  (FRED 수집기 철학 동일 — 로직 수정 = 자동 소급. 늦게 도착한 CORR 정정도 자동 반영).
- 미완결 파일 heal: report date의 ET 자정+2h 이전에 받은 파일은 provisional → final 될 때까지 재조회.
- 변환 규칙 (2026-08-03 설계 확정, codex 병렬설계 취합):
  · 관측 = Action 'NEWT' × Event 'TRAD' × Spread notation '3'(decimal) × Spread-Leg 1 존재.
    CORR/EROR 는 Original Dissemination Identifier 의 원거래를 무효화(supersede).
    스프레드를 실은 CORR 는 정정 관측으로 편입. MODI/TERM 은 가격 관측 아님(계약 수정).
  · 5Y = 체결일+5년에 가장 가까운 표준 롤 만기(6/20·12/20)와 Expiration Date 정확 일치
    (3Y·7Y 혼입 차단. 2026-07-31 골든데이: 오라클 3Y 142bp 는 제외, 5Y 202.5bp 만 채택).
  · 날짜 = Execution Timestamp(UTC 'Z')를 America/New_York 로 변환한 체결일.
  · 일중 집계 = 비가중 중앙값 (블록 노셔널 "5,000,000+" 캡 → 노셔널 가중 불가). sanity 5~1500bp.
  · 매칭 = 정규화 법인명 anchored alias + REDID 화이트리스트. 키워드만 맞고 alias 미일치면
    발견 리포트로 경고(자회사 오인 방지, 신규 표기 수동 승인).
- 바스켓 'AI 하이퍼스케일러 CDS 5Y' = BASKET_MEMBERS 고정 **시가총액 가중**(2026-08-03 사용자 지시로
  동일가중에서 변경). 가중치 = datalake overseas_ohlcv 일별 종가 × 유효 주식수(SHARES, marketCap/price
  기준 — GOOGL 은 A클래스 주식수만 쓰면 시총 절반 누락). 주중일 그리드에서 종목별 스프레드
  ffill(상한 FFILL_CAP_BDAYS 영업일), ★전 구성원이 유효한 날만 산출(부분 재구성 금지).
- 관측일 MIN_EMIT_OBS 미만 종목은 dataset.csv 미등재 (코어위브 2일 — 유동성 생기면 자동 편입).
- 맥미니 전용: ~/datalake 부재 시 graceful skip(exit 0) — GHA workflow_dispatch 백업 러너 대응.

사용:
  python execution/fetch_dtcc_cds.py              # 일일 (launchd gha-dtcc-cds, 화~토 11:30 KST)
  python execution/fetch_dtcc_cds.py --dry-run    # dataset.csv 미기록 (검증용)
  python execution/fetch_dtcc_cds.py --backfill   # 경계 탐색 + 전 공개창 수집 + 재계산 (최초 1회)
  python execution/fetch_dtcc_cds.py --no-download  # 다운로드 생략, 아카이브 재계산만
"""
import csv
import glob
import hashlib
import io
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CSV_PATH = 'dataset.csv'
RAW_ROOT = os.environ.get('DTCC_RAW_ROOT', os.path.expanduser('~/datalake/raw/dtcc_sbsdr'))
MANIFEST = os.path.join(RAW_ROOT, 'manifest.csv')
URL_TPL = {
    'sec': 'https://pddata.dtcc.com/ppd/api/report/cumulative/sec/SEC_CUMULATIVE_CREDITS_{}.zip',
    'cftc': 'https://pddata.dtcc.com/ppd/api/report/cumulative/cftc/CFTC_CUMULATIVE_CREDITS_{}.zip',
}
NY = ZoneInfo('America/New_York')
SLEEP = 0.7
TIMEOUT = 60
LOOKBACK_ET_DAYS = 14          # 일일 모드 재조회 창 (게재 지연·provisional heal)
BACKFILL_STOP_404 = 45         # 연속 404(일요일 제외) 이만큼이면 공개창 경계로 판정

DTYPE = 'CDS_SPREAD'
ND = 1                          # bp, 소수점 첫째 자리
SANITY_LO_BP, SANITY_HI_BP = 5.0, 1500.0

# 종목 레지스트리 — alias 는 정규화(대문자, [.;,&]→공백, 공백 압축) 후 '전체 일치'만 허용
ISSUERS = [
    dict(key='ORCL', name='오라클 CDS 5Y', kw='ORACLE',
         aliases={'ORACLE CORPORATION', 'ORACLE CORP',
                  # 2026-08-03 백필 발견 리포트에서 승인한 실측 표기 변형
                  'ORACLECORP', 'ORACLE COP-6EC42L'}, redids={'6EC42L'}),
    dict(key='AMZN', name='아마존 CDS 5Y', kw='AMAZON',
         # 'AMAZON'/'-0C5448' 변형도 백필 발견 리포트에서 승인 (AMENTUM(AMAZON HOLDCO)는 별개 법인 — 미등재 유지)
         aliases={'AMAZON COM INC', 'AMAZON', 'AMAZON COM INC-0C5448'}, redids={'0C5448'}),
    dict(key='META', name='메타 CDS 5Y', kw='META PLATFORM',
         aliases={'META PLATFORMS INC'}, redids=set()),
    dict(key='MSFT', name='마이크로소프트 CDS 5Y', kw='MICROSOFT',
         aliases={'MICROSOFT CORPORATION', 'MICROSOFT CORP', 'MICROSOFT'}, redids=set()),
    dict(key='GOOGL', name='알파벳 CDS 5Y', kw='ALPHABET',
         aliases={'ALPHABET INC'}, redids=set()),
    dict(key='CRWV', name='코어위브 CDS 5Y', kw='COREWEAVE',
         aliases={'COREWEAVE INC'}, redids=set()),
]
BASKET_NAME = 'AI 하이퍼스케일러 CDS 5Y'
# 2026-08-03 백필 커버리지 실측으로 확정: 빅5(JPM CDS 바스켓과 동일 구성) × cap15 → 산출일 82%
# (cap10=63%·빅4=86%였으나 구성 대표성 우선). CRWV 는 관측 2일 → MIN_EMIT_OBS 가드로 미등재.
BASKET_MEMBERS = ['ORCL', 'AMZN', 'META', 'MSFT', 'GOOGL']
FFILL_CAP_BDAYS = 15
BASKET_START = '2026-04-15'     # 빅5 전 구성원 관측 개시일 (META·GOOGL 최초 관측)
MIN_EMIT_OBS = 5                # 관측일 이 미만인 종목은 dataset.csv 미등재
# 시총 가중 유효 주식수 = marketCap ÷ 주가 (yfinance, 2026-08-03). ★sharesOutstanding 을 쓰면
# GOOGL(A만 5.87B ↔ 실효 12.23B)·META 가 과소 → 반드시 실효치. 분기 1회 갱신이면 충분
# (일별 가중 변동은 종가가 만들고, 주식수 드리프트는 미미).
SHARES = {'ORCL': 2.880e9, 'AMZN': 10.757e9, 'META': 2.548e9, 'MSFT': 7.426e9, 'GOOGL': 12.230e9}
DUCKDB_PATH = os.path.expanduser('~/datalake/market/market.duckdb')

REQUIRED_COLS = {
    'Dissemination Identifier', 'Original Dissemination Identifier', 'Action type',
    'Event type', 'Execution Timestamp', 'Expiration Date', 'Underlying Asset Name',
    'Underlier ID-Leg 1', 'Underlier ID source-Leg 1', 'Spread-Leg 1', 'Spread notation-Leg 1',
}


# ----------------------------- 유틸 -----------------------------

def norm_name(s: str) -> str:
    for ch in '.;,&':
        s = s.replace(ch, ' ')
    return ' '.join(s.upper().split())


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def et_today() -> date:
    return datetime.now(tz=NY).date()


def is_final(report_d: date, fetched_at_utc: datetime) -> bool:
    """report date 의 ET 자정 종료 +2h 이후에 받았으면 최종본."""
    end_et = datetime(report_d.year, report_d.month, report_d.day, tzinfo=NY) + timedelta(hours=26)
    return fetched_at_utc >= end_et.astimezone(timezone.utc)


def target_5y_expiry(exec_d: date) -> date:
    """체결일+5년에 가장 가까운 표준 롤 만기(6/20·12/20)."""
    try:
        t = exec_d.replace(year=exec_d.year + 5)
    except ValueError:                      # 2/29
        t = exec_d.replace(year=exec_d.year + 5, day=28)
    cands = [date(y, m, 20) for y in (t.year - 1, t.year, t.year + 1) for m in (6, 12)]
    return min(cands, key=lambda c: abs((c - t).days))


# ----------------------------- manifest -----------------------------

def load_manifest() -> dict:
    m = {}
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding='utf-8') as f:
            for row in csv.DictReader(f):
                m[(row['side'], row['report_date'])] = row
    return m


def save_manifest(m: dict) -> None:
    cols = ['side', 'report_date', 'status', 'size', 'sha256', 'csv_rows', 'final', 'fetched_at']
    tmp = MANIFEST + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        for k in sorted(m):
            w.writerow(m[k])
    os.replace(tmp, MANIFEST)


# ----------------------------- 다운로드 -----------------------------

def zip_path(side: str, d: date) -> str:
    fname = URL_TPL[side].rsplit('/', 1)[1].format(d.strftime('%Y_%m_%d'))
    return os.path.join(RAW_ROOT, side, str(d.year), fname)


def fetch_one(side: str, d: date, manifest: dict) -> str:
    """멱등 다운로드. 반환: 'cached'|'ok'|'404'|'err'"""
    key = (side, d.isoformat())
    path = zip_path(side, d)
    ent = manifest.get(key)
    if ent and ent.get('status') == '200' and ent.get('final') == '1' and os.path.exists(path):
        return 'cached'
    url = URL_TPL[side].format(d.strftime('%Y_%m_%d'))
    now = datetime.now(timezone.utc)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            manifest[key] = dict(side=side, report_date=d.isoformat(), status='404', size='0',
                                 sha256='', csv_rows='0', final='1' if is_final(d, now) else '0',
                                 fetched_at=now.isoformat(timespec='seconds'))
            return '404'
        print(f"  W {side} {d}: HTTP {e.code}")
        return 'err'
    except Exception as e:
        print(f"  W {side} {d}: {type(e).__name__}")
        return 'err'
    # zip 검증 (내부 파일 정확 1개) 후 원자적 이동
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = zf.namelist()
        assert len(names) == 1
        rows = sum(1 for _ in io.TextIOWrapper(zf.open(names[0]), encoding='utf-8-sig')) - 1
    except Exception:
        print(f"  W {side} {d}: zip 검증 실패 — 미보존")
        return 'err'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)
    manifest[key] = dict(side=side, report_date=d.isoformat(), status='200', size=str(len(data)),
                         sha256=sha256_file(path), csv_rows=str(rows),
                         final='1' if is_final(d, now) else '0',
                         fetched_at=now.isoformat(timespec='seconds'))
    return 'ok'


def download_daily(manifest: dict) -> None:
    t = et_today()
    got = c404 = 0
    for i in range(LOOKBACK_ET_DAYS + 1):
        d = t - timedelta(days=i)
        for side in ('sec', 'cftc'):
            r = fetch_one(side, d, manifest)
            if r == 'ok':
                got += 1
            elif r == '404':
                c404 += 1
            if r in ('ok', '404'):
                time.sleep(SLEEP)
    print(f"다운로드: 신규 {got}, 404 {c404} (창 {LOOKBACK_ET_DAYS} ET일)")


def download_backfill(manifest: dict) -> None:
    """현재 → 과거 방향, 연속 404(일요일 제외)가 임계에 달하면 공개창 경계로 판정."""
    d = et_today()
    misses = got = 0
    while misses < BACKFILL_STOP_404:
        r = fetch_one('sec', d, manifest)
        if r == 'ok':
            got += 1
        if r in ('ok', '404'):
            fetch_one('cftc', d, manifest)
            time.sleep(SLEEP)
        if d.weekday() != 6:                # 일요일 404 는 경계 카운트 제외
            if r == '404':
                misses += 1
            elif r in ('ok', 'cached'):
                misses = 0
        if got and got % 50 == 0 and r == 'ok':
            print(f"  ... {d} 까지 신규 {got}건", flush=True)
            save_manifest(manifest)         # 중단 대비 중간 저장
        d -= timedelta(days=1)
    print(f"백필 완료: 신규 {got}건, 경계(연속 404 {BACKFILL_STOP_404}) = {d.isoformat()} 부근")


# ----------------------------- 파싱 · 재계산 -----------------------------

def parse_archive():
    """아카이브 전 SEC zip → issuer/ET체결일별 bp 리스트 + QA 통계."""
    alias_map = {}
    for s in ISSUERS:
        for a in s['aliases']:
            alias_map[a] = s['key']
    redid_map = {}
    for s in ISSUERS:
        for r in s['redids']:
            redid_map[r] = s['key']
    kws = [(s['kw'], s['key']) for s in ISSUERS]

    superseded = set()
    cands = {}                              # dissemination id → (issuer, et_date, bp)
    discovery = set()
    stats = dict(files=0, rows=0, matched=0, no_spread=0, bad_notation=0,
                 off_tenor=0, sanity=0, dup_id=0, bad_ts=0)

    for zp in sorted(glob.glob(os.path.join(RAW_ROOT, 'sec', '*', '*.zip'))):
        try:
            zf = zipfile.ZipFile(zp)
            name = zf.namelist()[0]
            reader = csv.DictReader(io.TextIOWrapper(zf.open(name), encoding='utf-8-sig'))
        except Exception:
            print(f"  W 손상 zip skip: {os.path.basename(zp)}")
            continue
        stats['files'] += 1
        first = True
        for row in reader:
            if first:
                first = False
                missing = REQUIRED_COLS - set(row.keys())
                if missing:
                    print(f"  W 스키마 불일치 skip: {os.path.basename(zp)} 결측 {sorted(missing)[:3]}")
                    break
            stats['rows'] += 1
            act = row.get('Action type', '')
            orig = row.get('Original Dissemination Identifier', '')
            if act in ('CORR', 'EROR') and orig:
                superseded.add(orig)
            if act not in ('NEWT', 'CORR') or row.get('Event type') != 'TRAD':
                continue
            # 종목 매칭 (ID 우선 → anchored alias → 발견 리포트)
            nm = norm_name(row.get('Underlying Asset Name', ''))
            issuer = None
            if row.get('Underlier ID source-Leg 1') == 'REDID':
                issuer = redid_map.get(row.get('Underlier ID-Leg 1', ''))
            if issuer is None:
                issuer = alias_map.get(nm)
            if issuer is None:
                for kw, _k in kws:
                    if kw in nm:
                        discovery.add(nm)
                        break
                continue
            stats['matched'] += 1
            spr = row.get('Spread-Leg 1', '').replace(',', '')
            if not spr:
                stats['no_spread'] += 1
                continue
            if row.get('Spread notation-Leg 1') != '3':
                stats['bad_notation'] += 1
                continue
            try:
                bp = float(spr) * 10000.0
            except ValueError:
                stats['bad_notation'] += 1
                continue
            if not (SANITY_LO_BP <= bp <= SANITY_HI_BP):
                stats['sanity'] += 1
                continue
            ts = row.get('Execution Timestamp', '')
            try:
                exec_dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                et_d = exec_dt.astimezone(NY).date()
            except ValueError:
                stats['bad_ts'] += 1
                continue
            try:
                exp = date.fromisoformat(row.get('Expiration Date', ''))
            except ValueError:
                stats['off_tenor'] += 1
                continue
            if exp != target_5y_expiry(et_d):
                stats['off_tenor'] += 1
                continue
            did = row.get('Dissemination Identifier', '')
            if did in cands:
                stats['dup_id'] += 1
            cands[did] = (issuer, et_d, bp)

    obs = {s['key']: {} for s in ISSUERS}
    for did, (issuer, et_d, bp) in cands.items():
        if did in superseded:
            continue
        obs[issuer].setdefault(et_d, []).append(bp)
    return obs, stats, discovery


def load_daily_caps():
    """datalake overseas_ohlcv 일별 종가 × 유효 주식수 → {key: {date: 시총}}. 실패 시 예외."""
    import duckdb
    start = (date.fromisoformat(BASKET_START) - timedelta(days=40)).isoformat() \
        if BASKET_START else '2024-01-01'
    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    try:
        ph = ','.join('?' * len(BASKET_MEMBERS))
        rows = con.execute(
            f"SELECT symbol, CAST(date AS DATE), close FROM overseas_ohlcv "
            f"WHERE symbol IN ({ph}) AND date >= ?",
            BASKET_MEMBERS + [start]).fetchall()
    finally:
        con.close()
    caps = {k: {} for k in BASKET_MEMBERS}
    for sym, d, close in rows:
        if close:
            caps[sym][d] = close * SHARES[sym]
    return caps


def compute_series(obs):
    """종목별 일중 중앙값 + 고정 바스켓(시총 가중). 반환: {표시명: {date: float}}"""
    series = {}
    medians = {}                            # key → {date: 미반올림 중앙값}
    for s in ISSUERS:
        m = {d: statistics.median(v) for d, v in sorted(obs[s['key']].items())}
        medians[s['key']] = m
        if len(m) >= MIN_EMIT_OBS:
            series[s['name']] = m
        elif m:
            print(f"  - {s['name']}: 관측 {len(m)}일 < {MIN_EMIT_OBS} → 미등재 (원본은 보존)")
    if not (BASKET_MEMBERS and all(medians.get(k) for k in BASKET_MEMBERS)):
        return series
    caps = None
    try:
        caps = load_daily_caps()
        missing = [k for k in BASKET_MEMBERS if not caps.get(k)]
        if missing:
            print(f"  W 시총 가중치 결측 {missing} → 바스켓 미산출")
            caps = None
    except Exception as e:
        print(f"  W 시총 로드 실패({type(e).__name__}) → 바스켓 미산출")
    if caps is None:
        return series
    start = max(min(medians[k]) for k in BASKET_MEMBERS)
    if BASKET_START:
        start = max(start, date.fromisoformat(BASKET_START))
    end = max(max(medians[k]) for k in BASKET_MEMBERS)
    basket = {}
    last = {k: (None, None) for k in BASKET_MEMBERS}       # key → (관측일, 스프레드)
    lastcap = {k: None for k in BASKET_MEMBERS}            # key → 최근 시총 (종가 ffill)
    d = start
    while d <= end:
        if d.weekday() < 5:
            vals = {}
            for k in BASKET_MEMBERS:
                if d in caps[k]:
                    lastcap[k] = caps[k][d]
                if d in medians[k]:
                    last[k] = (d, medians[k][d])
                ld, lv = last[k]
                if ld is not None:
                    age = sum(1 for i in range(1, (d - ld).days + 1)
                              if (ld + timedelta(days=i)).weekday() < 5)
                    if age <= FFILL_CAP_BDAYS:
                        vals[k] = lv
            # 전 구성원의 스프레드·시총이 유효한 날만 산출 (부분 재구성 금지)
            if len(vals) == len(BASKET_MEMBERS) and all(lastcap[k] for k in BASKET_MEMBERS):
                tw = sum(lastcap[k] for k in BASKET_MEMBERS)
                basket[d] = sum(lastcap[k] * vals[k] for k in BASKET_MEMBERS) / tw
        d += timedelta(days=1)
    if basket:
        series[BASKET_NAME] = basket
    return series


# ----------------------------- dataset.csv upsert -----------------------------

def fmt(v: float, nd: int) -> str:
    out = f'{v:.{nd}f}'
    if '.' in out:
        out = out.rstrip('0').rstrip('.')
    return '0' if out in ('-0', '') else out


def upsert_dataset(series: dict, dry: bool) -> None:
    header = ['날짜', '제품명', '가격', '데이터 타입']
    all_rows = []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            h = next(reader, None)
            if h:
                header = h
            all_rows = [row for row in reader if row]
    index = {(r[0], r[1]): i for i, r in enumerate(all_rows) if len(r) >= 2}

    new_rows, healed = [], 0
    today = date.today()
    for name, m in series.items():
        added = 0
        for d, v in sorted(m.items()):
            if d > today:
                continue
            k = (d.isoformat(), name)
            new_s = fmt(v, ND)
            if k in index:
                if all_rows[index[k]][2] != new_s:
                    all_rows[index[k]][2] = new_s
                    healed += 1
            else:
                row = [d.isoformat(), name, new_s, DTYPE]
                all_rows.append(row)
                index[k] = len(all_rows) - 1
                new_rows.append(row)
                added += 1
        last_d = max(m) if m else None
        latest = f"{last_d.isoformat()}={fmt(m[last_d], ND)}" if last_d else '-'
        print(f"  + {name}: 관측일 {len(m)}, 신규 {added}, 최신 {latest}")

    if dry:
        print(f"[dry-run] dataset.csv 미기록 (신규 {len(new_rows)}, 개정 {healed})")
        return
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
    print(f"dataset.csv: 신규 {len(new_rows)}건, 개정 {healed}건")


# ----------------------------- 메인 -----------------------------

def main() -> int:
    dry = '--dry-run' in sys.argv
    backfill = '--backfill' in sys.argv
    no_dl = '--no-download' in sys.argv

    lake_parent = os.path.dirname(os.path.dirname(RAW_ROOT))   # ~/datalake
    if not os.path.isdir(lake_parent):
        print(f"datalake 부재({lake_parent}) → graceful skip (맥미니 전용 잡)")
        return 0
    os.makedirs(RAW_ROOT, exist_ok=True)

    manifest = load_manifest()
    try:
        if not no_dl:
            if backfill:
                download_backfill(manifest)
            else:
                download_daily(manifest)
    finally:
        save_manifest(manifest)

    obs, stats, discovery = parse_archive()
    print(f"파싱: 파일 {stats['files']}, 행 {stats['rows']}, 매칭 {stats['matched']} "
          f"(무스프레드 {stats['no_spread']}, 비표준표기 {stats['bad_notation']}, "
          f"테너제외 {stats['off_tenor']}, sanity {stats['sanity']}, 중복ID {stats['dup_id']})")
    for nm in sorted(discovery):
        print(f"  ? 미승인 유사 법인명 (화이트리스트 검토): {nm}")
    if stats['files'] == 0:
        print('아카이브에 파싱 가능한 파일 없음')
        return 1

    series = compute_series(obs)
    if not series:
        print('산출 시리즈 없음')
        return 1
    upsert_dataset(series, dry)
    return 0


if __name__ == '__main__':
    sys.exit(main())
