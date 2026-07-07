"""일본 CAPEX 지표 수집 → dataset.csv (dtype JP_CAPEX, 그룹 CAPEX)

시리즈 3종 (월간, 百万円→억엔 /100):
1. SEAJ 반도체장비 판매고   — 일본제 반도체 제조장치 판매액 3개월이동평균.
   소스: https://www.seaj.or.jp/statistics/ (Shift-JIS) 백넘버 xls.
   ★파일명이 매월 랜덤 숫자(예: 2687986571013.xls)로 회전 → 페이지에서
   라벨 행("販売高速報値…半導体" + .xls)을 파싱해 추출. 2005-01~ 전체
   히스토리가 한 파일에 있어 매 run 전체 upsert(개정 self-heal).
   수주(Bookings)/BB레시오는 2015년경 공표 중단이라 판매액만 사용.
2. JMTBA 공작기계 수주총액 / 3. JMTBA 공작기계 외수
   속보: uploads/{YYYY}/{MM}/sokuhou{발표YYMM}.pdf — 총액 행이 무라벨이라
   うち内需+うち外需 합산으로 총액 산출(2026-05 검증: 45,036+131,797=176,833).
   확보: kakuhou{데이터YYMM}.pdf — ★속보와 YYMM 의미가 다름(속보=발표월,
   확보=데이터월). pypdf layout 모드 p0의 外需/受注総額 행 파싱.
   과거 속보 PDF는 삭제됨(404) → 백필·개정 self-heal은 확보 경유.
   매 run: 속보(최신월) + 확보 최근 3건 upsert(속보값→확보값 자동 개정).

실행 경로: VM kodex-sectors 타이머(23:30 KST) 편승 — GHA 해외IP 차단 리스크
회피(KOSIS 전례). 의존성: pandas+xlrd(xls), pypdf. 실패는 소스 단위 격리,
exit 0 (다음 run 회수). 신선도 감시: JP_CAPEX는 DATASET_IGNORE (월간 지연).

usage: fetch_japan_capex.py [--backfill]   # 확보 2301~ 전체 순회
"""
import csv
import io
import os
import re
import sys
import time
import urllib.request

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CSV_PATH = 'dataset.csv'
DTYPE = 'JP_CAPEX'
SEAJ_NAME = 'SEAJ 반도체장비 판매고'
JMTBA_TOTAL = 'JMTBA 공작기계 수주총액'
JMTBA_FOREIGN = 'JMTBA 공작기계 외수'
JMTBA_BACKFILL_START = 2301   # kakuhou YYMM (데이터월)

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}


def http_get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    last = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except OSError as e:
            last = e
            time.sleep(3)
    raise last


def month_end_str(y: int, m: int) -> str:
    import calendar
    return f'{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}'


def oku_yen(million_yen: float) -> float:
    return round(million_yen / 100.0, 1)   # 百万円 → 억엔


# ---------------------------------------------------------------- SEAJ
def fetch_seaj() -> dict:
    """반도체 제조장치 판매고 3MMA 전체 히스토리 {date: 억엔}."""
    import pandas as pd
    page = http_get('https://www.seaj.or.jp/statistics/').decode('shift_jis', errors='replace')
    # 라벨 "販売高速報値(3ヶ月平均) <br>半導体" 행의 xls만 (PDF 월보·FPD 행 배제)
    m = re.search(r'販売高速報値[^<]*<br>\s*半導体\s*</td>\s*<td[^>]*>\s*<a href="(\d+\.xls)"', page)
    if not m:
        raise ValueError('SEAJ 백넘버 xls 링크 미발견 (페이지 개편 의심)')
    xls = http_get('https://www.seaj.or.jp/statistics/' + m.group(1))
    df = pd.read_excel(io.BytesIO(xls), sheet_name='半導体BBレシオ', header=None)
    out = {}
    year = None
    for _, row in df.iloc[6:].iterrows():
        y, mo, bill = row[0], row[1], row[4]
        if pd.notna(y):
            try:
                year = int(re.sub(r'[^0-9]', '', str(y)) or 0)
            except (TypeError, ValueError):
                continue
        if year is None or pd.isna(mo) or pd.isna(bill):
            continue
        try:
            # ★월 셀에 개정 표기가 붙음 (예: '8R') — 숫자만 추출
            mo = int(re.sub(r'[^0-9]', '', str(mo)) or 0)
            bill = float(bill)
        except (TypeError, ValueError):
            continue
        if not (1 <= mo <= 12) or bill <= 0:
            continue
        out[month_end_str(year, mo)] = oku_yen(bill)
    if len(out) < 100:
        raise ValueError(f'SEAJ 파싱 이상: {len(out)}점 (기대 250+)')
    return out


# ---------------------------------------------------------------- JMTBA
def _jmtba_page() -> str:
    return http_get('https://www.jmtba.or.jp/statistics/').decode('utf-8', errors='replace')


def parse_sokuhou(pdf: bytes) -> tuple:
    """속보 PDF → (date, total억엔, foreign억엔). 총액=내수+외수 합산."""
    from pypdf import PdfReader
    text = '\n'.join((p.extract_text() or '') for p in PdfReader(io.BytesIO(pdf)).pages)
    dm = re.search(r'(\d{4})年\s*(\d{1,2})月分', text)
    dom = re.search(r'うち内需\s*([\d,]+)', text)
    for_ = re.search(r'うち外需\s*([\d,]+)', text)
    if not (dm and dom and for_):
        raise ValueError('JMTBA 속보 PDF 파싱 실패 (레이아웃 변경 의심)')
    d = int(dom.group(1).replace(',', ''))
    f = int(for_.group(1).replace(',', ''))
    date = month_end_str(int(dm.group(1)), int(dm.group(2)))
    return date, oku_yen(d + f), oku_yen(f)


