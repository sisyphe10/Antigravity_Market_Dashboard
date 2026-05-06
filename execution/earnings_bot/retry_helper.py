"""재시도/백오프 표준 — stamina(이미 edgartools 의존성)로 통일.

호출처:
- SEC EDGAR (10 req/s, 429/503 backoff) → @sec_retry
- Finnhub free tier (60 req/min) → @finnhub_retry
- Notion / Anthropic / Telegram 등 일반 API → @api_retry

원칙:
- 네트워크 일시 오류만 재시도. 4xx 인증/요청 오류는 즉시 실패.
- 지수 백오프 + jitter
- 최대 5회 (Codex 권고: 명시적 정책 필요)
"""
from __future__ import annotations

import logging
from typing import Callable, TypeVar

import stamina

logger = logging.getLogger(__name__)

F = TypeVar('F', bound=Callable)


def _is_transient(exc: BaseException) -> bool:
    """재시도 가치 있는 일시적 오류 판정."""
    msg = str(exc).lower()
    transient_markers = ('429', '503', '502', '504', 'timeout', 'timed out',
                         'connection', 'temporarily', 'rate limit')
    if any(m in msg for m in transient_markers):
        return True
    cls_name = type(exc).__name__.lower()
    if 'timeout' in cls_name or 'connection' in cls_name:
        return True
    return False


# SEC EDGAR — 10 req/s, 보수적으로 0.5초 간격 + 백오프
sec_retry = stamina.retry(
    on=_is_transient,
    attempts=5,
    wait_initial=1.0,
    wait_max=30.0,
    wait_jitter=0.5,
    timeout=120.0,
)

# Finnhub — 60 req/min, 1초 간격 안전
finnhub_retry = stamina.retry(
    on=_is_transient,
    attempts=4,
    wait_initial=2.0,
    wait_max=60.0,
    wait_jitter=1.0,
    timeout=60.0,
)

# 일반 API (Notion, Anthropic, Telegram)
api_retry = stamina.retry(
    on=_is_transient,
    attempts=4,
    wait_initial=1.0,
    wait_max=20.0,
    wait_jitter=0.5,
    timeout=90.0,
)
