"""
Universe 미국 종목의 실적 발표 + Investor Day 일정을 Google Calendar "투자 활동"에 동기화.

CLI:
  python3 earnings_calendar_sync.py --dry-run          # 쓰기 없이 계획만 출력
  python3 earnings_calendar_sync.py                    # 실제 실행
  python3 earnings_calendar_sync.py --ticker AMGN      # 특정 종목만
  python3 earnings_calendar_sync.py --days 30          # 향후 30일만 (기본 60)
  python3 earnings_calendar_sync.py --skip-earnings    # 실적 스킵
  python3 earnings_calendar_sync.py --skip-ir-day      # Investor Day 스킵
"""
import os
import re
import sys
import json
import time
import hashlib
import argparse
import logging
import requests
from datetime import datetime, date as date_cls, timedelta, timezone
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
HOUR_LABEL = {'bmo': 'Before (장전)', 'amc': 'After (장후)', 'dmh': 'During (장중)'}
# 한국시간 기준 표기: 미국 장전(bmo)=KST 당일 저녁, 장후(amc)=KST 다음날 새벽,
# 장중(dmh)=KST 당일 밤(개장 22:30/23:30). amc만 캘린더 날짜를 +1일 이동.
KST_HOUR_PREFIX = {'bmo': '저녁', 'amc': '새벽', 'dmh': '밤'}