def parse_kakuhou(pdf: bytes, yymm: int) -> tuple:
    """확보 PDF p0 layout → (date, total억엔, foreign억엔). 내수+외수=총액 정합검증.

    ★레이아웃 2종: ~2025-03분은 라벨이 행 앞(内需計 43,402 …),
    2025-04분~은 라벨이 행 끝(34,379 … 100.4内需計). 라인 단위로 라벨을
    찾고 그 행의 첫 콤마 숫자(당월값 컬럼)를 취해 양쪽 모두 처리.
    """
    from pypdf import PdfReader
    t = PdfReader(io.BytesIO(pdf)).pages[0].extract_text(extraction_mode='layout') or ''
    dom = for_ = total = None
    for line in t.splitlines():
        ls = re.sub(r'[\s　]', '', line)
        nums = re.findall(r'\d{1,3}(?:,\d{3})+', line)   # 콤마 숫자만 (행번호 1-11 배제)
        if not nums:
            continue
        v = int(nums[0].replace(',', ''))
        if '受注総額' in ls:
            total = v
        elif '内需計' in ls:
            dom = v
        elif '外需' in ls:
            for_ = v
    if for_ is None or total is None:
        raise ValueError('JMTBA 확보 PDF 파싱 실패')
    if dom is not None and abs(dom + for_ - total) > 2:   # 반올림 허용
        raise ValueError(f'JMTBA 확보 정합 실패: {dom}+{for_}!={total}')
    y, m = 2000 + yymm // 100, yymm % 100
    return month_end_str(y, m), oku_yen(total), oku_yen(for_)


def fetch_jmtba(backfill: bool) -> tuple:
    """(total {date: 억엔}, foreign {date: 억엔})"""
    page = _jmtba_page()
    total, foreign = {}, {}
    # 확보 (백필 or 최근 3건 개정 self-heal)
    kaku = sorted(set(re.findall(
        r'href="(https://www\.jmtba\.or\.jp/wjmtbap/wp-content/uploads/\d{4}/\d{2}/kakuhou(\d{4})\.pdf)"',
        page)), key=lambda x: int(x[1]))
    kaku = [(u, int(s)) for u, s in kaku if int(s) >= JMTBA_BACKFILL_START]
    if not backfill:
        kaku = kaku[-3:]
    for url, yymm in kaku:
        try:
            d, t, f = parse_kakuhou(http_get(url), yymm)
            total[d], foreign[d] = t, f
        except Exception as e:
            print(f'  ⚠️ kakuhou{yymm} 실패({e}) - skip')
        time.sleep(0.5)
    # 속보 (최신월 — 확보보다 뒤 데이터, 확보 나오면 다음 run에 덮임)
    sok = re.search(
        r'href="(https://www\.jmtba\.or\.jp/wjmtbap/wp-content/uploads/\d{4}/\d{2}/sokuhou\d{4}\.pdf)"',
        page)
    if sok:
        d, t, f = parse_sokuhou(http_get(sok.group(1)))
        # 확보가 이미 커버한 달이면 확보값 우선
        total.setdefault(d, t)
        foreign.setdefault(d, f)
    elif not total:
        raise ValueError('JMTBA 속보 링크 미발견 (페이지 개편 의심)')
    return total, foreign


# ---------------------------------------------------------------- upsert
def upsert(series: dict) -> None:
    """series: {name: {date: value}} → dataset.csv 개정/추가."""
    header, rows = None, []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, encoding='utf-8-sig') as fh:
            r = csv.reader(fh)
            header = next(r, None)
            rows = list(r)
    index = {}
    for i, row in enumerate(rows):
        if len(row) >= 3:
            index.setdefault(row[1], {})[row[0]] = i

    new_rows, healed = [], 0
    for name, points in series.items():
        exist = index.get(name, {})
        added = 0
        for d, v in sorted(points.items()):
            if d in exist:
                if rows[exist[d]][2] != str(v):
                    rows[exist[d]][2] = str(v)
                    healed += 1
            else:
                new_rows.append([d, name, v, DTYPE])
                added += 1
        if points:
            last = max(points)
            print(f'  ✓ {name}: {len(points)}점, 신규 {added}건 (최신 {last} = {points[last]:,}억엔)')

    if healed:
        with open(CSV_PATH, 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.writer(fh)
            if header:
                w.writerow(header)
            w.writerows(rows)
            w.writerows(new_rows)
    elif new_rows:
        with open(CSV_PATH, 'a', newline='', encoding='utf-8-sig') as fh:
            csv.writer(fh).writerows(new_rows)
    print(f'JP CAPEX 완료: 신규 {len(new_rows)}건, 개정 {healed}건')


def main() -> int:
    backfill = '--backfill' in sys.argv
    print('\n🇯🇵 일본 CAPEX 지표 수집 시작' + (' (백필)' if backfill else ''))
    series = {}
    try:
        series[SEAJ_NAME] = fetch_seaj()
    except Exception as e:
        print(f'  ⚠️ SEAJ 실패({type(e).__name__}: {e}) - skip')
    try:
        total, foreign = fetch_jmtba(backfill)
        series[JMTBA_TOTAL] = total
        series[JMTBA_FOREIGN] = foreign
    except Exception as e:
        print(f'  ⚠️ JMTBA 실패({type(e).__name__}: {e}) - skip')
    if series:
        upsert(series)
    return 0


if __name__ == '__main__':
    sys.exit(main())
