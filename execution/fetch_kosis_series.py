"""KOSIS 시계열 레지스트리 수집 → dataset.csv

★KOSIS API는 GHA(해외 IP)에서 타임아웃 → VM kodex-sectors 타이머(23:30 KST)에 편승.
  로컬(거주IP)·VM(오라클)은 정상. 키: env KOSIS_API_KEY → 로컬 .secrets 폴백 → skip.
  apiKey는 base64 특수문자 포함 → urlencode 필수.

시리즈 레지스트리 (전 코드 2026-07-06 실호출 검증):
- 월간(M): 달력 말일 스탬프, 기존 max-14개월부터 증분 재조회 upsert (개정 self-heal)
- 연간(A): YYYY-12-31 스탬프 (퇴직연금 — 구 fetch_pension_kosis.py 흡수)
- KOSIS 다분류 표 함정: objL 파라미터 개수를 표 축 수와 정확히 맞춰야 함
  (부족="objL 누락" err20, 초과="잘못된 요청"). 코드 미상 축은 ALL + 이름 필터.
- 값 필터: filters={'C2_NM': '총지수'} 형태로 클라이언트 측 행 선별.

실패는 시리즈 단위 경고 후 계속 (전체 실패도 exit 0 — 다음 run 회수).
신선도 감시: KOSIS_MACRO/KOSIS_SECTOR/KOSIS_PENSION 모두 DATASET_IGNORE (발표 1~2개월 지연).
"""
import calendar
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CSV_PATH = 'dataset.csv'
SECRET_FILE = r'C:\Users\user\.secrets\kosis_api_keys.env'
API = 'https://kosis.kr/openapi/Param/statisticsParameterData.do'
LOOKBACK_MONTHS = 14

# objs: objL1.. 값 ('ALL' 가능). filters: 응답 행 선별 (키=필드명, 값=일치 문자열).
SERIES = [
    # ---- 유통업체 매출 (산업통상자원부 115, 전년동월대비 %, 승인 115023) ----
    dict(name='백화점 매출증감률',   org='115', tbl='DT_115023_200', itm='T002', objs={'objL1': '0013'}, prdSe='M', start='202101', dtype='KOSIS_MACRO', nd=1),
    dict(name='대형마트 매출증감률', org='115', tbl='DT_115023_100', itm='T002', objs={'objL1': '0011'}, prdSe='M', start='202101', dtype='KOSIS_MACRO', nd=1),
    dict(name='편의점 매출증감률',   org='115', tbl='DT_115023_300', itm='T002', objs={'objL1': '0010'}, prdSe='M', start='202101', dtype='KOSIS_MACRO', nd=1),
    dict(name='SSM 매출증감률',      org='115', tbl='DT_115023_400', itm='T002', objs={'objL1': '0010'}, prdSe='M', start='202101', dtype='KOSIS_MACRO', nd=1),
    # ---- 온라인쇼핑 거래액 (통계청 101, 합계=상품군000×범위00, 백만원→조원) ----
    dict(name='온라인쇼핑 거래액', org='101', tbl='DT_1KE10041', itm='T20', objs={'objL1': '000', 'objL2': '00'}, prdSe='M', start='202101', dtype='KOSIS_MACRO', scale=1e-6, nd=2),
    # ---- 고용 (실업률, 성계0×연령계00) ----
    dict(name='실업률 (한국)', org='101', tbl='DT_1DA7102S', itm='T80', objs={'objL1': '0', 'objL2': '00'}, prdSe='M', start='202101', dtype='KOSIS_MACRO', nd=1),
    # ---- 설비투자지수 (원지수 T3, 부문축 코드 미상 → ALL+이름 필터) ----
    dict(name='설비투자지수', org='101', tbl='DT_1F70011', itm='T3', objs={'objL1': 'ALL', 'objL2': 'ALL'}, filters={'C2_NM': '총지수'}, prdSe='M', start='202101', dtype='KOSIS_MACRO', nd=1),
    # ---- 미분양주택 (국토부 116, 전국×총합×총합) ----
    dict(name='미분양주택 (전국)', org='116', tbl='DT_MLTM_2080', itm='ALL',
         objs={'objL1': '13102792722A.0001', 'objL2': '13102792722B.0001', 'objL3': '13102792722C.0001'},
         prdSe='M', start='202101', dtype='KOSIS_SECTOR', nd=0),
    # ---- 퇴직연금 적립금 (통계청 연간, 제도유형계×운용방법계, 백만원→조원) ----
    dict(name='퇴직연금 적립금', org='101', tbl='DT_1RP013', itm='ALL', objs={'objL1': '0', 'objL2': '0'}, prdSe='A', start='2015', dtype='KOSIS_PENSION', scale=1e-6, nd=1),
]


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


