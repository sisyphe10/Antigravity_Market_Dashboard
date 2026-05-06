"""ticker → filing_type(8-K vs 6-K) + CIK 매핑.

Codex BLOCKER #1·HIGH 대응. 외국 발행인(Foreign Private Issuer)은 8-K가 아닌
6-K로 실적 공시하므로 edgar_monitor가 두 form 모두 추적해야 함.

운영 원칙:
- 외국 발행인 화이트리스트는 정적 (드물게 변경)
- CIK는 edgartools/SEC tickers.json으로 lazy lookup + 캐시
- Universe 35종목은 Phase 1에서 Google Sheets fetch로 대체 예정
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Literal

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ticker_cik_cache.json')

FilingType = Literal['8-K', '6-K']


# ─── 외국 발행인 (Foreign Private Issuer) 화이트리스트 ───
# 6-K 사용. 추가 시 SEC EDGAR에서 해당 발행인이 실제로 6-K를 사용하는지 확인할 것.
FOREIGN_PRIVATE_ISSUERS: dict[str, dict] = {
    'ASML':  {'country': 'NL', 'exchange': 'NASDAQ', 'note': 'ASML Holding NV (ADR)'},
    'TSM':   {'country': 'TW', 'exchange': 'NYSE',   'note': 'Taiwan Semiconductor (ADR)'},
    # 향후 ADR 추가 시 여기에 등록 (예: BABA, NIO, SHOP, NVO 등)
}


# ─── Universe USD 종목 초안 (Phase 1에서 Google Sheets fetch로 대체) ───
# 출처: 메모리 project_antigravity_earnings_bot.md 명시 22종목 + Phase 1 보완 예정
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
            tag = '🌏 FPI' if is_foreign_issuer(t) else '🇺🇸 US'
            print(f"{tag}  {t:6s}  {ftype}  CIK={cik or 'MISS'}")
        miss = [t for t, c in result.items() if c is None]
        if miss:
            print(f"\n⚠ CIK lookup 실패: {miss}")
    else:
        print("Usage: python ticker_registry.py warmup")
