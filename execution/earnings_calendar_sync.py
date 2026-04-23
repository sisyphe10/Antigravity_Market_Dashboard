"""
Universe 미국 종목의 실적 발표 일정을 Google Calendar "투자 활동"에 동기화.

CLI:
  python3 earnings_calendar_sync.py --dry-run       # 쓰기 없이 계획만 출력
  python3 earnings_calendar_sync.py                 # 실제 실행
  python3 earnings_calendar_sync.py --ticker AMGN   # 특정 종목만
  python3 earnings_calendar_sync.py --days 30       # 향후 30일만 (기본 60)
"""
import os
import sys
import json
import time
import hashlib
import argparse
import logging
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)
log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
SHEETS_API_KEY = 'AIzaSyCHPiRby5FVAIKDwneZHy1KGl3SfycjZEw'
SHEETS_ID = '1KR9RJN53G-yJtnowQbg5bcAiIBfrkIeNqN_PO2UOCTM'
CAL_ID = 's7m7ahc836cajffbt98vae3m1k@group.calendar.google.com'
FINNHUB_API = 'https://finnhub.io/api/v1'
HOUR_LABEL = {'bmo': 'BMO (장전)', 'amc': 'AMC (장후)', 'dmh': 'DMH (장중)'}


def load_us_universe():
    url = f'https://sheets.googleapis.com/v4/spreadsheets/{SHEETS_ID}/values/universe?key={SHEETS_API_KEY}'
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    values = r.json().get('values', [])
    if not values:
        return []
    header = values[0]
    try:
        curr_idx = header.index('통화')
        ticker_idx = header.index('티커')
        name_idx = header.index('기업명')
    except ValueError as e:
        raise RuntimeError(f"Universe 헤더 파싱 실패: {e}")

    result = []
    seen = set()
    for row in values[1:]:
        if len(row) <= max(curr_idx, ticker_idx, name_idx):
            continue
        if row[curr_idx].strip().upper() != 'USD':
            continue
        raw_ticker = row[ticker_idx].strip().upper()
        # "NYSE:AMGN", "NASDAQ:AMGN", "AMEX:X" 등 접두어 제거
        if ':' in raw_ticker:
            raw_ticker = raw_ticker.split(':', 1)[1].strip()
        ticker = raw_ticker
        name = row[name_idx].strip() if len(row) > name_idx else ticker
        if ticker and ticker not in seen:
            result.append((ticker, name))
            seen.add(ticker)
    log.info(f"USD 종목 {len(result)}개 로드")
    return result


def fetch_earnings(ticker, from_date, to_date, api_key, max_retries=3):
    params = {'from': from_date, 'to': to_date, 'symbol': ticker, 'token': api_key}
    url = f'{FINNHUB_API}/calendar/earnings'
    for attempt in range(max_retries):
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 429:
            wait = 5 * (attempt + 1)
            log.warning(f"Rate limit {ticker}, sleeping {wait}s (attempt {attempt+1})")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json().get('earningsCalendar', [])
    raise RuntimeError(f"Rate limit 재시도 초과: {ticker}")


def format_number(val, prefix='$'):
    if val is None:
        return '-'
    if abs(val) >= 1e9:
        return f"{prefix}{val/1e9:.2f}B"
    if abs(val) >= 1e6:
        return f"{prefix}{val/1e6:.2f}M"
    return f"{prefix}{val:.2f}"


def make_event_id(ticker, date_str):
    # Google Calendar event ID: [0-9a-v], 5~1024 chars
    # MD5 hex는 0-9a-f 범위라 항상 안전
    h = hashlib.md5(f"{ticker}_{date_str}".encode()).hexdigest()[:16]
    return f"agearn{h}"


