"""국민연금 기금 적립금(총 기금적립금, 시가) → dataset.csv — 월별 3원 소스

2026-07-06 조사 확정 (온에어 vs odcloud 84조 격차 = 정의차 아님, 2026-03 실제 급락.
2025 연말 1,458.0조로 양 소스 동일 기준 증명 — 시가평가 총 적립금 = 금융+복지·기타):
1) odcloud 15106894 (연말 앵커 + 최신월, 지연 ~3개월) — '전체 자산(시장가)' 헤드라인 행만
   사용 (구성행 합산 금지 — 반올림/집계 차이. '기타부문' 열은 이상치 있음).
   ★uddi가 파일 버전마다 바뀜 → 페이지에서 publicDataDetailPk 해석, 실패 시 폴백.
2) fund.nps.or.kr 포트폴리오 현황 (getOHED0016M0.do, 서버렌더 HTML, 클라우드 접근 OK)
   — 최신월 전체자산(조원), 지연 ~2개월로 odcloud보다 1개월 빠름.
3) 온에어(npsonair.kr) 월별 아티클 — 과거 월별 1회 백필용 (--backfill-onair).
   ★SSL 검증 실패(unverified context 필요) + EUC-KR + 텍스트 파싱이라 상시 운영 비권장.

- 키: env DATA_GO_KR_API_KEY 우선, 없으면 로컬 .secrets 폴백 (odcloud만 필요).
- 값: 조원(소수 1자리). 실패는 소스 단위 경고 후 계속 (다음 run 회수).
저장: (날짜, '국민연금 적립금', 값, 'NPS_FUND'). 연말=12-31, 월점=해당월 말일.
"""
import calendar
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CSV_PATH = 'dataset.csv'
PRODUCT = '국민연금 적립금'
DTYPE = 'NPS_FUND'
DATASET_ID = '15106894'
PAGE_URL = f'https://www.data.go.kr/data/{DATASET_ID}/fileData.do'
FALLBACK_UDDI = 'uddi:92693ca1-42e2-48ad-a850-9da4c89026bc'  # 2026-03월분 (2026-07-06 확인)
SECRET_FILE = r'C:\Users\user\.secrets\customs_api_keys.env'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0'}


def load_key() -> str:
    key = os.environ.get('DATA_GO_KR_API_KEY', '').strip()
    if key:
        return key
    try:
        with open(SECRET_FILE, encoding='utf-8-sig') as f:
            for line in f:
                if line.strip().startswith('DATA_GO_KR_API_KEY'):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ''


def resolve_uddi() -> str:
    """데이터셋 페이지에서 현재 파일 버전의 publicDataDetailPk(uddi) 추출."""
    try:
        req = urllib.request.Request(PAGE_URL, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode('utf-8', errors='replace')
        m = re.search(r'name="publicDataDetailPk"\s+value="(uddi:[a-f0-9-]+)"', html)
        if m:
            return m.group(1)
    except (urllib.error.URLError, OSError) as e:
        print(f'  ⚠️ uddi 해석 실패({type(e).__name__}) - 폴백 사용')
    return FALLBACK_UDDI


def fetch_rows(key: str, uddi: str) -> list:
    qs = urllib.parse.urlencode({'serviceKey': key, 'page': 1, 'perPage': 50})
    url = f'https://api.odcloud.kr/api/{DATASET_ID}/v1/{uddi}?{qs}'
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read().decode('utf-8'))
    return payload.get('data', [])


def parse_points(row: dict) -> dict:
    """전체 자산 행의 컬럼들 → {YYYY-MM-DD: 조원}. 연말·월점 컬럼만 인식."""
    out = {}
    for col, val in row.items():
        if not isinstance(val, (int, float)):
            continue
        m = re.match(r'^(\d{4})년\(십억\s?원\)$', col)
        if m:
            out[f'{m.group(1)}-12-31'] = round(val / 1000, 1)
            continue
        m = re.match(r'^(\d{4})년\s*(\d{1,2})월\(십억\s?원\)$', col)
        if m:
            y, mo = int(m.group(1)), int(m.group(2))
            last = calendar.monthrange(y, mo)[1]
            out[f'{y:04d}-{mo:02d}-{last:02d}'] = round(val / 1000, 1)
    return out


