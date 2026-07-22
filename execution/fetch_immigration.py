"""법무부 출입국 통계 (data.go.kr odcloud) → dataset.csv

★data.go.kr은 GHA(해외 IP) 차단 → 맥미니 kodex-sectors 타이머(23:30 KST)에 편승.
  키: env DATA_GO_KR_API_KEY → 로컬 .secrets 폴백 → skip.

소스 2종 (출입국·외국인정책 통계월보 원자료, 익월 하순~월말 갱신, 2022.1~):
- 15099985 월별 출입국자: 국민/외국인 × 입국/출국 × 승객/승무원
- 15100016 월별 체류자격별 체류외국인 (35개 자격, 총계행 없음)

★UDDI 함정: 파일 버전이 매월 새 UDDI로 갱신 → 스웨거 문서(infuser.odcloud.kr)에서
  paths 마지막 항목(최신 버전)을 동적 해석. 하드코딩 금지.
★컬럼·값 표기 변형: 버전에 따라 컬럼명 공백('출입국자 수')·체류자격 표기가
  'D2(유학)'/'유학D2'/'D2유학' 3형으로 섞임 → 키는 공백 제거, 자격은 정규식 코드 추출.

시리즈 5종 (만명 단위, 소수1, 달력 말일 스탬프, IMMIGRATION):
외국인 입국자·국민 출국자(승객 기준) / 체류외국인 총계·취업(E)·유학(D2·D4)
전량 재조회(각 파일 ≤2천행) 후 upsert — 개정 self-heal, 신규만이면 append.
실패는 경고 후 exit 0 (다음 run 회수). 신선도 감시: IMMIGRATION은 DATASET_IGNORE.
"""
import calendar
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CSV_PATH = 'dataset.csv'
SECRET_FILE = r'C:\Users\user\.secrets\customs_api_keys.env'
SWAGGER = 'https://infuser.odcloud.kr/oas/docs?namespace={ds}/v1'
API_BASE = 'https://api.odcloud.kr/api'
DTYPE = 'IMMIGRATION'
SCALE = 1e-4  # 명 → 만명
ND = 1

DS_ENTRY = '15099985'   # 월별 출입국자
DS_STAY = '15100016'    # 월별 체류자격별 체류외국인
QUAL_CODE = re.compile(r'([A-Z])-?(\d{1,2})')


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


def http_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    last = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode('utf-8'))
        except (urllib.error.URLError, OSError) as e:
            last = e
            if attempt == 1:
                raise
            time.sleep(2)
    raise last


def fetch_rows(ds: str, key: str) -> list:
    """스웨거에서 최신 UDDI 경로 해석 → 전체 행 (컬럼명 공백 제거 normalize)."""
    doc = http_json(SWAGGER.format(ds=ds))
    path = list(doc['paths'].keys())[-1]  # 마지막 = 최신 파일 버전
    url = (f'{API_BASE}{path}?page=1&perPage=5000'
           f'&serviceKey={urllib.parse.quote(key, safe="")}')
    payload = http_json(url)
    rows = payload.get('data', [])
    return [{k.replace(' ', ''): v for k, v in r.items()} for r in rows]


def month_end(y: int, m: int) -> str:
    return f'{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}'


def val(x: float) -> float:
    return round(x * SCALE, ND)


def build_series(key: str) -> dict:
    """{제품명: {날짜: 값}} — 실패 시 예외 전파 (호출부에서 시리즈 묶음 단위 skip)."""
    out = {}

    rows = fetch_rows(DS_ENTRY, key)
    for name, grp, direction in (('외국인 입국자', '외국인', '입국'), ('국민 출국자', '국민', '출국')):
        pts = {}
        for r in rows:
            if (r.get('국민외국인구분') == grp and r.get('출입국구분') == direction
                    and r.get('승객승무원구분') == '승객'):
                pts[month_end(int(r['년']), int(r['월']))] = val(float(r['출입국자수']))
        out[name] = pts

    rows = fetch_rows(DS_STAY, key)
    vkey = next(k for k in rows[0] if '체류외국인' in k)
    agg = {'체류외국인 총계': {}, '체류외국인 취업(E)': {}, '체류외국인 유학(D2·D4)': {}}
    for r in rows:
        d = month_end(int(r['년']), int(r['월']))
        v = float(r[vkey])
        m = QUAL_CODE.search(str(r.get('체류자격', '')))
        code = f'{m.group(1)}{int(m.group(2))}' if m else ''
        agg['체류외국인 총계'][d] = agg['체류외국인 총계'].get(d, 0.0) + v
        if code.startswith('E'):
            agg['체류외국인 취업(E)'][d] = agg['체류외국인 취업(E)'].get(d, 0.0) + v
        if code in ('D2', 'D4'):
            agg['체류외국인 유학(D2·D4)'][d] = agg['체류외국인 유학(D2·D4)'].get(d, 0.0) + v
    for name, pts in agg.items():
        out[name] = {d: val(v) for d, v in pts.items()}
    return out


def main() -> int:
    print('\n🛂 출입국 통계 수집 시작')
    key = load_key()
    if not key:
        print('  DATA_GO_KR_API_KEY 없음 - skip (no failure)')
        return 0

    try:
        series = build_series(key)
    except Exception as e:
        print(f'  ⚠️ 수집 실패({type(e).__name__}: {e}) - skip')
        return 0

    header, all_rows = None, []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, encoding='utf-8-sig') as f:
            r = csv.reader(f)
            header = next(r, None)
            all_rows = list(r)
    by_product = {}
    for i, row in enumerate(all_rows):
        if len(row) >= 3:
            by_product.setdefault(row[1], {})[row[0]] = i

    new_rows, healed = [], 0
    for name, points in series.items():
        exist = by_product.get(name, {})
        added = 0
        for d, v in sorted(points.items()):
            if d in exist:
                idx = exist[d]
                if all_rows[idx][2] != str(v):
                    all_rows[idx][2] = str(v)
                    healed += 1
            else:
                new_rows.append([d, name, v, DTYPE])
                added += 1
        if points:
            last = max(points)
            print(f'  ✓ {name}: {len(points)}점, 신규 {added}건 (최신 {last} = {points[last]})')

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
    print(f'출입국 수집 완료: 시리즈 {len(series)}종, 신규 {len(new_rows)}건, 개정 {healed}건')
    return 0


if __name__ == '__main__':
    sys.exit(main())
