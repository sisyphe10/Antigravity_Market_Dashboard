"""
data.go.kr 금융위원회_금융투자협회종합통계 API에서 고객예탁금(투자자예탁금) +
신용잔고(신용거래융자) 일별 시계열(2025-01-01~)을 수집해 kofia_stats.json으로 저장.
반대매매금액(위탁매매 미수금 대비)은 dataset.csv에 억원 단위로 적재 (market.html DATA 탭).

- 고객예탁금: getSecuritiesMarketTotalCapitalInfo .invrDpsgAmt (단위: 원)
- 반대매매금액: getSecuritiesMarketTotalCapitalInfo .brkTrdUcolMnyVsOppsTrdAmt (단위: 원)
  → dataset.csv 제품명 '반대매매금액', 데이터 타입 DEPOSIT, 억원(소수 1자리)
  ※ 위탁매매 미수금 반대매매만 집계 (신용융자 담보부족 반대매매는 상시 공표 통계 없음)
- 신용잔고:   getGrantingOfCreditBalanceInfo .crdTrFingWhl(합계) /
              .crdTrFingScrs(코스피) / .crdTrFingKosdaq(코스닥) (단위: 원)
- 날짜 필터: beginBasDt / endBasDt (YYYYMMDD) 지원 확인됨 (2026-06-10 실측)
- --dataset-begin YYYYMMDD: 반대매매금액 dataset.csv 백필용 1회성 조회 시작일
  (API 보유 시작 ~2021-10월. kofia_stats.json 창은 백필과 무관하게 BEGIN_BAS_DT~ 고정)
- API key: 환경변수 DATA_GO_KR_API_KEY 우선, 없으면
  C:\\Users\\user\\.secrets\\customs_api_keys.env 폴백 (키 값은 절대 출력하지 않음)
- 키가 없으면 exit 0 (graceful skip) — index.html 차트는 커밋된 kofia_stats.json을 읽음
"""
import os
import sys
import json
import argparse
from datetime import datetime, timezone, timedelta

import requests
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

KST = timezone(timedelta(hours=9))
BASE_URL = 'http://apis.data.go.kr/1160100/service/GetKofiaStatisticsInfoService'
OUTPUT = 'kofia_stats.json'
BEGIN_BAS_DT = '20250101'
SECRETS_ENV = r'C:\Users\user\.secrets\customs_api_keys.env'
NUM_OF_ROWS = 1000
DATASET = 'dataset.csv'
BANDAE_PRODUCT = '반대매매금액'
BANDAE_TYPE = 'DEPOSIT'


