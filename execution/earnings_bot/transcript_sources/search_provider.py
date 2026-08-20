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

# headless(구독) 검색이 기본 — API 는 백업(EARNINGS_SEARCH_BACKEND=api, 유료 = 사전 승인 필수, 8/20)
SEARCH_BACKEND = os.getenv('EARNINGS_SEARCH_BACKEND', 'headless')   # headless | api(롤백)
HEADLESS_SEARCH_MODEL = os.getenv('EARNINGS_SEARCH_MODEL', 'claude-haiku-4-5')
try:
    HEADLESS_SEARCH_TIMEOUT = int(os.getenv('EARNINGS_SEARCH_TIMEOUT', '120'))
except ValueError:
    HEADLESS_SEARCH_TIMEOUT = 120
_RESULTS_SCHEMA = {
    'type': 'object',
    'properties': {'results': {'type': 'array', 'maxItems': 8, 'items': {
        'type': 'object',
        'properties': {'url': {'type': 'string'}, 'title': {'type': 'string'}},
        'required': ['url']}}},
    'required': ['results'],
}


def _filter_candidates(pairs, site, max_results):
    """scheme·도메인 경계(host==site or host.endswith('.'+site))·중복 제거 — API allowed_domains 동등성."""
    from urllib.parse import urlparse
    out, seen = [], set()
    for url, title in pairs:
        try:
            pr = urlparse(url)
        except ValueError:
            continue
        if pr.scheme not in ('http', 'https') or not pr.hostname:
            continue
        if site:
            host, sl = pr.hostname.lower(), site.lower()
            if not (host == sl or host.endswith('.' + sl)):
                continue
        if url in seen:
            continue
        seen.add(url)
        out.append(TranscriptCandidate(url=url, title=title or '', snippet='',
                                       source='headless_web_search'))
        if len(out) >= max_results:
            break
    return out


def _headless_web_search(query, site, max_results):
    """claude -p + WebSearch 도구 + --json-schema (2026-08-20 macmini 스모크 실측 성공).

    구독 쿼터 사용(0원). 인증 실패는 raise(무경보 영구 0건 방지 — API AuthenticationError
    re-raise 정책 승계), 그 외 실패·0건은 [] 로 소스 자체 폴백에 맡긴다. 유료 API 자동
    폴백은 두지 않는다(8/20 사용자 규칙). --max-turns 4 는 비용 상한일 뿐 API 의
    max_uses=1 과 동등하지 않다(초과 검색해도 구독 쿼터 외 비용 0)."""
    import json
    import subprocess
    import sys
    earn = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if earn not in sys.path:
        sys.path.insert(0, earn)
    import headless_llm as hl

    q = f'{query} site:{site}' if site else query
    prompt = (f'Search the web for: {q}\n'
              'Run one web search and return only the result URLs you actually found. '
              'Never invent or guess URLs. If nothing relevant is found, return an empty results list.')
    mcp_cfg = hl._ensure_home()
    cmd = [hl.CLAUDE_BIN, '-p',
           '--model', HEADLESS_SEARCH_MODEL,
           '--tools', 'WebSearch',
           '--allowedTools', 'WebSearch',
           '--output-format', 'json',
           '--max-turns', '4',
           '--json-schema', json.dumps(_RESULTS_SCHEMA),
           '--no-session-persistence',
           '--strict-mcp-config', '--mcp-config', mcp_cfg]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=hl.WORK_HOME, env=hl._clean_env(),
                            text=True, encoding='utf-8', start_new_session=True)
    try:
        out, err = proc.communicate(input=prompt, timeout=HEADLESS_SEARCH_TIMEOUT)
    except subprocess.TimeoutExpired:
        hl._kill_group(proc)
        logger.warning('headless web_search timeout %ss', HEADLESS_SEARCH_TIMEOUT)
        return []
    try:
        ev = json.loads((out or '').strip() or '{}')
    except ValueError:
        logger.warning('headless web_search: stdout JSON 아님: %r', (out or '')[:150])
        return []
    text = str(ev.get('result') or '')
    if 'failed to authenticate' in text.lower():
        logger.error('headless web_search 구독 인증 실패 (H7)')
        raise RuntimeError('headless 구독 인증 실패 (H7): ' + text[:150])
    if ev.get('is_error'):
        logger.warning('headless web_search result error: %s', str(ev.get('subtype'))[:120])
        return []
    items = (ev.get('structured_output') or {}).get('results') or []
    pairs = [(str(it.get('url') or ''), str(it.get('title') or ''))
             for it in items if isinstance(it, dict) and it.get('url')]
    return _filter_candidates(pairs, site, max_results)


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
    if SEARCH_BACKEND == 'headless':
        return _headless_web_search(query, site, max_results)

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
