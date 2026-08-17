"""headless_llm fake-CLI 픽스처 테스트 — 실패 경로 우선 (설계 v2 §5-1, codex #11).

실행: PYTHONPATH=$PWD venv/bin/python3 execution/earnings_bot/tests_headless_llm.py
실제 claude CLI를 호출하지 않는다 — 시나리오별로 구운 가짜 CLI 스크립트로
스트림 스키마·오류 분류·봉인 검증·재시도 정책을 검사한다.
"""
from __future__ import annotations

import json
import os
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from execution.earnings_bot import headless_llm as H

TMP = tempfile.mkdtemp(prefix='headless_test_')
H.WORK_HOME = os.path.join(TMP, 'home')
FLAG = os.path.join(TMP, 'flaky_flag')

SYS_EV = {"type": "system", "claude_code_version": "2.1.226-test",
          "tools": [], "mcp_servers": [], "model": "claude-sonnet-5"}
OK_USAGE = {"claude-sonnet-5": {"inputTokens": 100, "outputTokens": 50,
                                "cacheReadInputTokens": 7, "cacheCreationInputTokens": 3}}


def make_fake(mode: str) -> str:
    """MODE를 구워 넣은 가짜 CLI 생성 (allowlist env라 env로 못 넘긴다)."""
    lines = [
        "#!/usr/bin/python3",
        "import json, sys, time",
        "sys.stdin.read()",
        f"MODE = {mode!r}",
        f"FLAG = {FLAG!r}",
        f"SYS_EV = {json.dumps(SYS_EV)}",
        f"OK_USAGE = {json.dumps(OK_USAGE)}",
        "def emit(d): print(json.dumps(d))",
        "def ok_result(text='\\ubc88\\uc5ed \\uacb0\\uacfc\\ubb38'):",
        "    emit({'type':'result','subtype':'success','is_error':False,'result':text,",
        "          'stop_reason':'end_turn','modelUsage':OK_USAGE,'permission_denials':[]})",
        "emit(SYS_EV)",
        "if MODE == 'auth_fail':",
        "    emit({'type':'result','subtype':'success','is_error':False,'permission_denials':[],",
        "          'result':'Failed to authenticate: OAuth session expired and could not be refreshed',",
        "          'modelUsage':{}})",
        "elif MODE == 'quota':",
        "    emit({'type':'rate_limit_event','rateLimit':{'overageStatus':'rejected'}})",
        "    emit({'type':'result','subtype':'error_during_execution','is_error':True,",
        "          'result':'5-hour usage limit reached','modelUsage':{},'permission_denials':[]})",
        "elif MODE == 'quota_no_result':",
        "    emit({'type':'rate_limit_event','rateLimit':{'overageStatus':'rejected'}})",
        "elif MODE == 'malformed':",
        "    print('this is not json'); print('{broken')",
        "elif MODE == 'empty':",
        "    emit({'type':'result','subtype':'success','is_error':False,'result':'  ',",
        "          'modelUsage':OK_USAGE,'permission_denials':[]})",
        "elif MODE == 'timeout':",
        "    time.sleep(30); ok_result()",
        "elif MODE == 'tooluse':",
        "    emit({'type':'assistant','message':{'content':[{'type':'tool_use','name':'Bash'}]}})",
        "    ok_result()",
        "elif MODE == 'model_mismatch':",
        "    emit({'type':'result','subtype':'success','is_error':False,'result':'x',",
        "          'modelUsage':{'claude-opus-4-8':{'inputTokens':1,'outputTokens':1}},",
        "          'permission_denials':[]})",
        "elif MODE == 'flaky':",
        "    import os",
        "    if not os.path.exists(FLAG):",
        "        open(FLAG,'w').write('1'); print('garbage — result \\uc5c6\\uc74c')",
        "    else:",
        "        emit({'type':'assistant','message':{'content':[{'type':'text','text':'ok'}]}}); ok_result()",
        "else:",
        "    emit({'type':'assistant','message':{'content':[{'type':'text','text':'ok'}]}}); ok_result()",
    ]
    path = os.path.join(TMP, f'fake_{mode}')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


MSGS = [{'role': 'user', 'content': '테스트 입력'}]
passed = failed = 0


def expect(name, fn, exc=None, check=None):
    global passed, failed
    try:
        r = fn()
    except Exception as e:
        if exc and isinstance(e, exc) and (not check or check(e)):
            print(f'[PASS] {name} — {type(e).__name__}: {str(e)[:80]}')
            passed += 1
        else:
            print(f'[FAIL] {name} — 예상 {exc and exc.__name__}, 실제 {type(e).__name__}: {e}')
            failed += 1
        return
    if exc:
        print(f'[FAIL] {name} — 예외 {exc.__name__} 기대했으나 정상 반환: {str(r)[:100]}')
        failed += 1
    elif check and not check(r):
        print(f'[FAIL] {name} — 반환 검증 실패: {str(r)[:200]}')
        failed += 1
    else:
        print(f'[PASS] {name}')
        passed += 1


# 1~8 시나리오
for mode, exc in [('auth_fail', H.HeadlessAuthError), ('quota', H.HeadlessQuotaError),
                  ('quota_no_result', H.HeadlessQuotaError), ('malformed', H.HeadlessError),
                  ('empty', H.HeadlessError), ('tooluse', H.HeadlessError),
                  ('model_mismatch', H.HeadlessError)]:
    H.CLAUDE_BIN = make_fake(mode)
    expect(f'시나리오 {mode}', lambda: H.call('sys', MSGS), exc=exc)

H.CLAUDE_BIN = make_fake('timeout')
expect('시나리오 timeout(3s)', lambda: H.call('sys', MSGS, timeout_sec=3),
       exc=H.HeadlessError, check=lambda e: 'timeout' in str(e))

H.CLAUDE_BIN = make_fake('success')
expect('시나리오 success 계약', lambda: H.call('sys', MSGS),
       check=lambda r: (r['text'] == '번역 결과문' and r['input_tokens'] == 100
                        and r['output_tokens'] == 50 and r['cache_read_input_tokens'] == 7
                        and r['stop_reason'] == 'end_turn'
                        and r['resolved_model'] == 'claude-sonnet-5'
                        and r['backend'] == 'headless'
                        and r['cli_version'] == '2.1.226-test'))

# 재시도 정책: transient 1회 재시도로 성공 / Auth·Quota는 재시도 없이 전파
H.CLAUDE_BIN = make_fake('flaky')
if os.path.exists(FLAG):
    os.remove(FLAG)
expect('call_with_retry transient 1회 재시도', lambda: H.call_with_retry('sys', MSGS),
       check=lambda r: r['text'] == '번역 결과문')
H.CLAUDE_BIN = make_fake('auth_fail')
expect('call_with_retry Auth 즉시 전파', lambda: H.call_with_retry('sys', MSGS),
       exc=H.HeadlessAuthError)

# 직렬화 가드
expect('직렬화: assistant role 거부',
       lambda: H.serialize_messages([{'role': 'assistant', 'content': 'x'}]),
       exc=H.HeadlessError)
expect('직렬화: 비텍스트 블록 거부',
       lambda: H.serialize_messages([{'role': 'user', 'content': [{'type': 'image'}]}]),
       exc=H.HeadlessError)
expect('직렬화: cache_control 텍스트 블록 수용',
       lambda: H.serialize_messages([{'role': 'user', 'content': [
           {'type': 'text', 'text': 'A', 'cache_control': {'type': 'ephemeral'}}]}]),
       check=lambda r: r == 'A')

print(f'\n결과: {passed} PASS / {failed} FAIL')
sys.exit(1 if failed else 0)