def month_end(yyyymm: str) -> str:
    y, m = int(yyyymm[:4]), int(yyyymm[4:6])
    return f'{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}'


def sub_months(yyyymm: str, n: int) -> str:
    y, m = int(yyyymm[:4]), int(yyyymm[4:6])
    idx = y * 12 + (m - 1) - n
    return f'{idx // 12:04d}{idx % 12 + 1:02d}'


def api_fetch(key: str, s: dict, start: str, end: str) -> list:
    params = {'method': 'getList', 'apiKey': key, 'orgId': s['org'], 'tblId': s['tbl'],
              'itmId': s['itm'], 'format': 'json', 'jsonVD': 'Y', 'prdSe': s['prdSe'],
              'startPrdDe': start, 'endPrdDe': end}
    params.update(s['objs'])
    url = API + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    last = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                payload = json.loads(r.read().decode('utf-8'))
            break
        except (urllib.error.URLError, OSError) as e:
            last = e
            if attempt == 1:
                raise
            time.sleep(2)
    if isinstance(payload, dict):
        if str(payload.get('err')) == '30':   # 데이터 없음 (기간 내 발표 전) — 정상
            return []
        raise ValueError(f"KOSIS err {payload.get('err')}: {payload.get('errMsg')}")
    return payload


def series_points(key: str, s: dict, existing_max: str | None) -> dict:
    today = date.today()
    if s['prdSe'] == 'A':
        start, end = s['start'], str(today.year)
    else:
        cur = f'{today.year:04d}{today.month:02d}'
        if existing_max:
            start = sub_months(existing_max.replace('-', '')[:6], LOOKBACK_MONTHS)
            start = max(start, s['start'])
        else:
            start = s['start']
        end = cur
    rows = api_fetch(key, s, start, end)
    out = {}
    for row in rows:
        if any(str(row.get(k, '')).strip() != v for k, v in (s.get('filters') or {}).items()):
            continue
        prd = str(row.get('PRD_DE', '')).strip()
        try:
            v = float(row['DT'])
        except (KeyError, TypeError, ValueError):
            continue
        v = v * s.get('scale', 1)
        v = round(v, s['nd']) if s['nd'] > 0 else int(round(v))
        if s['prdSe'] == 'A' and len(prd) == 4:
            out[f'{prd}-12-31'] = v
        elif s['prdSe'] == 'M' and len(prd) == 6:
            out[month_end(prd)] = v
    return out


def load_dataset():
    header, rows = None, []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, encoding='utf-8-sig') as f:
            r = csv.reader(f)
            header = next(r, None)
            rows = list(r)
    return header, rows


def main() -> int:
    print('\n📊 KOSIS 시계열 수집 시작')
    key = load_key()
    if not key:
        print('  KOSIS_API_KEY 없음 - skip (no failure)')
        return 0

    header, all_rows = load_dataset()
    by_product = {}
    for i, row in enumerate(all_rows):
        if len(row) >= 3:
            by_product.setdefault(row[1], {})[row[0]] = i

    new_rows, healed = [], 0
    ok = 0
    for s in SERIES:
        try:
            exist = by_product.get(s['name'], {})
            points = series_points(key, s, max(exist) if exist else None)
        except Exception as e:
            print(f"  ⚠️ {s['name']} 실패({type(e).__name__}: {e}) - skip")
            continue
        added = 0
        for d, v in sorted(points.items()):
            if d in exist:
                idx = exist[d]
                if all_rows[idx][2] != str(v):
                    all_rows[idx][2] = str(v)
                    healed += 1
            else:
                new_rows.append([d, s['name'], v, s['dtype']])
                added += 1
        ok += 1
        if points:
            last = max(points)
            print(f"  ✓ {s['name']}: {len(points)}점, 신규 {added}건 (최신 {last} = {points[last]})")
        else:
            print(f"  ✓ {s['name']}: 조회 구간 내 신규 발표 없음")
        time.sleep(0.4)

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
    print(f'KOSIS 수집 완료: 시리즈 {ok}/{len(SERIES)} 성공, 신규 {len(new_rows)}건, 개정 {healed}건')
    return 0


if __name__ == '__main__':
    sys.exit(main())