def load_api_key():
    """env 우선, 없으면 로컬 secrets 파일 폴백. 키 값은 출력 금지."""
    key = os.environ.get('DATA_GO_KR_API_KEY', '').strip()
    if key:
        return key
    try:
        with open(SECRETS_ENV, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or '=' not in line:
                    continue
                name, _, value = line.partition('=')
                if name.strip() == 'DATA_GO_KR_API_KEY':
                    return value.strip().strip('"').strip("'")
    except OSError:
        pass
    return ''


def fetch_all(key, operation, begin=BEGIN_BAS_DT):
    """오퍼레이션 하나를 페이지네이션으로 전부 수집 (API는 최신일 내림차순)."""
    end_bas_dt = datetime.now(tz=KST).strftime('%Y%m%d')
    items = []
    page = 1
    while True:
        params = {
            'serviceKey': key,
            'numOfRows': NUM_OF_ROWS,
            'pageNo': page,
            'resultType': 'json',
            'beginBasDt': begin,
            'endBasDt': end_bas_dt,
        }
        r = requests.get(f'{BASE_URL}/{operation}', params=params, timeout=60)
        r.raise_for_status()
        body = r.json().get('response', {}).get('body', {})
        total = int(body.get('totalCount') or 0)
        chunk = body.get('items') or {}
        if isinstance(chunk, dict):
            chunk = chunk.get('item') or []
        if isinstance(chunk, dict):
            chunk = [chunk]
        items.extend(chunk)
        if not chunk or len(items) >= total:
            break
        page += 1
    return items


def to_series(items, fields):
    """item 리스트 -> (오름차순 dates, {field: [원 단위 int 또는 None]})."""
    rows = {}
    for it in items:
        bas_dt = str(it.get('basDt') or '')
        if len(bas_dt) != 8:
            continue
        rows[f'{bas_dt[:4]}-{bas_dt[4:6]}-{bas_dt[6:]}'] = it
    dates = sorted(rows)
    out = {f: [] for f in fields}
    for d in dates:
        for f in fields:
            try:
                out[f].append(int(rows[d].get(f)))
            except (TypeError, ValueError):
                out[f].append(None)
    return dates, out


def append_bandae_dataset(dates, won_values):
    """반대매매금액(원)을 dataset.csv에 억원(소수 1자리)으로 append. 결측일만 추가(멱등)."""
    df = pd.read_csv(DATASET)
    existing = set(df[df['제품명'] == BANDAE_PRODUCT]['날짜'].values)
    new_rows = []
    for d, v in zip(dates, won_values):
        if v is None or d in existing:
            continue
        new_rows.append({'날짜': d, '제품명': BANDAE_PRODUCT,
                         '가격': round(v / 1e8, 1), '데이터 타입': BANDAE_TYPE})
    if new_rows:
        pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True).to_csv(
            DATASET, index=False)
    return len(new_rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dataset-begin', default=None, metavar='YYYYMMDD',
                    help='반대매매금액 dataset.csv 백필 시작일 (기본=BEGIN_BAS_DT)')
    args = ap.parse_args()

    key = load_api_key()
    if not key:
        print('DATA_GO_KR_API_KEY not set (env / .secrets) - skipping KOFIA fetch')
        return 0

    fetch_begin = min(args.dataset_begin or BEGIN_BAS_DT, BEGIN_BAS_DT)
    dep_items = fetch_all(key, 'getSecuritiesMarketTotalCapitalInfo',
                          begin=fetch_begin)
    crd_items = fetch_all(key, 'getGrantingOfCreditBalanceInfo')

    dep_dates, dep = to_series(
        dep_items, ['invrDpsgAmt', 'brkTrdUcolMnyVsOppsTrdAmt'])
    crd_dates, crd = to_series(
        crd_items, ['crdTrFingWhl', 'crdTrFingScrs', 'crdTrFingKosdaq'])

    if not dep_dates or not crd_dates:
        print('KOFIA fetch returned no data - keeping existing kofia_stats.json')
        return 1

    # kofia_stats.json 창은 백필과 무관하게 BEGIN_BAS_DT~ 고정 (랜딩 차트 호환)
    cut = f'{BEGIN_BAS_DT[:4]}-{BEGIN_BAS_DT[4:6]}-{BEGIN_BAS_DT[6:]}'
    j_dates = [d for d in dep_dates if d >= cut]
    j_values = [v for d, v in zip(dep_dates, dep['invrDpsgAmt']) if d >= cut]

    payload = {
        'updated_at': datetime.now(tz=KST).strftime('%Y-%m-%d %H:%M:%S KST'),
        'source': 'data.go.kr GetKofiaStatisticsInfoService (금투협 FreeSIS)',
        'unit': 'KRW',
        'begin': cut,
        'deposit': {'dates': j_dates, 'values': j_values},
        'credit': {
            'dates': crd_dates,
            'total': crd['crdTrFingWhl'],
            'kospi': crd['crdTrFingScrs'],
            'kosdaq': crd['crdTrFingKosdaq'],
        },
    }
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)

    added = append_bandae_dataset(dep_dates, dep['brkTrdUcolMnyVsOppsTrdAmt'])

    print(f'kofia_stats.json saved: deposit {len(j_dates)} days '
          f'({j_dates[0]}~{j_dates[-1]}), credit {len(crd_dates)} days '
          f'({crd_dates[0]}~{crd_dates[-1]})')
    print(f'dataset.csv: {BANDAE_PRODUCT} {added}행 추가 '
          f'(조회 {dep_dates[0]}~{dep_dates[-1]})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