def upsert(points: dict) -> tuple:
    existing = set()
    all_rows = []
    header = None
    healed = 0
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, encoding='utf-8-sig') as f:
            r = csv.reader(f)
            header = next(r, None)
            for row in r:
                if len(row) >= 3 and row[1] == PRODUCT:
                    existing.add(row[0])
                    if row[0] in points and row[2] != str(points[row[0]]):
                        row[2] = str(points[row[0]])
                        healed += 1
                all_rows.append(row)
    new_rows = [[d, PRODUCT, v, DTYPE] for d, v in sorted(points.items()) if d not in existing]
    if healed:
        with open(CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            if header:
                w.writerow(header)
            w.writerows(all_rows)
            w.writerows(new_rows)
    elif new_rows:
        with open(CSV_PATH, 'a', newline='', encoding='utf-8-sig') as f:
            csv.writer(f).writerows(new_rows)
    return len(new_rows), healed


def _month_end_key(y: int, mo: int) -> str:
    return f'{y:04d}-{mo:02d}-{calendar.monthrange(y, mo)[1]:02d}'


def fetch_fundnps_latest() -> dict:
    """기금운용본부 포트폴리오 현황 — 최신월 전체자산(조원). 지연 ~2개월."""
    url = 'https://fund.nps.or.kr/oprtprcn/ivsmprcn/getOHED0016M0.do'
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        html = r.read().decode('utf-8', errors='replace')
    m_date = re.search(r'(\d{4})년\s*(\d{1,2})월\s*말\s*기준', html)
    m_val = re.search(r'pf-total"><em>([\d,]+\.?\d*)</em>', html)
    if not (m_date and m_val):
        return {}
    y, mo = int(m_date.group(1)), int(m_date.group(2))
    return {_month_end_key(y, mo): round(float(m_val.group(1).replace(',', '')), 1)}


def fetch_onair_backfill(max_pages: int = 5) -> dict:
    """온에어 월별 아티클에서 (월말, 적립금 조원) 백필 — 1회성 시드용.

    소수점 있는 값만 채택 ("1,600조 원 돌파" 같은 라운드 헤드라인 배제).
    같은 월 중복 시 첫 매칭(구체 수치) 우선.
    """
    import ssl
    ctx = ssl._create_unverified_context()  # 온에어 인증서 체인 불완전 (실측)
    out = {}
    for page in range(1, max_pages + 1):
        url = f'https://www.npsonair.kr/fund_management/list.html?page={page}'
        req = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
                raw = r.read()
        except (urllib.error.URLError, OSError) as e:
            print(f'  ⚠️ 온에어 p{page} 실패({type(e).__name__}) - 중단')
            break
        try:
            html = raw.decode('utf-8')
        except UnicodeDecodeError:
            html = raw.decode('euc-kr', errors='replace')
        pairs = re.findall(
            r'적립금\s*([\d,]+\.\d)\s*조\s*원[^(]{0,30}\(\s*(\d{4})년\s*(\d{1,2})월\s*말',
            html)
        pairs += [(v, y, mo) for y, mo, v in re.findall(
            r'\(\s*(\d{4})년\s*(\d{1,2})월\s*말\s*기준\)[^0-9]{0,60}([\d,]+\.\d)\s*조\s*원', html)]
        for v, y, mo in pairs:
            k = _month_end_key(int(y), int(mo))
            out.setdefault(k, round(float(v.replace(',', '')), 1))
    return out


def main() -> int:
    print('\n🏦 국민연금 적립금 수집 시작')
    points = {}

    # 1) odcloud (연말 앵커 + 최신월)
    key = load_key()
    if not key:
        print('  DATA_GO_KR_API_KEY 없음 - odcloud skip')
    else:
        try:
            rows = fetch_rows(key, resolve_uddi())
            total_row = next((r for r in rows if str(r.get('구분', '')).startswith('전체 자산')), None)
            if total_row:
                got = parse_points(total_row)
                points.update(got)
                print(f'  ✓ odcloud: {len(got)}점')
            else:
                print(f'  ⚠️ odcloud 전체 자산 행 미발견 (rows={len(rows)})')
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            print(f'  ⚠️ odcloud 실패({type(e).__name__}) - 계속')

    # 2) fund.nps 최신월 (더 빠름 — odcloud와 같은 달이면 공식 공시 우선 덮어씀)
    try:
        latest = fetch_fundnps_latest()
        if latest:
            points.update(latest)
            d = max(latest)
            print(f'  ✓ fund.nps 최신월: {d} = {latest[d]}조원')
        else:
            print('  ⚠️ fund.nps 파싱 0건 - 페이지 구조 변경 가능성')
    except (urllib.error.URLError, OSError) as e:
        print(f'  ⚠️ fund.nps 실패({type(e).__name__}) - 계속')

    # 3) 온에어 백필 (옵션) — 이미 있는 날짜는 upsert가 값 다르면 정정하므로,
    #    공식 소스(1·2)가 이미 넣은 달은 setdefault로 보호
    if '--backfill-onair' in sys.argv:
        onair = fetch_onair_backfill()
        added_src = 0
        for k, v in onair.items():
            if k not in points:
                points[k] = v
                added_src += 1
        print(f'  ✓ 온에어 백필: {len(onair)}점 파싱, {added_src}점 채택(공식 소스 우선)')

    if not points:
        print('  ⚠️ 수집 0건 - skip')
        return 0
    added, healed = upsert(points)
    last = max(points)
    print(f'  ✓ {PRODUCT}: 총 {len(points)}점, 신규 {added}건, 정정 {healed}건 '
          f'(최신 {last} = {points[last]}조원)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
