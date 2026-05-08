"""Anthropic web_search tool 래퍼 — transcript URL 1순위 검색.

Anthropic API의 server-side web_search tool 사용:
- $10/1k searches + 토큰 (Haiku 4.5: $1/MTok in, $5/MTok out)
- 호출당 ~$0.012 (어닝봇 월 50~100건 → ~$0.6~1.2/월)
- 기존 ANTHROPIC_API_KEY 재활용, 신규 계정·CSE 설정 불필요
- allowed_domains 파라미터로 fool.com / marketbeat.com 도메인 제한

Anthropic SDK 응답에서 `web_search_tool_result` 블록을 파싱하여 URL 후보 추출.
실패·rate limit 시 빈 리스트 반환 (caller가 fallback 결정).
"""
from __future__ import annotations

import logging
import os

from . import TranscriptCandidate

logger = logging.getLogger(__name__)

WEB_SEARCH_TOOL_VERSION = 'web_search_20250305'
SEARCH_MODEL = 'claude-haiku-4-5'
# 256으로 했더니 query JSON 마무리 못 하는 edge case 우려 (Codex 리뷰).
# URL은 server tool block에서 오므로 model 출력 토큰과 무관하지만 방어용으로 상향.
DEFAULT_MAX_TOKENS = 512


def anthropic_web_search(query: str, *, site: str | None = None,
                         max_results: int = 5) -> list[TranscriptCandidate]:
    """Anthropic web_search tool로 URL 후보 검색.

    Args:
        query: 자연어 검색 query (예: "AAPL Q2 2026 earnings call transcript")
        site: 도메인 제한 (예: "fool.com"). None이면 제한 없음.
        max_results: 반환 candidate 최대 개수.

    Returns:
        TranscriptCandidate 리스트. ANTHROPIC_API_KEY 미설정·API 오류 시 빈 리스트.
    """
    if not os.getenv('ANTHROPIC_API_KEY'):
        logger.warning('ANTHROPIC_API_KEY 미설정 — web_search 스킵')
        return []

    try:
        import anthropic
    except ImportError:
        logger.error('anthropic SDK 미설치')
        return []

    tool: dict = {
        'type': WEB_SEARCH_TOOL_VERSION,
        'name': 'web_search',
        'max_uses': 1,
    }
    if site:
        tool['allowed_domains'] = [site]

    prompt = (
        f'Search the web for: {query}\n'
        f'Run exactly one search and return the results. '
        f'Do not write any analysis or summary.'
    )

    try:
        client = anthropic.Anthropic(max_retries=1, timeout=30.0)
        resp = client.messages.create(
            model=SEARCH_MODEL,
            max_tokens=DEFAULT_MAX_TOKENS,
            messages=[{'role': 'user', 'content': prompt}],
            tools=[tool],
        )
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
        # 키 만료·tool 비활성화는 재시도해도 안 풀리고 폴백도 의미없음.
        # 운영 중 무경보 영구 0건 방지 — ERROR 로그 + re-raise로 상위 단계가 실패 처리하도록.
        logger.error(f'Anthropic 인증·권한 오류 (web_search): {e}')
        raise
    except Exception as e:
        logger.warning(f'Anthropic web_search 호출 실패: {e}')
        return []

    candidates: list[TranscriptCandidate] = []
    for block in resp.content:
        # SDK는 Pydantic 모델로 type 속성 노출
        if getattr(block, 'type', None) != 'web_search_tool_result':
            continue
        content = getattr(block, 'content', None)
        # 에러 블록 (rate limit 등): content가 dict로 error_code 포함
        if isinstance(content, dict) or hasattr(content, 'error_code'):
            err = (
                content.get('error_code') if isinstance(content, dict)
                else getattr(content, 'error_code', None)
            )
            logger.warning(f'web_search_tool_result error: {err}')
            continue
        if not isinstance(content, list):
            continue
        for result in content:
            url = getattr(result, 'url', None)
            if not url:
                continue
            candidates.append(TranscriptCandidate(
                url=url,
                title=getattr(result, 'title', '') or '',
                snippet='',
                source='anthropic_web_search',
            ))

    return candidates[:max_results]
