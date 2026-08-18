"""구독 headless Claude Code CLI 호출 코어 — 어닝봇 전용 순수 텍스트 생성 (도구 0).

2026-08-18 설계 v2 구현 (codex:rescue 검토 11건 반영,
정본=맥미니 ~/work/design/260817_earnings_headless_llm/design_v2_final.md).
API 저수준 호출(_call_sonnet/_call_haiku_long)과 동일한 반환 계약에
provenance(resolved_model/backend/cli_version)를 더해 돌려준다.

★함정 (위키 headless_backend 실측 계승 + 2026-08-18 스모크 실측):
- CLI는 인증 실패에도 exit 0 + subtype='success' — 판정은 본문 'Failed to authenticate'
- env에 ANTHROPIC_API_KEY가 있으면 API 과금으로 붙는다 → allowlist env로 원천 차단
- rate_limit_event는 정상 성공에도 흘러나온다 — 이벤트 존재만으로 쿼터 판정 금지
- modelUsage에는 요청 모델 외에 CLI 내부용 haiku 항목도 섞인다 — 요청 모델 키를 집을 것
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import time

logger = logging.getLogger(__name__)

CLAUDE_BIN = os.getenv('EARNINGS_CLAUDE_BIN', os.path.expanduser('~/.local/bin/claude'))
HEADLESS_MODEL = os.getenv('EARNINGS_HEADLESS_MODEL', 'claude-sonnet-5')
WORK_HOME = os.path.expanduser(os.getenv('EARNINGS_HEADLESS_HOME', '~/.earnings_llm_home'))
TIMEOUT_SEC = int(os.getenv('EARNINGS_HEADLESS_TIMEOUT', '900'))

# 쿼터 소진 본문 마커 (is_error 결과 한정 검사 — 정상 번역문 오탐 방지)
QUOTA_TEXT_MARKERS = ('usage limit', 'rate limit', 'limit reached',
                      'out of extra usage', 'hour limit')


class HeadlessError(RuntimeError):
    """headless 호출 일반 실패 (transient 후보 — call_with_retry가 1회 재시도)."""


class HeadlessAuthError(HeadlessError):
    """구독 인증 실패 — 재시도 무의미. 배치는 즉시 중단해야 한다."""


class HeadlessQuotaError(HeadlessError):
    """구독 쿼터 소진 — 재시도 무의미. 잔여 작업은 pending 유지 후 다음 배치로 이월."""


def _clean_env() -> dict:
    """allowlist env (codex #6) — ANTHROPIC_*/클라우드 공급자 변수를 원천 배제해
    구독(claude.ai OAuth) 인증을 강제한다. dotenv가 os.environ을 오염시켜도 무관."""
    return {
        'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
        'HOME': os.path.expanduser('~'),
        'LANG': 'en_US.UTF-8',
        'LC_ALL': 'en_US.UTF-8',
        'TZ': os.environ.get('TZ', 'Asia/Seoul'),
        'TERM': 'dumb',
        'DISABLE_AUTOUPDATER': '1',
    }


def _ensure_home() -> str:
    """전용 빈 cwd (CLAUDE.md·프로젝트 설정 로드 차단) + 빈 MCP config."""
    os.makedirs(WORK_HOME, exist_ok=True)
    mcp = os.path.join(WORK_HOME, 'empty_mcp.json')
    if not os.path.exists(mcp):
        with open(mcp, 'w', encoding='utf-8') as f:
            f.write('{"mcpServers":{}}')
    return mcp


def serialize_messages(messages: list[dict]) -> str:
    """단일 user 텍스트 턴만 허용 — API messages 범용 흉내 금지 (codex #7)."""
    parts: list[str] = []
    for m in messages:
        if m.get('role') != 'user':
            raise HeadlessError(f"headless는 user 턴만 지원: role={m.get('role')}")
        c = m.get('content')
        if isinstance(c, str):
            parts.append(c)
        elif isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and b.get('type') == 'text':
                    parts.append(b['text'])
                else:
                    bt = b.get('type') if isinstance(b, dict) else type(b).__name__
                    raise HeadlessError(f'지원하지 않는 content 블록: {bt}')
        else:
            raise HeadlessError(f'지원하지 않는 content 형식: {type(c).__name__}')
    if not any(p.strip() for p in parts):
        raise HeadlessError('빈 messages')
    return '\n\n'.join(parts)


def preflight() -> dict:
    """배치 시작 전 구독 인증 확인. 실패 시 HeadlessAuthError (codex #6)."""
    _ensure_home()
    try:
        p = subprocess.run([CLAUDE_BIN, 'auth', 'status'], capture_output=True,
                           text=True, timeout=60, env=_clean_env(), cwd=WORK_HOME)
        j = json.loads(p.stdout)
    except Exception as e:
        raise HeadlessAuthError(f'auth status 확인 실패: {e}')
    if not (j.get('loggedIn') and j.get('authMethod') == 'claude.ai'):
        raise HeadlessAuthError(f'구독 인증 아님: {json.dumps(j, ensure_ascii=False)[:200]}')
    return j


def _kill_group(proc: subprocess.Popen) -> None:
    """자식 프로세스 그룹 전체 정리 (TERM → 3초 유예 → KILL)."""
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=3)
            return
        except subprocess.TimeoutExpired:
            continue


def _events_from(out: str) -> list[dict]:
    events = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        if isinstance(e, dict):
            events.append(e)
    return events


def call(system_prompt: str, messages: list[dict], *, model: str | None = None,
         timeout_sec: int | None = None) -> dict:
    """headless 1회 호출. 반환 계약 = API _call_* 상위집합:
    {text, input_tokens, output_tokens, cache_read_input_tokens,
     cache_creation_input_tokens, stop_reason, resolved_model, backend, cli_version}
    """
    model = model or HEADLESS_MODEL
    mcp_cfg = _ensure_home()
    prompt = serialize_messages(messages)
    limit = timeout_sec or TIMEOUT_SEC

    # 도구 봉인 스택 (codex #3) — 2026-08-18 macmini 스모크 실측: tools=[], mcp_servers=[]
    cmd = [
        CLAUDE_BIN, '-p',
        '--input-format', 'text',
        '--output-format', 'stream-json', '--verbose',
        '--model', model,
        '--system-prompt', system_prompt,        # 대체 모드 — CLI 기본 페르소나 미혼입
        '--safe-mode',
        '--tools', '',
        '--disallowedTools', '*',
        '--strict-mcp-config', '--mcp-config', mcp_cfg,
        '--no-session-persistence',
        '--max-turns', '1',
    ]
    t0 = time.time()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=WORK_HOME, env=_clean_env(),
                            text=True, encoding='utf-8', start_new_session=True)
    try:
        out, err = proc.communicate(input=prompt, timeout=limit)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        raise HeadlessError(f'timeout {limit}s (모델={model}, 입력 {len(prompt):,}자)')

    events = _events_from(out)
    result = next((e for e in events if e.get('type') == 'result'), None)
    rl_dump = json.dumps([e for e in events if 'rate_limit' in str(e.get('type', ''))])

    if result is None:
        # ★쿼터 완전 소진 시 result 자체가 안 나올 수 있다 — rejected/blocked 흔적으로 판별
        if '"rejected"' in rl_dump or '"blocked"' in rl_dump:
            raise HeadlessQuotaError(f'쿼터 소진 추정 (result 없음): {rl_dump[:200]}')
        raise HeadlessError(f'result 이벤트 없음 rc={proc.returncode} stderr={err[:200]!r}')

    text = (result.get('result') or '').strip()
    low = text.lower()

    # ★인증 실패는 exit 0 + is_error=False 로도 온다 (위키 8/8 실측) — 본문 판정이 정본
    if 'failed to authenticate' in low:
        raise HeadlessAuthError(text[:200])

    if result.get('is_error'):
        if (any(m in low for m in QUOTA_TEXT_MARKERS)
                or '"rejected"' in rl_dump or '"blocked"' in rl_dump):
            raise HeadlessQuotaError(text[:200] or rl_dump[:200])
        raise HeadlessError(f"result error: {result.get('subtype')} {text[:200]!r}")

    if result.get('permission_denials'):
        raise HeadlessError(f"permission denial 발생 — 봉인 구성 오류: "
                            f"{str(result['permission_denials'])[:200]}")

    # 도구 봉인 사후 검증 (codex #3): tool_use가 하나라도 있으면 실패
    tool_uses = 0
    for e in events:
        if e.get('type') == 'assistant':
            for b in (e.get('message', {}).get('content') or []):
                if isinstance(b, dict) and b.get('type') == 'tool_use':
                    tool_uses += 1
    if tool_uses:
        raise HeadlessError(f'tool_use {tool_uses}건 혼입 — 도구 봉인 실패')

    # 모델 해석 검증 (codex #1) — 조용한 모델 폴백 금지
    mu = result.get('modelUsage') or {}
    resolved = None
    if model in mu:
        resolved = model
    else:
        for k in mu:
            if k.startswith(model):
                resolved = k
                break
    if mu and resolved is None:
        raise HeadlessError(f'모델 불일치: 요청 {model} vs 실사용 {sorted(mu.keys())}')

    if not text:
        raise HeadlessError('빈 result 본문')

    usage = mu.get(resolved, {}) if resolved else {}
    sys_ev = next((e for e in events if e.get('type') == 'system'), {})
    return {
        'text': text,
        'input_tokens': usage.get('inputTokens', 0),
        'output_tokens': usage.get('outputTokens', 0),
        'cache_read_input_tokens': usage.get('cacheReadInputTokens', 0),
        'cache_creation_input_tokens': usage.get('cacheCreationInputTokens', 0),
        'stop_reason': result.get('stop_reason') or 'end_turn',
        'resolved_model': resolved or model,
        'backend': 'headless',
        'cli_version': sys_ev.get('claude_code_version', ''),
        'elapsed_s': round(time.time() - t0, 1),
    }


