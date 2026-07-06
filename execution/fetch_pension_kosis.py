"""퇴직연금 총 적립금 (연간) → dataset.csv

Source: KOSIS 퇴직연금통계 (통계청, 승인통계 — 매년 12월 전년말 확정 발표)
- 통계표: orgId=101, tblId=DT_1RP013 '제도유형별 운용방법별 적립금액'
- 총액 = 제도유형 계(objL1=0) × 운용방법 계(objL2=0), 단위 백만원 → 조원
- 수록: 2015~ (2026-07 기준 최신 2024 = 430.5조원)
- ★분기+ 빈도 공식 소스 없음 (금감원 분기 발표는 2015-12 종료) — 연 1회 갱신이 최선.
- 키: env KOSIS_API_KEY 우선, 없으면 로컬 .secrets 폴백. 없으면 graceful skip.
  ★apiKey는 base64 특수문자 포함 → URL 인코딩 필수.
- 실패는 경고 후 exit 0. 신선도 감시는 DATASET_IGNORE (연간 소스).

저장: (YYYY-12-31, '퇴직연금 적립금', 조원, 'KOSIS_PENSION'). upsert(값 정정 시 덮어씀).
"""
import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CSV_PATH = 'dataset.csv'
PRODUCT = '퇴직연금 적립금'
DTYPE = 'KOSIS_PENSION'
SECRET_FILE = r'C:\Users\user\.secrets\kosis_api_keys.env'
START_YEAR = '2015'


def load_key() -> str:
    key = os.environ.get('KOSIS_API_KEY', '').strip()
    if key:
        return key
    try:
        with open(SECRET_FILE, encoding='utf-8-sig') as f:
            for line in f:
                if line.strip().startswith('KOSIS_API_KEY'):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ''


def fetch_points(key: str) -> dict:
    params = {
        'method': 'getList', 'apiKey': key, 'orgId': '101', 'tblId': 'DT_1RP013',
        'itmId': 'ALL', 'objL1': '0', 'objL2': '0',
        'format': 'json', 'jsonVD': 'Y', 'prdSe': 'A',
        'startPrdDe': START_YEAR, 'endPrdDe': str(date.today().year),
    }
    url = 'https://kosis.kr/openapi/Param/statisticsParameterData.do?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read().decode('utf-8'))
    if isinstance(payload, dict) and payload.get('err'):
        raise ValueError(f"KOSIS err {payload.get('err')}")
    out = {}
    for row in payload:
        y = str(row.get('PRD_DE', '')).strip()
        try:
            v = float(row['DT'])
        except (KeyError, TypeError, ValueError):
            continue
        if len(y) == 4 and v > 0:
            out[f'{y}-12-31'] = round(v / 1e6, 1)  # 백만원 → 조원
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
    print('\n🪙 퇴직연금 적립금(연간) 수집 시작')
    key = load_key()
    if not key:
        print('  KOSIS_API_KEY 없음 - skip (no failure)')
        return 0
    try:
        points = fetch_points(key)
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError) as e:
        print(f'  ⚠️ KOSIS 호출 실패({type(e).__name__}: {e}) - skip')
        return 0
    if not points:
        print('  ⚠️ 파싱 0건 - 표 구조 변경 가능성, skip')
        return 0
    added, healed = upsert(points)
    last = max(points)
    print(f'  ✓ {PRODUCT}: {len(points)}년치, 신규 {added}건, 정정 {healed}건 '
          f'(최신 {last[:4]}년 = {points[last]}조원)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
