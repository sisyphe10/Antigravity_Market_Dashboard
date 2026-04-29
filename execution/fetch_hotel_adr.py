"""호텔 ADR 일별 수집 (Booking.com 단독)

각 호텔의 entry 객실 = 페이지 내 최저가 객실 가격을 매일 추적.
Lead time +7/+14/+30일 기준 가격을 hotel_adr.csv 누적.

실행: python execution/fetch_hotel_adr.py
"""
import sys
import os
import re
import csv
import time
import datetime

sys.stdout.reconfigure(encoding='utf-8')

# ────────────────────────────────────────────────────────────
# 호텔 10개 (Booking.com URL — entry 객실은 페이지 최저가 자동 픽업)
# ────────────────────────────────────────────────────────────
HOTEL_MAPPINGS = [
    # 서울 (5)
    {'hotel': '시그니엘 서울',       'city': '서울', 'grade': 'Lux', 'booking_url': 'https://www.booking.com/hotel/kr/signiel-seoul.ko.html'},
    {'hotel': '포시즌스 호텔 서울',  'city': '서울', 'grade': 'Lux', 'booking_url': 'https://www.booking.com/hotel/kr/four-seasons-seoul.ko.html'},
    {'hotel': '그랜드 하얏트 서울',  'city': '서울', 'grade': '5*',  'booking_url': 'https://www.booking.com/hotel/kr/grand-hyatt-seoul.ko.html'},
    {'hotel': '롯데호텔 서울',       'city': '서울', 'grade': '5*',  'booking_url': 'https://www.booking.com/hotel/kr/lotte-seoul-seoul.ko.html'},
    {'hotel': '글래드 여의도',       'city': '서울', 'grade': '4*',  'booking_url': 'https://www.booking.com/hotel/kr/glad-yeouido.ko.html'},
    # 부산 (2)
    {'hotel': '시그니엘 부산',       'city': '부산', 'grade': 'Lux', 'booking_url': 'https://www.booking.com/hotel/kr/signiel-busan.ko.html'},
    {'hotel': '파라다이스 호텔 부산','city': '부산', 'grade': '5*',  'booking_url': 'https://www.booking.com/hotel/kr/paradise-busan.ko.html'},
    # 제주 (2)
    {'hotel': '그랜드 하얏트 제주',  'city': '제주', 'grade': '5*',  'booking_url': 'https://www.booking.com/hotel/kr/grand-hyatt-jeju.ko.html'},
    {'hotel': '롯데호텔 제주',       'city': '제주', 'grade': '5*',  'booking_url': 'https://www.booking.com/hotel/kr/lotte-jeju.ko.html'},
    # 경주 (1)
    {'hotel': '힐튼 경주',           'city': '경주', 'grade': '5*',  'booking_url': 'https://www.booking.com/hotel/kr/gyeongju-hilton.ko.html'},
]

LEAD_DAYS = [7, 14, 30]
KST = datetime.timezone(datetime.timedelta(hours=9))
CSV_FILE = 'hotel_adr.csv'
CSV_COLUMNS = [
    'collected_at', 'hotel', 'city', 'grade',
    'ota', 'search_date', 'lead_days',
    'price_krw', 'url',
]
PRICE_FLOOR = 50000  # 객실 가격은 5만원 이상으로 가정 (페이지 내 부수 ₩숫자 필터)


def get_booking_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_argument(
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
    )
    opts.add_experimental_option('excludeSwitches', ['enable-automation'])

    # VM (Ubuntu)에서 snap chromium 사용 시 wrapper 필요 (fetch_seibro_data.py 패턴)
    if os.path.exists('/snap/bin/chromium'):
        opts.binary_location = '/snap/bin/chromium'
        wrapper = '/tmp/chromedriver_wrapper.sh'
        with open(wrapper, 'w') as f:
            f.write('#!/bin/bash\nexec snap run chromium.chromedriver "$@"\n')
        os.chmod(wrapper, 0o755)
        from selenium.webdriver.chrome.service import Service
        return webdriver.Chrome(service=Service(wrapper), options=opts)
    return webdriver.Chrome(options=opts)


def fetch_booking_min_price(driver, booking_url, search_date):
    """Booking.com 호텔 페이지에서 entry(최저가) 객실 가격 추출

    Booking.com은 객실 가격을 prco-* 클래스 컨테이너에 표시.
    부수 가격(추가 침대/조식/세금)과 분리됨.
    """
    checkout = (datetime.datetime.strptime(search_date, '%Y-%m-%d') + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    url = f'{booking_url}?checkin={search_date}&checkout={checkout}&group_adults=2&no_rooms=1'
    try:
        driver.get(url)
        time.sleep(7)
        text = driver.page_source

        if len(text) < 50000:
            return None, url, 'page_too_short'

        # 1순위: "₩가격 × 1박" 패턴 (객실 카드의 실제 1박 가격)
        per_night = re.findall(r'₩\s*(\d{1,3}(?:,\d{3})+)\s*[×x*]\s*1\s*박', text)
        if per_night:
            prices = [int(m.replace(',', '')) for m in per_night]
            prices = [p for p in prices if p >= PRICE_FLOOR]
            if prices:
                return min(prices), url, None

        # 2순위: prco-* 클래스 가격
        prco_matches = re.findall(r'class="[^"]*prco[^"]*"[^>]*>\s*[^<]*₩\s*(\d{1,3}(?:,\d{3})+)', text)
        if prco_matches:
            prices = [int(m.replace(',', '')) for m in prco_matches]
            prices = [p for p in prices if p >= PRICE_FLOOR]
            if prices:
                return min(prices), url, 'fallback_prco'

        return None, url, 'no_valid_price'
    except Exception as e:
        return None, url, str(e)[:50]


def append_csv(rows):
    file_exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            w.writeheader()
        for row in rows:
            w.writerow(row)


def main():
    now = datetime.datetime.now(tz=KST)
    today = now.date()
    collected_at = now.strftime('%Y-%m-%d %H:%M:%S')

    print(f'=== 호텔 ADR 수집 시작 {collected_at} KST ({len(HOTEL_MAPPINGS)}호텔 × {len(LEAD_DAYS)} lead = {len(HOTEL_MAPPINGS)*len(LEAD_DAYS)}건) ===')
    rows = []
    fail_log = []
    driver = None

    try:
        driver = get_booking_driver()
        for hotel in HOTEL_MAPPINGS:
            print(f'\n[{hotel["hotel"]}]')
            for lead in LEAD_DAYS:
                search_date = (today + datetime.timedelta(days=lead)).strftime('%Y-%m-%d')
                price, url, err = fetch_booking_min_price(driver, hotel['booking_url'], search_date)
                if price:
                    print(f'  lead+{lead}d {search_date}: ₩{price:,}')
                    rows.append({
                        'collected_at': collected_at, 'hotel': hotel['hotel'],
                        'city': hotel['city'], 'grade': hotel['grade'],
                        'ota': 'booking', 'search_date': search_date, 'lead_days': lead,
                        'price_krw': price, 'url': url,
                    })
                else:
                    print(f'  lead+{lead}d {search_date}: FAIL ({err})')
                    fail_log.append((hotel['hotel'], lead, err))
    finally:
        if driver:
            driver.quit()

    if rows:
        append_csv(rows)
        print(f'\n=== ✅ {len(rows)}건 {CSV_FILE}에 저장 완료 ===')
    if fail_log:
        print(f'\n=== ⚠️  {len(fail_log)}건 실패 ===')
        for h, l, e in fail_log:
            print(f'  {h} lead+{l}d: {e}')


if __name__ == '__main__':
    main()
