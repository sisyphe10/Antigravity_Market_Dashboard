"""SiliconData Silicon Index 3종 수집 (LLM Token / H100 GPU Rental / RAM)

Source: https://portal.silicondata.com/{token,gpu,ram}-index-chart
- www.silicondata.com 제품 페이지가 iframe으로 임베드하는 포털 차트 페이지.
- Next.js RSC flight payload에 직전 7일치 (날짜, 값)가 escaped JSON으로 포함:
    indexes\":{\"YYYY-MM-DD\":\"1.6261\", ...}  +  ending_date\":\"YYYY-MM-DD\"
  raw HTML에 백슬래시+따옴표가 문자 그대로 있으므로 unescape 없이 정규식 직접 매칭.
- 공개 범위는 7일 롤링 윈도우 (전체 히스토리는 유료) → 데일리 수집으로 누적.
  7일 겹침 구간은 소스가 값을 정정할 수 있어 다르면 덮어쓰기(self-heal).
  7일 초과 연속 결측 시 해당 구간은 영구 손실 — check_data_freshness.py가
  calendar 5일 임계로 손실 전에 경보 (지수는 주말 포함 매일 산출, 발행 1~2일 지연).

수집 모드:
- crawl_silicondata_indexes() : market_crawler.py에서 호출 (23:00 KST daily_crawl)
- python fetch_silicondata_index.py : 단독 실행 (동일 동작 — backfill 불가)

저장: dataset.csv 에 (날짜, 제품명, 가격, 데이터 타입) — 시리즈별 데이터 타입 분리
(SDLLMTK/SDH100RT/SD_RAM)로 check_data_freshness가 개별 신선도 추적.
"""
import csv
import os
import re
import sys
import time
import urllib.error
import urllib.request

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CSV_PATH = 'dataset.csv'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
}
# slug → (제품명, 데이터 타입, 단위 메모)
SILICONDATA_INDEXES = {
    'token-index-chart': ('LLM Token Index', 'SDLLMTK', 'USD/1M tokens'),
    'gpu-index-chart':   ('H100 GPU Rental', 'SDH100RT', 'USD/hr'),
    'ram-index-chart':   ('RAM Index',       'SD_RAM',   'index'),
}


def fetch_page(slug: str) -> str:
    url = f'https://portal.silicondata.com/{slug}'
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='replace')


def parse_indexes(html: str) -> tuple[dict[str, float], str | None]:
    """RSC payload에서 ({날짜: 값}, ending_date) 추출. 구조 변경 시 빈 dict."""
    m = re.search(r'indexes\\":\{([^}]*)\}', html)
    if not m:
        return {}, None
    out = {}
    for d, v in re.findall(r'\\"(\d{4}-\d{2}-\d{2})\\":\\"([\d.]+)\\"', m.group(1)):
        try:
            fv = float(v)
        except ValueError:
            continue
        if fv > 0:
            out[d] = fv
    e = re.search(r'ending_date\\":\\"(\d{4}-\d{2}-\d{2})', html)
    return out, (e.group(1) if e else None)


def upsert_dataset(product: str, data_type: str, fetched: dict[str, float]) -> tuple[int, int]:
    """dataset.csv에 (날짜, 제품명, 가격, 데이터 타입) upsert.

    반환 (신규 건수, 정정 건수). 7일 공개 창 안(=이번 fetch에 포함된 날짜)의
    기존 행은 값이 다르면 fetch값으로 덮어씀. 창 밖 과거 행은 불변.
    """
    existing_keys = set()
    all_rows = []
    header = None
    healed = 0
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
            r = csv.reader(f)
            header = next(r, None)
            for row in r:
                if len(row) >= 3 and row[1] == product:
                    existing_keys.add((row[0], row[1]))
                    if row[0] in fetched:
                        try:
                            same = abs(float(row[2]) - fetched[row[0]]) < 1e-9
                        except ValueError:
                            same = False
                        if not same:
                            row[2] = str(fetched[row[0]])
                            healed += 1
                elif len(row) >= 2:
                    existing_keys.add((row[0], row[1]))
                all_rows.append(row)

    new_rows = [[d, product, v, data_type]
                for d, v in sorted(fetched.items())
                if (d, product) not in existing_keys]

    if healed:
        # 기존 행 수정은 append 불가 → 전체 재작성 (fetch_smp_kpx self-heal 패턴)
        with open(CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            if header:
                w.writerow(header)
            w.writerows(all_rows)
            w.writerows(new_rows)
    elif new_rows:
        write_header = not os.path.exists(CSV_PATH)
        with open(CSV_PATH, 'a', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(['날짜', '제품명', '가격', '데이터 타입'])
            w.writerows(new_rows)
    return len(new_rows), healed


def crawl_silicondata_indexes() -> None:
    print('\n🔌 SiliconData Silicon Index 크롤링 시작')
    for slug, (product, data_type, unit) in SILICONDATA_INDEXES.items():
        try:
            fetched, ending_date = parse_indexes(fetch_page(slug))
        except (urllib.error.URLError, OSError) as e:
            print(f'  ⚠️ {product} fetch 실패 (계속 진행): {e}')
            continue
        if not fetched:
            print(f'  ⚠️ {product}: 데이터 미발견 — 포털 페이지 구조 변경 가능성')
            continue
        added, healed = upsert_dataset(product, data_type, fetched)
        last = max(fetched)
        extra = f', {healed}건 정정' if healed else ''
        print(f'  ✓ {product}: {len(fetched)}일 fetch, {added}건 신규{extra} '
              f'(최신 {last} = {fetched[last]} {unit}, ending_date={ending_date})')
        time.sleep(0.5)


if __name__ == '__main__':
    crawl_silicondata_indexes()
