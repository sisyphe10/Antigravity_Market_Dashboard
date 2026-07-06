"""국민연금 기금 적립금(전체 자산, 시장가) → dataset.csv

Source: 공공데이터포털 국민연금공단_기금 포트폴리오 현황 (dataset 15106894)
- odcloud 파일데이터 API. 구조가 피벗형: '구분' 행 × 컬럼 '2021년(십억 원)'..
  '2026년 3월(십억 원)' — 연말 스냅샷 + 최신월 1개점.
- 파일이 갱신될 때마다 최신월 컬럼이 교체되므로, 매 run upsert로 누적하면
  연간 백필 + 분기/월 단위 최신점들이 시계열로 쌓인다 (SiliconData 창 누적과 동일 철학).
- ★uddi가 파일 버전마다 바뀜 → 데이터셋 페이지에서 publicDataDetailPk를 매번 해석,
  실패 시 마지막 확인 uddi 폴백.
- 키: env DATA_GO_KR_API_KEY 우선, 없으면 로컬 .secrets 폴백. 둘 다 없으면 graceful skip.
- 값: 십억원 → 조원(소수 1자리). 실패는 경고 후 exit 0 (다음 run 회수,
  일별 감시 부적합한 저빈도 소스라 check_data_freshness는 IGNORE).

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


def main() -> int:
    print('\n🏦 국민연금 적립금 수집 시작')
    key = load_key()
    if not key:
        print('  DATA_GO_KR_API_KEY 없음 - skip (no failure)')
        return 0
    try:
        rows = fetch_rows(key, resolve_uddi())
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        print(f'  ⚠️ API 실패({type(e).__name__}) - skip')
        return 0
    total_row = next((r for r in rows if str(r.get('구분', '')).startswith('전체 자산')), None)
    if not total_row:
        print(f'  ⚠️ 전체 자산 행 미발견 (rows={len(rows)}) - 파일 구조 변경 가능성, skip')
        return 0
    points = parse_points(total_row)
    if not points:
        print('  ⚠️ 날짜 컬럼 파싱 0건 - 컬럼 형식 변경 가능성, skip')
        return 0
    added, healed = upsert(points)
    last = max(points)
    print(f'  ✓ {PRODUCT}: {len(points)}점 파싱, 신규 {added}건, 정정 {healed}건 '
          f'(최신 {last} = {points[last]}조원)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
