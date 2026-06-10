"""
data.go.kr 금융위원회_금융투자협회종합통계 API에서 고객예탁금(투자자예탁금) +
신용잔고(신용거래융자) 일별 시계열(2025-01-01~)을 수집해 kofia_stats.json으로 저장.

- 고객예탁금: getSecuritiesMarketTotalCapitalInfo .invrDpsgAmt (단위: 원)
- 신용잔고:   getGrantingOfCreditBalanceInfo .crdTrFingWhl(합계) /
              .crdTrFingScrs(코스피) / .crdTrFingKosdaq(코스닥) (단위: 원)
- 날짜 필터: beginBasDt / endBasDt (YYYYMMDD) 지원 확인됨 (2026-06-10 실측)
- API key: 환경변수 DATA_GO_KR_API_KEY 우선, 없으면
  C:\\Users\\user\\.secrets\\customs_api_keys.env 폴백 (키 값은 절대 출력하지 않음)
- 키가 없으면 exit 0 (graceful skip) — index.html 차트는 커밋된 kofia_stats.json을 읽음
"""
import os
import sys
import json
from datetime import datetime, timezone, timedelta

import requests

sys.stdout.reconfigure(encoding='utf-8')

KST = timezone(timedelta(hours=9))
BASE_URL = 'http://apis.data.go.kr/1160100/service/GetKofiaStatisticsInfoService'
OUTPUT = 'kofia_stats.json'
BEGIN_BAS_DT = '20250101'
SECRETS_ENV = r'C:\Users\user\.secrets\customs_api_keys.env'
NUM_OF_ROWS = 1000


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


def fetch_all(key, operation):
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
            'beginBasDt': BEGIN_BAS_DT,
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


def main():
    key = load_api_key()
    if not key:
        print('DATA_GO_KR_API_KEY not set (env / .secrets) - skipping KOFIA fetch')
        return 0

    dep_items = fetch_all(key, 'getSecuritiesMarketTotalCapitalInfo')
    crd_items = fetch_all(key, 'getGrantingOfCreditBalanceInfo')

    dep_dates, dep = to_series(dep_items, ['invrDpsgAmt'])
    crd_dates, crd = to_series(
        crd_items, ['crdTrFingWhl', 'crdTrFingScrs', 'crdTrFingKosdaq'])

    if not dep_dates or not crd_dates:
        print('KOFIA fetch returned no data - keeping existing kofia_stats.json')
        return 1

    payload = {
        'updated_at': datetime.now(tz=KST).strftime('%Y-%m-%d %H:%M:%S KST'),
        'source': 'data.go.kr GetKofiaStatisticsInfoService (금투협 FreeSIS)',
        'unit': 'KRW',
        'begin': f'{BEGIN_BAS_DT[:4]}-{BEGIN_BAS_DT[4:6]}-{BEGIN_BAS_DT[6:]}',
        'deposit': {'dates': dep_dates, 'values': dep['invrDpsgAmt']},
        'credit': {
            'dates': crd_dates,
            'total': crd['crdTrFingWhl'],
            'kospi': crd['crdTrFingScrs'],
            'kosdaq': crd['crdTrFingKosdaq'],
        },
    }
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f'kofia_stats.json saved: deposit {len(dep_dates)} days '
          f'({dep_dates[0]}~{dep_dates[-1]}), credit {len(crd_dates)} days '
          f'({crd_dates[0]}~{crd_dates[-1]})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
