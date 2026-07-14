"""ticker → filing_type(8-K vs 6-K) + CIK 매핑.

Codex BLOCKER #1·HIGH 대응. 외국 발행인(Foreign Private Issuer)은 8-K가 아닌
6-K로 실적 공시하므로 edgar_monitor가 두 form 모두 추적해야 함.

운영 원칙:
- 외국 발행인 화이트리스트는 정적 (드물게 변경)
- CIK는 edgartools/SEC tickers.json으로 lazy lookup + 캐시
- Universe USD 종목은 Google Sheets `universe` 시트에서 라이브 fetch (get_universe_usd).
  Sheets 호출 실패 시 UNIVERSE_USD_DRAFT 22종목으로 폴백.
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Literal

logger = logging.getLogger(__name__)

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ticker_cik_cache.json')

# earnings_calendar_sync.py와 공유 (대시보드 universe 시트 동일 출처)
SHEETS_API_KEY = 'AIzaSyCHPiRby5FVAIKDwneZHy1KGl3SfycjZEw'
SHEETS_ID = '1KR9RJN53G-yJtnowQbg5bcAiIBfrkIeNqN_PO2UOCTM'

FilingType = Literal['8-K', '6-K']


# ─── 외국 발행인 (Foreign Private Issuer) 화이트리스트 ───
# 6-K 사용. 추가 시 SEC EDGAR에서 해당 발행인이 실제로 6-K를 사용하는지 확인할 것.
FOREIGN_PRIVATE_ISSUERS: dict[str, dict] = {
    'ASML':  {'country': 'NL', 'exchange': 'NASDAQ', 'note': 'ASML Holding NV (ADR)'},
    'TSM':   {'country': 'TW', 'exchange': 'NYSE',   'note': 'Taiwan Semiconductor (ADR)'},
    'CCJ':   {'country': 'CA', 'exchange': 'NYSE',   'note': 'Cameco Corporation (Canadian uranium)'},
    # 2026-07-15 universe USD 전수 스캔(SEC submissions API)으로 활성 FPI 10종 일괄 등록.
    # 판별 기준: 최신 6-K가 현행이고 최근 8-K/10-K 없음. (NXPI/SATL/SHOP/SN은 8-K 전환 완료라 제외)
    'AS':    {'country': 'FI', 'exchange': 'NYSE',   'note': 'Amer Sports'},
    'BABA':  {'country': 'CN', 'exchange': 'NYSE',   'note': 'Alibaba Group (ADR)'},
    'ERIC':  {'country': 'SE', 'exchange': 'NASDAQ', 'note': 'Ericsson (ADR)'},
    'JD':    {'country': 'CN', 'exchange': 'NASDAQ', 'note': 'JD.com (ADR)'},
    'NOK':   {'country': 'FI', 'exchange': 'NYSE',   'note': 'Nokia (ADR)'},
    'NVO':   {'country': 'DK', 'exchange': 'NYSE',   'note': 'Novo Nordisk (ADR)'},
    'NXE':   {'country': 'CA', 'exchange': 'NYSE',   'note': 'NexGen Energy (Canadian uranium)'},
    'ONON':  {'country': 'CH', 'exchange': 'NYSE',   'note': 'On Holding'},
    'SE':    {'country': 'SG', 'exchange': 'NYSE',   'note': 'Sea Ltd (ADR)'},
    'SPOT':  {'country': 'LU', 'exchange': 'NYSE',   'note': 'Spotify Technology'},
}


# ─── Universe USD 종목 폴백 (Sheets fetch 실패 시 비상용) ───
# 평상시에는 get_universe_usd()가 Google Sheets에서 라이브 fetch.
# Sheets 호출이 막혔을 때만 이 목록으로 동작 — 운영 안정성 안전망.
UNIVERSE_USD_DRAFT: list[str] = [
    # 반도체
    'ASML', 'TSM', 'MU', 'LRCX', 'KLAC', 'INTC', 'TXN', 'ON',
    # 메모리/스토리지
    'STX', 'WDC',
    # 헬스케어
    'AMGN', 'JNJ', 'MRK', 'GILD',
    # 산업/방산
    'HON', 'MSI', 'ETN',
    # 리테일
    'COST', 'WMT', 'ULTA', 'TPR',
    # 통신
    'T',
]


@lru_cache(maxsize=1)
def get_universe_usd() -> tuple[str, ...]:
    """대시보드 Google Sheets `universe` 시트에서 통화=USD 종목 ticker 리스트 fetch.

    Sheets 호출 실패·결과 0건 시 UNIVERSE_USD_DRAFT 폴백.
    캐시는 lru_cache(maxsize=1) — 프로세스 lifetime. runner.py가 oneshot이라
    매 사이클마다 새 프로세스로 fetch (= 자연스럽게 매일 1회 갱신).

    반환: tuple (lru_cache 호환 위해 immutable). 호출자가 list 필요하면 list(...)로 변환.

    소스 우선순위: 자체 리스트 universe.json (GHA fetch_universe.py가 매일 07:00·
    18:30 KST 생성) → 옛 Google Sheets 폴백 → DRAFT. Sheets는 미국 장 직후
    통화 컬럼이 '로드 중...'으로 비는 시간대가 있어 신뢰도가 낮음.
    """
    values = None
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'universe.json')
    try:
        with open(local_path, encoding='utf-8') as f:
            values = json.load(f).get('values') or None
    except Exception as e:
        logger.warning(f'universe.json 로드 실패 → Sheets 폴백: {e}')

    try:
        if values is None:
            import requests  # 호출 시점에 import (테스트·CLI 시 의존성 미설치 환경 보호)
            url = f'https://sheets.googleapis.com/v4/spreadsheets/{SHEETS_ID}/values/universe?key={SHEETS_API_KEY}'
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            values = r.json().get('values', [])
        if not values:
            raise RuntimeError('universe values empty')
        header = values[0]
        curr_idx = header.index('통화')
        ticker_idx = header.index('티커')
    except Exception as e:
        logger.warning(f'Universe fetch 실패, DRAFT 22종목 폴백: {e}')
        return tuple(UNIVERSE_USD_DRAFT)

    tickers: list[str] = []
    seen: set[str] = set()
    for row in values[1:]:
        if len(row) <= max(curr_idx, ticker_idx):
            continue
        if row[curr_idx].strip().upper() != 'USD':
            continue
        raw = row[ticker_idx].strip().upper()
        # 'NYSE:NVDA' 같은 prefix 제거 (universe 시트 일부 행이 거래소 prefix 포함)
        if ':' in raw:
            raw = raw.split(':', 1)[1].strip()
        if raw and raw not in seen:
            tickers.append(raw)
            seen.add(raw)
    if not tickers:
        logger.warning('Sheets universe USD 0건 매칭, DRAFT 폴백')
        return tuple(UNIVERSE_USD_DRAFT)
    logger.info(f'Sheets universe: USD {len(tickers)}종목 로드')
    return tuple(tickers)


def is_foreign_issuer(ticker: str) -> bool:
    return ticker.upper() in FOREIGN_PRIVATE_ISSUERS


def get_filing_type(ticker: str) -> FilingType:
    """발행인 유형에 따라 추적할 form 종류 반환."""
    return '6-K' if is_foreign_issuer(ticker) else '8-K'


def get_issuer_meta(ticker: str) -> dict | None:
    return FOREIGN_PRIVATE_ISSUERS.get(ticker.upper())


# ─── CIK 매핑 (edgartools lazy lookup + 영구 캐시) ───
def _load_cache() -> dict[str, str]:
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict[str, str]) -> None:
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2, sort_keys=True)


@lru_cache(maxsize=512)
def _resolve_via_edgartools(ticker: str) -> str | None:
    """edgartools로 CIK 조회. SEC tickers.json 기반."""
    try:
        from edgar import Company
        company = Company(ticker.upper())
        cik = getattr(company, 'cik', None)
        if cik is None:
            return None
        return str(int(cik)).zfill(10)  # SEC 표준 10자리 zero-pad
    except Exception:
        return None


def resolve_cik(ticker: str, *, refresh: bool = False) -> str | None:
    """ticker → CIK (10자리 zero-pad). 캐시→edgartools 순. 실패 시 None."""
    ticker = ticker.upper()
    cache = _load_cache()
    if not refresh and ticker in cache:
        return cache[ticker]
    cik = _resolve_via_edgartools(ticker)
    if cik:
        cache[ticker] = cik
        _save_cache(cache)
    return cik


@lru_cache(maxsize=512)
def get_company_name(ticker: str) -> str | None:
    """ticker → SEC 공식 회사명 (예: 'Reddit, Inc.'). matcher 회사명 fuzzy 매칭용.

    set_identity()를 1회 호출 — 없으면 SEC가 UA 요청을 거부해 None만 반환.
    lru_cache 첫 호출 시에만 실행되며 edgartools 내부에서 idempotent하게 동작.
    """
    try:
        from edgar import Company, set_identity
        set_identity(os.getenv('SEC_EDGAR_USER_AGENT', 'Kimtaesik (kts77775@gmail.com)'))
        c = Company(ticker.upper())
        name = getattr(c, 'name', None)
        return str(name) if name else None
    except Exception:
        return None


@lru_cache(maxsize=512)
def get_fiscal_year_end_month(ticker: str) -> int:
    """ticker → 회계연도 종료 월 (1-12). 조회 실패 시 12 (캘린더) 반환.

    edgartools Company.fiscal_year_end는 'MMDD' 문자열 (예: TPR='0627', AAPL='0928').
    transcript_sources가 비-캘린더 FY 기업(TPR=6월, AAPL=9월, NVDA=1월 등)의
    fiscal_quarter를 정확히 산출하도록 lookup 제공.
    """
    try:
        from edgar import Company, set_identity
        set_identity(os.getenv('SEC_EDGAR_USER_AGENT', 'Kimtaesik (kts77775@gmail.com)'))
        c = Company(ticker.upper())
        fye = getattr(c, 'fiscal_year_end', None)
        if fye and len(fye) >= 2:
            m = int(fye[:2])
            if 1 <= m <= 12:
                return m
    except Exception:
        pass
    return 12


def warmup_universe_cache() -> dict[str, str | None]:
    """Universe 전체 CIK 사전 채우기. Phase 0 검증 + 운영 준비용."""
    result = {}
    for t in UNIVERSE_USD_DRAFT:
        result[t] = resolve_cik(t)
    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'warmup':
        result = warmup_universe_cache()
        for t, cik in result.items():
            ftype = get_filing_type(t)
            tag = 'FPI' if is_foreign_issuer(t) else 'US'
            print(f"[{tag}] {t:6s} {ftype} CIK={cik or 'MISS'}")
        miss = [t for t, c in result.items() if c is None]
        if miss:
            print(f"\n[WARN] CIK lookup 실패: {miss}")
    elif len(sys.argv) > 1 and sys.argv[1] == 'name-check':
        # P2 set_identity 패치 검증: 9종 SEC 회사명이 None이 아닌지 확인.
        # 네트워크/SEC 의존이라 SKIP_NAME_CHECK=1 환경변수 또는 오프라인 시 skip.
        if os.getenv('SKIP_NAME_CHECK', '').lower() in ('1', 'true', 'yes'):
            print('[SKIP] SKIP_NAME_CHECK=1 — name-check 건너뜀')
            sys.exit(0)
        expected = {
            'CORZ': 'Core Scientific, Inc./tx',
            'TPR': 'TAPESTRY, INC.',
            'BMY': 'BRISTOL MYERS SQUIBB CO',
        }
        fails = []
        for t, exp in expected.items():
            try:
                got = get_company_name(t)
            except Exception as e:
                fails.append((t, f'예외: {e}'))
                continue
            if got != exp:
                fails.append((t, f'expected={exp!r} got={got!r}'))
            else:
                print(f'[OK] {t}: {got}')
        if fails:
            for t, reason in fails:
                print(f'[FAIL] {t}: {reason}')
            sys.exit(1)
        print('\nname-check OK (3/3)')
    else:
        print("Usage: python ticker_registry.py [warmup|name-check]")