def call_with_retry(system_prompt: str, messages: list[dict], *, model: str | None = None,
                    timeout_sec: int | None = None) -> dict:
    """transient(HeadlessError)만 1회 재시도. Auth/Quota는 즉시 전파 (codex #4).
    stamina @api_retry를 태우지 않는 것이 핵심 — 쿼터 소진 메시지의 'rate limit'
    문자열이 transient로 오판돼 5회 재시도되는 사고를 차단한다."""
    try:
        return call(system_prompt, messages, model=model, timeout_sec=timeout_sec)
    except (HeadlessAuthError, HeadlessQuotaError):
        raise
    except HeadlessError as e:
        logger.warning(f'[headless_llm] transient 실패, 1회 재시도: {e}')
        time.sleep(5)
        return call(system_prompt, messages, model=model, timeout_sec=timeout_sec)


def call_multimodal(system_prompt: str, content: list, *, model: str | None = None,
                    timeout_sec: int | None = None) -> dict:
    """이미지 포함 1회 호출 — --input-format stream-json (2026-08-18, 리서치노트 봇 전용).

    content = API user content 블록 리스트(text / base64 image만 허용).
    봉인 스택·사후검증·오류 위계·반환 계약은 call()과 동일하며, call() 경로는
    바이트 무변경으로 유지한다 (설계 v3 [C#2] — 텍스트 경로 회귀 0 원칙).
    2026-08-18 macmini 스모크 실측: stream-json 입력의 image 블록 정상 처리 확인.
    """
    model = model or HEADLESS_MODEL
    mcp_cfg = _ensure_home()
    limit = timeout_sec if timeout_sec is not None else TIMEOUT_SEC
    if limit <= 0:
        raise HeadlessError('예산 소진 (timeout<=0) — 호출 전 skip 해야 한다')

    approx_chars = 0
    for b in content:
        if not isinstance(b, dict) or b.get('type') not in ('text', 'image'):
            bt = b.get('type') if isinstance(b, dict) else type(b).__name__
            raise HeadlessError(f'지원하지 않는 content 블록: {bt}')
        if b['type'] == 'text':
            approx_chars += len(b.get('text') or '')
    if approx_chars == 0:
        raise HeadlessError('빈 content')

    event = json.dumps({'type': 'user', 'message': {'role': 'user', 'content': content}},
                       ensure_ascii=False)

    cmd = [
        CLAUDE_BIN, '-p',
        '--input-format', 'stream-json',
        '--output-format', 'stream-json', '--verbose',
        '--model', model,
        '--system-prompt', system_prompt,
        '--safe-mode',
        '--tools', '',
        '--disallowedTools', '*',
        '--strict-mcp-config', '--mcp-config', mcp_cfg,
        '--no-session-persistence',
        '--max-turns', '1',
    ]
    t0 = time.time()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=WORK_HOME, env=_clean_env(),
                            text=True, encoding='utf-8', start_new_session=True)
    try:
        out, err = proc.communicate(input=event + '\n', timeout=limit)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        raise HeadlessError(f'timeout {limit}s (모델={model}, 텍스트 {approx_chars:,}자 멀티모달)')

    events = _events_from(out)
    result = next((e for e in events if e.get('type') == 'result'), None)
    rl_dump = json.dumps([e for e in events if 'rate_limit' in str(e.get('type', ''))])

    if result is None:
        if '"rejected"' in rl_dump or '"blocked"' in rl_dump:
            raise HeadlessQuotaError(f'쿼터 소진 추정 (result 없음): {rl_dump[:200]}')
        raise HeadlessError(f'result 이벤트 없음 rc={proc.returncode} stderr={err[:200]!r}')

    text = (result.get('result') or '').strip()
    low = text.lower()

    if 'failed to authenticate' in low:
        raise HeadlessAuthError(text[:200])

    if result.get('is_error'):
        if (any(m in low for m in QUOTA_TEXT_MARKERS)
                or '"rejected"' in rl_dump or '"blocked"' in rl_dump):
            raise HeadlessQuotaError(text[:200] or rl_dump[:200])
        raise HeadlessError(f"result error: {result.get('subtype')} {text[:200]!r}")

    if result.get('permission_denials'):
        raise HeadlessError(f"permission denial 발생 — 봉인 구성 오류: "
                            f"{str(result['permission_denials'])[:200]}")

    tool_uses = 0
    for e in events:
        if e.get('type') == 'assistant':
            for b in (e.get('message', {}).get('content') or []):
                if isinstance(b, dict) and b.get('type') == 'tool_use':
                    tool_uses += 1
    if tool_uses:
        raise HeadlessError(f'tool_use {tool_uses}건 혼입 — 도구 봉인 실패')

    mu = result.get('modelUsage') or {}
    resolved = None
    if model in mu:
        resolved = model
    else:
        for k in mu:
            if k.startswith(model):
                resolved = k
                break
    if mu and resolved is None:
        raise HeadlessError(f'모델 불일치: 요청 {model} vs 실사용 {sorted(mu.keys())}')

    if not text:
        raise HeadlessError('빈 result 본문')

    usage = mu.get(resolved, {}) if resolved else {}
    sys_ev = next((e for e in events if e.get('type') == 'system'), {})
    return {
        'text': text,
        'input_tokens': usage.get('inputTokens', 0),
        'output_tokens': usage.get('outputTokens', 0),
        'cache_read_input_tokens': usage.get('cacheReadInputTokens', 0),
        'cache_creation_input_tokens': usage.get('cacheCreationInputTokens', 0),
        'stop_reason': result.get('stop_reason') or 'end_turn',
        'resolved_model': resolved or model,
        'backend': 'headless',
        'cli_version': sys_ev.get('claude_code_version', ''),
        'elapsed_s': round(time.time() - t0, 1),
    }