IR_DAY_KEYWORDS = re.compile(
    r'\b(investor\s+day|analyst\s+day|capital\s+markets\s+day|shareholder\s+day)\b',
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(
    r'\b(january|february|march|april|may|june|july|august|september|october|november|december)'
    r'\s+(\d{1,2})(?:st|nd|rd|th)?(?:,)?\s+(\d{4})\b',
    re.IGNORECASE,
)
MONTH_MAP = {'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
             'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12}
EDGAR_UA = 'antigravity-bot kts77775@gmail.com'


def _load_universe_values():
    """Universe 행 데이터 로드. 자체 리스트 universe.json 우선(GHA fetch_universe.py가
    매일 07:00·18:30 KST 생성, Sheets 응답과 동일한 {values:[header,...rows]} 형식).
    없거나 비면 옛 Google Sheets로 폴백 — Sheets는 미국 장 직후 '로드 중...'으로
    통화 컬럼이 비는 시간대가 있어 신뢰도가 낮음."""
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'universe.json')
    try:
        with open(local_path, encoding='utf-8') as f:
            data = json.load(f)
        values = data.get('values', [])
        if values:
            log.info(f"universe.json 로드 (updated_at={data.get('updated_at','?')})")
            return values
        log.warning("universe.json values 비어있음 → Sheets 폴백")
    except Exception as e:
        log.warning(f"universe.json 로드 실패 → Sheets 폴백: {e}")
    url = f'https://sheets.googleapis.com/v4/spreadsheets/{SHEETS_ID}/values/universe?key={SHEETS_API_KEY}'
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json().get('values', [])


def load_us_universe():
    values = _load_universe_values()
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
        if ':' in raw_ticker:
            raw_ticker = raw_ticker.split(':', 1)[1].strip()
        ticker = raw_ticker
        name = row[name_idx].strip() if len(row) > name_idx else ticker
        if ticker and ticker not in seen:
            result.append((ticker, name))
            seen.add(ticker)
    log.info(f"USD 종목 {len(result)}개 로드")
    return result


def _finnhub_get(path, params, max_retries=3):
    url = f'{FINNHUB_API}{path}'
    for attempt in range(max_retries):
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 429:
            wait = 5 * (attempt + 1)
            log.warning(f"Rate limit {path} {params.get('symbol','')}, sleeping {wait}s (attempt {attempt+1})")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Rate limit 재시도 초과: {path} {params.get('symbol','')}")


def fetch_earnings(ticker, from_date, to_date, api_key):
    data = _finnhub_get('/calendar/earnings',
                       {'from': from_date, 'to': to_date, 'symbol': ticker, 'token': api_key})
    return data.get('earningsCalendar', []) if isinstance(data, dict) else []


def fetch_company_news(ticker, from_date, to_date, api_key):
    data = _finnhub_get('/company-news',
                       {'symbol': ticker, 'from': from_date, 'to': to_date, 'token': api_key})
    return data if isinstance(data, list) else []


def parse_date_from_text(text):
    """'March 12, 2026' 같은 패턴 파싱 → 'YYYY-MM-DD'."""
    m = DATE_PATTERN.search(text)
    if not m:
        return None
    month = MONTH_MAP.get(m.group(1).lower())
    if not month:
        return None
    try:
        return date_cls(int(m.group(3)), month, int(m.group(2))).isoformat()
    except ValueError:
        return None


def extract_ir_days_from_news(ticker, news_items, event_from, event_to):
    """뉴스에서 Investor Day 언급 + 날짜 파싱 (event_from ~ event_to 범위)."""
    events = []
    for n in news_items:
        title = n.get('headline') or ''
        summary = n.get('summary') or ''
        combined = f"{title} {summary}"
        if not IR_DAY_KEYWORDS.search(combined):
            continue
        event_date = parse_date_from_text(combined)
        if not event_date:
            continue  # 뉴스 datetime으로 fallback하면 사후 기사 노이즈 많음
        if event_date < event_from or event_date > event_to:
            continue
        events.append({
            'ticker': ticker,
            'date': event_date,
            'title': title[:120],
            'source': 'finnhub-news',
            'url': n.get('url', ''),
        })
    return events


_TICKER_PAREN = re.compile(r'\(([A-Z][A-Z\.]{0,5})\)')


def fetch_edgar_ir_days(search_from, search_to, universe_tickers, event_from, event_to):
    """EDGAR 8-K Full-text search로 Investor Day 관련 공시 수집."""
    url = 'https://efts.sec.gov/LATEST/search-index'
    events = []
    from_idx = 0
    while True:
        try:
            params = {
                'q': '"Investor Day"',
                'forms': '8-K',
                'dateRange': 'custom',
                'startdt': search_from,
                'enddt': search_to,
                'from': from_idx,
            }
            r = requests.get(url, params=params, headers={'User-Agent': EDGAR_UA}, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log.warning(f"EDGAR 검색 실패 (from={from_idx}): {e}")
            break

        hits = data.get('hits', {}).get('hits', [])
        if not hits:
            break
        total = data.get('hits', {}).get('total', {}).get('value', 0)

        for hit in hits:
            src = hit.get('_source', {})
            # Item 7.01 (Reg FD) 만 포함
            if '7.01' not in (src.get('items') or []):
                continue
            names = src.get('display_names', [])
            ticker = None
            for n in names:
                for m in _TICKER_PAREN.finditer(n):
                    t = m.group(1)
                    if t == 'CIK' or t.startswith('CIK'):
                        continue
                    ticker = t
                    break
                if ticker:
                    break
            if not ticker or ticker not in universe_tickers:
                continue
            # 이벤트 날짜: period_ending 우선 (이벤트 실제 날짜), 없으면 file_date
            ev_date = src.get('period_ending') or src.get('file_date')
            if not ev_date or ev_date < event_from or ev_date > event_to:
                continue
            ciks = src.get('ciks') or ['0']
            cik_int = int(ciks[0].lstrip('0') or '0')
            events.append({
                'ticker': ticker,
                'date': ev_date,
                'title': src.get('file_description') or 'Investor Day',
                'source': 'edgar',
                'url': f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_int}&type=8-K",
            })

        from_idx += len(hits)
        if from_idx >= total:
            break
        time.sleep(0.3)  # EDGAR: 초당 10req 제한

    return events


def format_number(val, prefix='$'):
    if val is None:
        return '-'
    if abs(val) >= 1e9:
        return f"{prefix}{val/1e9:.2f}B"
    if abs(val) >= 1e6:
        return f"{prefix}{val/1e6:.2f}M"
    return f"{prefix}{val:.2f}"


def make_event_id(ticker, date_str, prefix='agearn'):
    h = hashlib.md5(f"{ticker}_{date_str}".encode()).hexdigest()[:16]
    return f"{prefix}{h}"


def build_earnings_event(earnings, company_name):
    ticker = earnings['symbol']
    ed = earnings['date']
    hour = (earnings.get('hour') or '').lower()
    q = earnings.get('quarter')
    y = earnings.get('year')

    hour_disp = HOUR_LABEL.get(hour, '시간 미정')
    prefix_word = KST_HOUR_PREFIX.get(hour)
    yy = str(y)[-2:] if y else ''
    core = f"[{ticker}] {q}Q{yy} Earnings"
    summary = f"{prefix_word} | {core}" if prefix_word else core

    # 캘린더 표시일: amc는 한국시간 발표가 다음날 새벽이므로 +1일
    kst_date = ed
    if hour == 'amc':
        kst_date = (datetime.fromisoformat(ed) + timedelta(days=1)).strftime('%Y-%m-%d')

    eps_est = earnings.get('epsEstimate')
    rev_est = earnings.get('revenueEstimate')
    eps_actual = earnings.get('epsActual')
    rev_actual = earnings.get('revenueActual')

    lines = [
        f"기업: {company_name}",
        f"발표일(미국 현지): {ed} ({hour_disp})",
    ]
    if prefix_word:
        lines.append(f"한국시간: {kst_date} {prefix_word}")
    lines += [
        f"EPS 추정: {format_number(eps_est)}",
        f"Revenue 추정: {format_number(rev_est)}",
    ]
    if eps_actual is not None or rev_actual is not None:
        lines.append("")
        lines.append(f"EPS 실제: {format_number(eps_actual)}")
        lines.append(f"Revenue 실제: {format_number(rev_actual)}")
    lines.append("")
    lines.append(f"Finnhub: https://finnhub.io/dashboard/stock/{ticker}")

    # 안정 ID: (ticker, 회계분기) 기반. Finnhub가 추정 발표일을 갱신해도 ID가 같아
    # 새로 insert하지 않고 기존 이벤트를 update → 날짜 변경에 의한 유령 중복 방지.
    # quarter/year가 비는 경우(드묾)에만 날짜 기반으로 폴백.
    if q and yy:
        stable_key = f"{ticker}_{q}Q{yy}"
    else:
        stable_key = f"{ticker}_{ed}"
    eid = 'agearn' + hashlib.md5(stable_key.encode()).hexdigest()[:16]

    end_date = (datetime.fromisoformat(kst_date) + timedelta(days=1)).strftime('%Y-%m-%d')
    return {
        'id': eid,
        'summary': summary,
        'description': '\n'.join(lines),
        'start': {'date': kst_date},
        'end': {'date': end_date},
    }


def build_ir_day_event(ev, company_name):
    ticker = ev['ticker']
    ed = ev['date']
    src_label = {'edgar': 'SEC EDGAR 8-K Item 7.01', 'finnhub-news': 'Finnhub 뉴스'}.get(ev['source'], ev['source'])

    lines = [
        f"기업: {company_name}",
        f"이벤트: Investor Day",
        f"추정 일자: {ed}",
        f"출처: {src_label}",
        "",
        f"원문 제목: {ev.get('title','')}",
    ]
    if ev.get('url'):
        lines.append("")
        lines.append(f"링크: {ev['url']}")
    lines.append("")
    lines.append("※ 추정 일자는 자동 파싱 결과 — 회사 IR 페이지 재확인 권장")

    # 안정 ID: (ticker, 연도) 기반 — 추정 일자가 재파싱으로 바뀌어도 같은 연도면 같은 ID로
    # update (실적 fix와 동일 원리). IR Day는 회계분기가 없어 연도 단위로 묶음.
    stable_key = f"{ticker}_IRDAY_{ed[:4]}"
    eid = 'agird' + hashlib.md5(stable_key.encode()).hexdigest()[:16]
    end_date = (datetime.fromisoformat(ed) + timedelta(days=1)).strftime('%Y-%m-%d')
    return {
        'id': eid,
        'summary': f"[{ticker}] Investor Day",
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


EARN_LABEL_RE = re.compile(r"\[([A-Z0-9\.\-]+)\]\s+(\d+Q\d+)\s+Earnings")


def dedup_earnings_events(service, dry_run=False):
    """같은 (ticker, 회계분기) 라벨의 중복 실적 이벤트 정리.
    안정 ID(분기 기반)만 남기고 나머지 삭제 → ID 스킴 전환 시 옛 날짜해시
    이벤트를 1회 자동 청소하고, 이후에도 혹시 생기는 중복을 매 실행마다 self-heal.
    주의: Finnhub가 동일 분기를 다른 연도로 표기(2026↔2027 정정)하면 라벨이 달라져
    같은 그룹으로 묶이지 않을 수 있음 — 그 경우는 드물며 다음 sync에서 수렴."""
    if dry_run:
        return 0
    items = []
    token = None
    while True:
        res = service.events().list(
            calendarId=CAL_ID, timeMin='2026-01-01T00:00:00Z',
            timeMax='2027-12-31T00:00:00Z', singleEvents=True, orderBy='startTime',
            maxResults=2500, pageToken=token).execute()
        items += res.get('items', [])
        token = res.get('nextPageToken')
        if not token:
            break
    groups = {}
    for ev in items:
        eid = ev.get('id', '')
        if not eid.startswith('agearn'):
            continue
        m = EARN_LABEL_RE.search(ev.get('summary', ''))
        if not m:
            continue
        tk, label = m.group(1), m.group(2)
        d = ev.get('start', {}).get('date', '')
        groups.setdefault((tk, label), []).append((eid, d))
    removed = 0
    for (tk, label), evs in groups.items():
        if len(evs) < 2:
            continue
        canonical = 'agearn' + hashlib.md5(f"{tk}_{label}".encode()).hexdigest()[:16]
        ids = [e[0] for e in evs]
        keep = canonical if canonical in ids else sorted(evs, key=lambda x: x[1])[-1][0]
        for eid, d in evs:
            if eid == keep:
                continue
            try:
                service.events().delete(calendarId=CAL_ID, eventId=eid).execute()
                removed += 1
                log.info(f"  [dedup] {tk} {label}: deleted {eid} ({d})")
            except HttpError as e:
                log.warning(f"  [dedup] {tk} {label} delete 실패 {eid}: {e}")
    if removed:
        log.info(f"[Dedup] 중복 실적 이벤트 {removed}건 정리")
    return removed


def run_earnings(universe, service, api_key, from_date, to_date, dry_run):
    log.info(f"[Earnings] 조회 범위: {from_date} ~ {to_date} ({len(universe)}개 종목)")
    stats = {'inserted': 0, 'updated': 0, 'unchanged': 0, 'dry-run': 0, 'no-earnings': 0, 'error': 0}
    for ticker, name in universe:
        try:
            earnings_list = fetch_earnings(ticker, from_date, to_date, api_key)
        except Exception as e:
            log.error(f"{ticker}: earnings 조회 실패: {e}")
            stats['error'] += 1
            continue
        if not earnings_list:
            stats['no-earnings'] += 1
            time.sleep(1.1)
            continue
        for earnings in earnings_list:
            try:
                event = build_earnings_event(earnings, name)
                result = upsert_event(service, event, dry_run=dry_run)
                stats[result] += 1
                if result != 'unchanged':
                    log.info(f"  Earn {ticker} {earnings['date']}: {result}")
            except Exception as e:
                log.error(f"  Earn {ticker} {earnings.get('date','?')}: upsert 실패: {e}")
                stats['error'] += 1
        time.sleep(1.1)
    log.info(f"[Earnings] 완료: {stats}")
    dedup_earnings_events(service, dry_run=dry_run)
    return stats


IR_LABEL_RE = re.compile(r"\[([A-Z0-9\.\-]+)\]\s+Investor Day")


def dedup_ir_events(service, dry_run=False):
    """같은 (ticker, 연도)의 중복 Investor Day 이벤트 정리.
    연도 기반 안정 ID만 남기고 나머지 삭제 → 옛 날짜해시 이벤트 1회 청소 + 이후 self-heal.
    한 종목이 한 해 복수 IR day를 여는 드문 경우는 병합될 수 있음(허용)."""
    if dry_run or service is None:
        return 0
    items = []
    token = None
    while True:
        res = service.events().list(
            calendarId=CAL_ID, timeMin='2026-01-01T00:00:00Z',
            timeMax='2027-12-31T00:00:00Z', singleEvents=True, orderBy='startTime',
            maxResults=2500, pageToken=token).execute()
        items += res.get('items', [])
        token = res.get('nextPageToken')
        if not token:
            break
    groups = {}
    for ev in items:
        eid = ev.get('id', '')
        if not eid.startswith('agird'):
            continue
        m = IR_LABEL_RE.search(ev.get('summary', ''))
        if not m:
            continue
        tk = m.group(1)
        d = ev.get('start', {}).get('date', '')
        groups.setdefault((tk, d[:4]), []).append((eid, d))
    removed = 0
    for (tk, yr), evs in groups.items():
        if len(evs) < 2:
            continue
        canonical = 'agird' + hashlib.md5(f"{tk}_IRDAY_{yr}".encode()).hexdigest()[:16]
        ids = [e[0] for e in evs]
        keep = canonical if canonical in ids else sorted(evs, key=lambda x: x[1])[-1][0]
        for eid, d in evs:
            if eid == keep:
                continue
            try:
                service.events().delete(calendarId=CAL_ID, eventId=eid).execute()
                removed += 1
                log.info(f"  [ir-dedup] {tk} {yr}: deleted {eid} ({d})")
            except HttpError as e:
                log.warning(f"  [ir-dedup] {tk} {yr} delete 실패 {eid}: {e}")
    if removed:
        log.info(f"[ir-dedup] IR Day 중복 {removed}건 정리")
    return removed


def run_investor_days(universe, service, api_key, today, days, dry_run):
    event_from = today.isoformat()
    event_to = (today + timedelta(days=days)).isoformat()
    news_from = (today - timedelta(days=90)).isoformat()
    news_to = today.isoformat()

    names_by_ticker = {t: n for t, n in universe}
    universe_tickers = set(names_by_ticker.keys())

    log.info(f"[IR Day] 이벤트 범위: {event_from} ~ {event_to} / 뉴스 검색: {news_from} ~ {news_to}")

    collected = {}  # (ticker, date) → event (EDGAR 우선)

    # 1. EDGAR (filing date는 과거만 가능 → search_to는 today로 제한)
    log.info(f"[IR Day] EDGAR 8-K 검색 중...")
    try:
        edgar_events = fetch_edgar_ir_days(news_from, news_to, universe_tickers, event_from, event_to)
        for ev in edgar_events:
            key = (ev['ticker'], ev['date'])
            collected[key] = ev
        log.info(f"[IR Day] EDGAR 수집: {len(edgar_events)}건 (Universe 매치)")
    except Exception as e:
        log.error(f"[IR Day] EDGAR 실패: {e}")

    # 2. Finnhub company-news
    log.info(f"[IR Day] Finnhub 뉴스 검색 중... ({len(universe)}개 종목)")
    news_added = 0
    for ticker, name in universe:
        try:
            news_items = fetch_company_news(ticker, news_from, news_to, api_key)
        except Exception as e:
            log.warning(f"  {ticker} news 실패: {e}")
            time.sleep(1.1)
            continue
        found = extract_ir_days_from_news(ticker, news_items, event_from, event_to)
        for ev in found:
            key = (ev['ticker'], ev['date'])
            if key not in collected:
                collected[key] = ev
                news_added += 1
        time.sleep(1.1)
    log.info(f"[IR Day] Finnhub 추가: {news_added}건")

    # 3. Upsert
    stats = {'inserted': 0, 'updated': 0, 'unchanged': 0, 'dry-run': 0, 'error': 0}
    for key, ev in collected.items():
        name = names_by_ticker.get(ev['ticker'], ev['ticker'])
        try:
            event = build_ir_day_event(ev, name)
            result = upsert_event(service, event, dry_run=dry_run)
            stats[result] += 1
            if result != 'unchanged':
                log.info(f"  IR {ev['ticker']} {ev['date']}: {result} ({ev['source']})")
        except Exception as e:
            log.error(f"  IR {ev['ticker']} {ev.get('date','?')}: upsert 실패: {e}")
            stats['error'] += 1
    log.info(f"[IR Day] 완료: {stats}")
    dedup_ir_events(service, dry_run=dry_run)
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--days', type=int, default=60)
    ap.add_argument('--ticker', help='특정 티커만 (테스트용)')
    ap.add_argument('--skip-earnings', action='store_true')
    ap.add_argument('--skip-ir-day', action='store_true')
    ap.add_argument('--ir-dedup-only', action='store_true', help='IR Day 중복 정리만 실행')
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

    service = None
    if not args.dry_run:
        sa_info = json.loads(os.getenv('GOOGLE_SERVICE_ACCOUNT_KEY'))
        creds = service_account.Credentials.from_service_account_info(
            sa_info, scopes=['https://www.googleapis.com/auth/calendar.events']
        )
        service = build('calendar', 'v3', credentials=creds)

    if args.ir_dedup_only:
        dedup_ir_events(service, dry_run=args.dry_run)
        log.info('IR Day 중복 정리만 완료')
        return

    if not args.skip_earnings:
        run_earnings(universe, service, api_key, from_date, to_date, args.dry_run)

    if not args.skip_ir_day:
        run_investor_days(universe, service, api_key, today, args.days, args.dry_run)


if __name__ == '__main__':
    main()
