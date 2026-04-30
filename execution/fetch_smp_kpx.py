"""KPX 육지 SMP 일별 가중평균 수집

Source: https://new.kpx.or.kr/smpInland.es?mid=a10606080100&device=pc
- 페이지에 issue_date 기준 직전 7일치 시간대별 SMP + 가중평균 row 포함
- WAF가 엑셀 다운로드 차단 → HTML 파싱으로 우회

수집 모드:
- crawl_kpx_smp()        : market_crawler.py에서 호출. 직전 7일만 fetch (daily 누적용)
- python fetch_smp_kpx.py            : 1년치 backfill 후 dataset.csv에 append
- python fetch_smp_kpx.py --backfill : 동일 (명시용)

저장: dataset.csv 에 (날짜, 제품명='SMP', 가격, 데이터 타입='SMP_KPX') 형식
중복(날짜+제품명)은 save_to_csv가 자동 제거.
"""
import csv
import os
import re
import sys
import time
from datetime import date, timedelta
import urllib.request
import urllib.error

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

URL_BASE = 'https://new.kpx.or.kr/smpInland.es?mid=a10606080100&device=pc'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}
PRODUCT_NAME = 'SMP'
DATA_TYPE = 'SMP_KPX'


def fetch_page(issue_date: str) -> str:
    url = f'{URL_BASE}&issue_date={issue_date}'
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode('utf-8', errors='replace')


def parse_page(html: str, anchor_date: date) -> list[tuple[str, float]]:
    """페이지에서 7개 (날짜, 가중평균) 튜플 추출."""
    headers = re.findall(r'<th[^>]*>(\d{2})\.(\d{2})<br', html, re.S)
    if len(headers) < 7:
        return []
    headers = headers[:7]

    avg_block = re.search(r'<td>가중평균</td>(.*?)</tr>', html, re.S)
    if not avg_block:
        return []
    avg_vals = re.findall(r'<td>([\d.]+)</td>', avg_block.group(1))
    if len(avg_vals) < 7:
        return []
    avg_vals = avg_vals[:7]

    out = []
    for (mm, dd), v in zip(headers, avg_vals):
        m, d = int(mm), int(dd)
        # 헤더에는 연도가 없음 → anchor_date 기준 역추정 (월이 더 크면 전년)
        y = anchor_date.year
        if m > anchor_date.month:
            y -= 1
        elif m == anchor_date.month and d > anchor_date.day:
            y -= 1
        out.append((f'{y:04d}-{m:02d}-{d:02d}', float(v)))
    return out


def collect_range(start: date, end: date, sleep_sec: float = 0.6) -> list[tuple[str, float]]:
    """end → start 방향으로 7일씩 anchor를 점프하며 수집. 중복 제거."""
    collected: dict[str, float] = {}
    cur = end
    page_count = 0
    while cur >= start:
        try:
            rows = parse_page(fetch_page(cur.isoformat()), cur)
            for d, v in rows:
                if d not in collected:
                    collected[d] = v
            page_count += 1
            print(f'  [{page_count:02d}] anchor={cur} → {len(rows)}일 (누적 {len(collected)})')
        except (urllib.error.URLError, ValueError) as e:
            print(f'  ⚠️ {cur} 실패: {e}')
        cur -= timedelta(days=7)
        time.sleep(sleep_sec)

    rows = sorted(((d, v) for d, v in collected.items() if start.isoformat() <= d <= end.isoformat()),
                  key=lambda x: x[0])
    return rows


def append_to_dataset(rows: list[tuple[str, float]]) -> int:
    """dataset.csv 에 (날짜, 제품명, 가격, 데이터 타입) 추가. 중복 제외 후 신규 건수 반환.

    market_crawler.save_to_csv 와 동일 로직 (utf-8-sig, 헤더: 날짜,제품명,가격,데이터 타입)
    """
    csv_path = 'dataset.csv'
    existing_keys = set()
    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            r = csv.reader(f)
            next(r, None)
            for row in r:
                if len(row) >= 2:
                    existing_keys.add((row[0], row[1]))

    new_rows = []
    for d, v in rows:
        key = (d, PRODUCT_NAME)
        if key not in existing_keys:
            new_rows.append([d, PRODUCT_NAME, v, DATA_TYPE])
            existing_keys.add(key)

    if not new_rows:
        return 0

    write_header = not os.path.exists(csv_path)
    with open(csv_path, 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(['날짜', '제품명', '가격', '데이터 타입'])
        w.writerows(new_rows)
    return len(new_rows)


# ------------------------------------------------------------
# 두 가지 진입점
# ------------------------------------------------------------
def crawl_kpx_smp() -> None:
    """daily 누적용 — 오늘부터 직전 7일만 fetch (market_crawler.py에서 호출)."""
    print(f"\n⚡ KPX 육지 SMP 크롤링 시작")
    today = date.today()
    rows = collect_range(today - timedelta(days=6), today, sleep_sec=0.3)
    if not rows:
        print('  ⚠️ KPX SMP 수집 결과 없음')
        return
    added = append_to_dataset(rows)
    print(f'✓ {PRODUCT_NAME}: {len(rows)}일 fetch, {added}건 신규 저장 (최신 {rows[-1][0]} = {rows[-1][1]})')


def backfill_one_year() -> None:
    """초기 1년치 backfill — 단독 실행용."""
    today = date.today()
    start = today - timedelta(days=365)
    print(f'=== KPX SMP 1년 backfill: {start} ~ {today} ===')
    rows = collect_range(start, today)
    if not rows:
        print('⚠️ 수집 결과 없음')
        return
    print(f'\n최종 {len(rows)}일치 ({rows[0][0]} ~ {rows[-1][0]})')
    added = append_to_dataset(rows)
    print(f'✅ dataset.csv: {added}건 신규 저장')


if __name__ == '__main__':
    backfill_one_year()
