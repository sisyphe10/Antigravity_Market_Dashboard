"""
WICS (Wise Industry Classification Standard) 종목별 섹터 매핑 수집
- wiseindex.com 무료 API
- 10개 대분류 섹터�� 전 종목 수집 → wics_mapping.json 저장
"""
import sys
import json
import logging
import requests
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

KST = timezone(timedelta(hours=9))

SECTORS = {
    'G10': '에너지',
    'G15': '소재',
    'G20': '산업재',
    'G25': '경기소비재',
    'G30': '필수소비재',
    'G35': '건강관리',
    'G40': '금융',
    'G45': 'IT',
    'G50': '커뮤니케이션',
    'G55': '유틸리티',
}

API_URL = 'https://www.wiseindex.com/Index/GetIndexComponets'


def fetch_wics(date_str=None):
    """전 종목 WICS 섹터 매핑 수집"""
    if not date_str:
        # 최근 거래일 (주말 보정)
        today = datetime.now(tz=KST).date()
        d = today - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        date_str = d.strftime('%Y%m%d')

    mapping = {}  # code -> sector
    total = 0

    for sec_cd, sec_name in SECTORS.items():
        try:
            r = requests.get(API_URL, params={
                'ceil_yn': 0, 'dt': date_str, 'sec_cd': sec_cd
            }, timeout=30)
            items = r.json().get('list', [])
            for item in items:
                code = item.get('CMP_CD', '')
                if code:
                    mapping[code] = sec_name
            total += len(items)
            logging.info(f"  {sec_name} ({sec_cd}): {len(items)}종목")
        except Exception as e:
            logging.warning(f"  {sec_name} ({sec_cd}) 실패: {e}")

    logging.info(f"완료: {len(mapping)}종목 (기준일: {date_str})")

    with open('wics_mapping.json', 'w', encoding='utf-8') as f:
        json.dump({'date': date_str, 'mapping': mapping}, f, ensure_ascii=False)

    return mapping


if __name__ == '__main__':
    fetch_wics()
