"""
WICS (Wise Industry Classification Standard) 종목별 소분류 매핑 수집
- wiseindex.com 무료 API
- 27개 소분류 섹터별 전 종목 수집 → wics_mapping.json 저장
"""
import sys
import json
import logging
import requests
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

KST = timezone(timedelta(hours=9))

# WICS 소분류 27개
SUB_SECTORS = [
    'G1010', 'G1510',
    'G2010', 'G2020', 'G2030',
    'G2510', 'G2520', 'G2530', 'G2550', 'G2560',
    'G3010', 'G3020', 'G3030',
    'G3510', 'G3520',
    'G4010', 'G4020', 'G4030', 'G4040', 'G4050',
    'G4510', 'G4520', 'G4530', 'G4540',
    'G5010', 'G5020',
    'G5510',
]

API_URL = 'https://www.wiseindex.com/Index/GetIndexComponets'


def fetch_wics(date_str=None):
    """전 종목 WICS 소분류 매핑 수집"""
    if not date_str:
        today = datetime.now(tz=KST).date()
        d = today - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        date_str = d.strftime('%Y%m%d')

    mapping = {}  # code -> sub_sector name

    for sec_cd in SUB_SECTORS:
        try:
            r = requests.get(API_URL, params={
                'ceil_yn': 0, 'dt': date_str, 'sec_cd': sec_cd
            }, timeout=30)
            items = r.json().get('list', [])
            if not items:
                continue
            sub_name = items[0].get('IDX_NM_KOR', '').replace('WICS ', '')
            for item in items:
                code = item.get('CMP_CD', '')
                if code:
                    mapping[code] = sub_name
            logging.info(f"  {sub_name} ({sec_cd}): {len(items)}종목")
        except Exception as e:
            logging.warning(f"  {sec_cd} 실패: {e}")

    logging.info(f"완료: {len(mapping)}종목 (기준일: {date_str})")

    with open('wics_mapping.json', 'w', encoding='utf-8') as f:
        json.dump({'date': date_str, 'mapping': mapping}, f, ensure_ascii=False)

    return mapping


if __name__ == '__main__':
    fetch_wics()
