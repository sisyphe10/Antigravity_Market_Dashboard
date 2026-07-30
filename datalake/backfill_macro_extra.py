# -*- coding: utf-8 -*-
"""dataset.csv 수집기가 커버하지 못하는 '과거 이력'을 macro_series 로 직접 백필 (2026-07-30).

★배경: dataset.csv 는 수집 시작 시점부터만 쌓인다(SMP 2025-04~, VKOSPI 2025-01~).
  그래서 RoC²(YoY lag 12개월 + MA3 → 연속 16버킷 필요)가 SMP 1점·VKOSPI 4점밖에 안 나왔다.
  ★일별 전량을 dataset.csv 에 백필하면 안 된다 — market.html 의 cmbData 축이 2024년부터만
   일별이라, 2013/2009년까지 넣으면 축이 696→5,000일로 늘고 184종 전부가 그 길이의 배열을
   갖게 되어 인라인 JSON 이 폭발한다.
  → 그래서 **레이크(macro_series)에만** 넣는다. dataset.csv 는 손대지 않는다.
    accumulate_macro_series.py 는 upsert 이고 삭제를 하지 않으므로 이 행들은 지워지지 않는다.
    build_roc_history.py 가 macro_series 에서 기간말값을 읽어 RoC² 에 쓴다.

원천·상한 (2026-07-30 실측):
  SMP    = KPX smpInland.es. **2013년까지** 열림(2012 이전은 빈 응답). 한 페이지=직전 7일.
  VKOSPI = KIS 업종 U/0503 inquire-daily-indexchartprice. **1회 50건 상한**(요청 기간과 무관,
           끝날짜 기준 역방향 50영업일). 산출 개시 2009년. 끝날짜를 밀며 루프.

사용: venv/bin/python3 datalake/backfill_macro_extra.py [--only smp|vkospi] [--from 2013-01-01]
"""
import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, 'execution'))
from dl_common import merge_into_year_files  # noqa: E402

DATASET = 'macro_series'


def backfill_smp(start: date, end: date, pace: float = 0.6):
    """KPX 육지 SMP 일별 가중평균. 기존 fetch_smp_kpx 의 파서를 그대로 재사용."""
    import fetch_smp_kpx as smp
    got, cur, pages, empty_streak = {}, end, 0, 0
    while cur >= start:
        try:
            rows = smp.parse_page(smp.fetch_page(cur.isoformat()), cur)
        except Exception as e:
            print(f'  ! {cur}: {type(e).__name__}: {e}', flush=True)
            rows = []
        hit = 0
        for d, v in rows:
            if v:                      # 당일 미확정은 0.0 으로 오므로 제외
                got[d] = float(v); hit += 1
        pages += 1
        empty_streak = 0 if hit else empty_streak + 1
        if pages % 50 == 0:
            print(f'  SMP {pages}페이지 … 현재 {len(got):,}일치 (진행 {cur})', flush=True)
        # 과거 끝(2012 이전)에 닿으면 빈 페이지가 연속된다 — 20회면 중단
        if empty_streak >= 20:
            print(f'  SMP: 빈 페이지 {empty_streak}연속 → {cur} 에서 중단(원천 이력 끝)', flush=True)
            break
        cur -= timedelta(days=7)
        time.sleep(pace)
    print(f'  SMP 완료: {len(got):,}일치, {pages}페이지', flush=True)
    return [(d, 'SMP', v, 'SMP_KPX') for d, v in sorted(got.items())]


def backfill_vkospi(start: date, end: date, pace: float = 0.35):
    """KIS 업종 U/0503. 1회 50건 상한 → 끝날짜를 반환 최소일-1 로 밀며 역방향 루프."""
    from kis_token import kis_get
    got, cur, calls, empty_streak = {}, end, 0, 0
    while cur >= start:
        s8 = (cur - timedelta(days=120)).strftime('%Y%m%d')   # 50영업일 여유
        e8 = cur.strftime('%Y%m%d')
        try:
            j = kis_get('/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice',
                        'FHKUP03500100',
                        {'FID_COND_MRKT_DIV_CODE': 'U', 'FID_INPUT_ISCD': '0503',
                         'FID_INPUT_DATE_1': s8, 'FID_INPUT_DATE_2': e8,
                         'FID_PERIOD_DIV_CODE': 'D'})
            out2 = [r for r in (j.get('output2') or []) if r.get('stck_bsop_date')]
        except Exception as e:
            print(f'  ! VKOSPI {e8}: {type(e).__name__}: {e}', flush=True)
            out2 = []
        calls += 1
        hit = 0
        oldest = None
        for r in out2:
            d8 = r['stck_bsop_date']
            try:
                v = float(str(r.get('bstp_nmix_prpr') or '').replace(',', ''))
            except ValueError:
                continue
            if v <= 0:
                continue
            iso = f'{d8[:4]}-{d8[4:6]}-{d8[6:]}'
            got[iso] = v; hit += 1
            if oldest is None or d8 < oldest:
                oldest = d8
        empty_streak = 0 if hit else empty_streak + 1
        if calls % 20 == 0:
            print(f'  VKOSPI {calls}회 … 현재 {len(got):,}일치 (진행 {cur})', flush=True)
        if empty_streak >= 5:
            print(f'  VKOSPI: 빈 응답 {empty_streak}연속 → {cur} 에서 중단(원천 이력 끝)', flush=True)
            break
        # 다음 창 = 이번 응답의 최고(最古)일 하루 전. 못 받았으면 60일 점프로 탈출.
        cur = (datetime.strptime(oldest, '%Y%m%d').date() - timedelta(days=1)) if oldest \
            else (cur - timedelta(days=60))
        time.sleep(pace)
    print(f'  VKOSPI 완료: {len(got):,}일치, {calls}회 호출', flush=True)
    return [(d, 'VKOSPI', v, 'INDEX_KR') for d, v in sorted(got.items())]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', choices=['smp', 'vkospi'])
    ap.add_argument('--from', dest='start', default='2013-01-01')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = date.today()

    import pandas as pd
    rows = []
    if args.only in (None, 'vkospi'):
        print('=== VKOSPI (KIS U/0503) ===', flush=True)
        rows += backfill_vkospi(max(start, date(2009, 1, 1)), end)
    if args.only in (None, 'smp'):
        print('=== SMP (KPX) ===', flush=True)
        rows += backfill_smp(max(start, date(2013, 1, 1)), end)

    if not rows:
        print('! 수집 결과 없음')
        return 1
    df = pd.DataFrame(rows, columns=['date', 'series', 'value', 'dtype'])
    df['date'] = pd.to_datetime(df['date'])
    for nm, g in df.groupby('series'):
        print(f'  {nm}: {len(g):,}행 {g["date"].min().date()} ~ {g["date"].max().date()}')
    if args.dry_run:
        print('(dry-run — 적재 생략)')
        return 0
    res = merge_into_year_files(DATASET, df, ['date', 'series'])
    print(f'적재: 연도 {len(res)}개 / 순증 {sum(f - b for b, f in res.values()):+,}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