def build_event(earnings, company_name):
    ticker = earnings['symbol']
    ed = earnings['date']
    hour = (earnings.get('hour') or '').lower()
    q = earnings.get('quarter')
    y = earnings.get('year')

    short = hour.upper() if hour in HOUR_LABEL else ''
    hour_disp = HOUR_LABEL.get(hour, '시간 미정')
    suffix = f" ({short})" if short else ""
    summary = f"[{ticker}] {y}Q{q} Earnings{suffix}"

    eps_est = earnings.get('epsEstimate')
    rev_est = earnings.get('revenueEstimate')
    eps_actual = earnings.get('epsActual')
    rev_actual = earnings.get('revenueActual')

    lines = [
        f"기업: {company_name}",
        f"발표일: {ed} ({hour_disp})",
        f"EPS 추정: {format_number(eps_est)}",
        f"Revenue 추정: {format_number(rev_est)}",
    ]
    if eps_actual is not None or rev_actual is not None:
        lines.append("")
        lines.append(f"EPS 실제: {format_number(eps_actual)}")
        lines.append(f"Revenue 실제: {format_number(rev_actual)}")
    lines.append("")
    lines.append(f"Finnhub: https://finnhub.io/dashboard/stock/{ticker}")

    end_date = (datetime.fromisoformat(ed) + timedelta(days=1)).strftime('%Y-%m-%d')
    return {
        'id': make_event_id(ticker, ed),
        'summary': summary,
        'description': '\n'.join(lines),
        'start': {'date': ed},
        'end': {'date': end_date},
    }


def upsert_event(service, event, dry_run=False):
    if dry_run:
        log.info(f"  [DRY-RUN] {event['summary']} → {event['start']['date']}")
        return 'dry-run'
    eid = event['id']
    try:
        existing = service.events().get(calendarId=CAL_ID, eventId=eid).execute()
        if (existing.get('summary') == event['summary'] and
            existing.get('description') == event['description'] and
            existing.get('start', {}).get('date') == event['start']['date']):
            return 'unchanged'
        service.events().update(calendarId=CAL_ID, eventId=eid, body=event).execute()
        return 'updated'
    except HttpError as e:
        if e.resp.status in (404, 410):
            service.events().insert(calendarId=CAL_ID, body=event).execute()
            return 'inserted'
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--days', type=int, default=60)
    ap.add_argument('--ticker', help='특정 티커만 (테스트용)')
    args = ap.parse_args()

    api_key = os.getenv('FINNHUB_API_KEY')
    if not api_key:
        log.error("FINNHUB_API_KEY not set in .env")
        sys.exit(1)

    universe = load_us_universe()
    if args.ticker:
        universe = [(t, n) for t, n in universe if t == args.ticker.upper()]
        if not universe:
            log.error(f"Ticker {args.ticker} not in Universe")
            sys.exit(1)

    today = datetime.now(tz=KST).date()
    from_date = today.isoformat()
    to_date = (today + timedelta(days=args.days)).isoformat()
    log.info(f"조회 범위: {from_date} ~ {to_date} ({len(universe)}개 종목)")

    service = None
    if not args.dry_run:
        sa_info = json.loads(os.getenv('GOOGLE_SERVICE_ACCOUNT_KEY'))
        creds = service_account.Credentials.from_service_account_info(
            sa_info, scopes=['https://www.googleapis.com/auth/calendar.events']
        )
        service = build('calendar', 'v3', credentials=creds)

    stats = {'inserted': 0, 'updated': 0, 'unchanged': 0, 'dry-run': 0, 'no-earnings': 0, 'error': 0}

    for ticker, name in universe:
        try:
            earnings_list = fetch_earnings(ticker, from_date, to_date, api_key)
        except Exception as e:
            log.error(f"{ticker}: Finnhub 조회 실패: {e}")
            stats['error'] += 1
            continue

        if not earnings_list:
            stats['no-earnings'] += 1
            continue

        for earnings in earnings_list:
            try:
                event = build_event(earnings, name)
                result = upsert_event(service, event, dry_run=args.dry_run)
                stats[result] += 1
                if result != 'unchanged':
                    log.info(f"  {ticker} {earnings['date']}: {result}")
            except Exception as e:
                log.error(f"  {ticker} {earnings.get('date','?')}: upsert 실패: {e}")
                stats['error'] += 1

        time.sleep(1.1)  # 60 req/min 제한, 여유있게 초당 1건 이하

    log.info(f"완료: {stats}")


if __name__ == '__main__':
    main()
