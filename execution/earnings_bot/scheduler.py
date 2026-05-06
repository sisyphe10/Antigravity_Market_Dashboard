"""Finnhub earnings calendar 단일 윈도우 호출 — 매일 08:00 KST.

Codex 권고 #2c 반영: 티커별 N회 호출 대신 캘린더 1회 윈도우 호출로 쿼터 절약.

API: GET https://finnhub.io/api/v1/calendar/earnings?from=YYYY-MM-DD&to=YYYY-MM-DD
응답: { earningsCalendar: [{symbol, date, hour, year, quarter, epsEstimate, revenueEstimate, ...}] }

hour 값: 'amc' (after market close) / 'bmo' (before market open) / 'dmh' (during market hours) / null
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import db, ticker_registry
from .retry_helper import finnhub_retry

logger = logging.getLogger(__name__)

FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY', '')
LOOKAHEAD_DAYS = 14  # 오늘 포함 14일 윈도우


@finnhub_retry
def _fetch_window(date_from: str, date_to: str) -> dict:
    if not FINNHUB_API_KEY:
        raise RuntimeError("FINNHUB_API_KEY 미설정")
    qs = urlencode({'from': date_from, 'to': date_to, 'token': FINNHUB_API_KEY})
    url = f"https://finnhub.io/api/v1/calendar/earnings?{qs}"
    req = Request(url, headers={'User-Agent': 'antigravity-earnings-bot/1.0'})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def sync_calendar(tickers: list[str] | None = None, days: int = LOOKAHEAD_DAYS) -> dict:
    """Finnhub에서 N일 윈도우 캘린더 가져와 universe 종목만 DB 적재."""
    db.init_db()
    if tickers is None:
        tickers = ticker_registry.UNIVERSE_USD_DRAFT
    universe = set(t.upper() for t in tickers)

    today = date.today()
    date_from = today.isoformat()
    date_to = (today + timedelta(days=days)).isoformat()

    payload = _fetch_window(date_from, date_to)
    entries = payload.get('earningsCalendar', []) or []
    matched = [e for e in entries if (e.get('symbol') or '').upper() in universe]

    for e in matched:
        symbol = (e.get('symbol') or '').upper()
        event_date = e.get('date')   # YYYY-MM-DD ET 기준
        hour = (e.get('hour') or '').lower() or None
        year = e.get('year')
        quarter = e.get('quarter')
        eps_estimate = e.get('epsEstimate')
        revenue_estimate = e.get('revenueEstimate')
        db.upsert_calendar_entry(
            ticker=symbol,
            event_date=event_date,
            hour=hour,
            year=year,
            quarter=quarter,
            eps_estimate=eps_estimate,
            revenue_estimate=revenue_estimate,
        )

    return {
        'window': f'{date_from}~{date_to}',
        'total_in_window': len(entries),
        'matched_universe': len(matched),
        'tickers_matched': sorted({(e.get('symbol') or '').upper() for e in matched}),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    result = sync_calendar()
    print(f"Window: {result['window']}")
    print(f"Total: {result['total_in_window']}, Universe matches: {result['matched_universe']}")
    print(f"Tickers: {result['tickers_matched']}")
