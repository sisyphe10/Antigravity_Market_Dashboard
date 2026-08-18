"""codex exec 격리 wrapper — 리서치노트 요약 2차 폴백 (2026-08-18 설계 v3).

시크릿 격리가 제1 원칙 (codex 검토 1차 #1 / 2차 #1.1·#1.2):
- env는 allowlist만 — 봇의 텔레그램·Notion·Anthropic 변수 원천 미전달
- HOME = 전용 최소 홈(~/.research_codex_home, 내용물 = .codex/auth.json 사본뿐)
  → 실제 홈의 .ssh/.env/설정 파일 비노출
- 프롬프트는 argv 금지, stdin('-')으로 전달 (ps 노출·argv 한도 회피)
- 수명주기 = headless_llm 패턴 이식: 절대 바이너리·start_new_session·
  프로세스 그룹 TERM→KILL·mkstemp 출력 파일·finally 정리
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import tempfile
import time

logger = logging.getLogger(__name__)

CODEX_BIN = os.getenv('RESEARCH_CODEX_BIN', '/opt/homebrew/bin/codex')
CODEX_HOME = os.path.expanduser(os.getenv('RESEARCH_CODEX_HOME', '~/.research_codex_home'))
# 빈 값 = codex 기본 모델 사용 (ChatGPT 계정은 명시 모델 다수 거부 — 2026-08-18 실측:
# 'gpt-5' 지정 시 400 "not supported when using Codex with a ChatGPT account")
CODEX_MODEL = os.getenv('RESEARCH_CODEX_MODEL', '')
WORK_DIR = os.path.join(CODEX_HOME, 'work')


class CodexError(RuntimeError):
    pass


def available() -> tuple[bool, str]:
    """(가용 여부, 불가 사유). 미설치/미인증이면 체인이 이 단계를 skip한다."""
    if not os.path.exists(CODEX_BIN):
        return False, f'미설치({CODEX_BIN} 없음)'
    if not os.path.exists(os.path.join(CODEX_HOME, '.codex', 'auth.json')):
        return False, '미인증(전용 홈에 auth.json 없음)'
    return True, ''


def _codex_env() -> dict:
    return {
        'PATH': '/opt/homebrew/bin:/usr/bin:/bin',
        'HOME': CODEX_HOME,                 # 전용 최소 홈 — 실제 홈 비노출
        'CODEX_HOME': os.path.join(CODEX_HOME, '.codex'),
        'LANG': 'en_US.UTF-8',
        'LC_ALL': 'en_US.UTF-8',
        'TZ': 'Asia/Seoul',
        'TERM': 'dumb',
    }


def _kill_group(proc: subprocess.Popen) -> None:
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


def call(prompt: str, image_paths: list[str], *, timeout_sec: int) -> dict:
    """codex exec 1회 호출. 반환 = {text, resolved_model, backend, elapsed_s}."""
    if timeout_sec <= 0:
        raise CodexError('예산 소진 (timeout<=0)')
    ok, why = available()
    if not ok:
        raise CodexError(f'codex 불가: {why}')
    os.makedirs(WORK_DIR, exist_ok=True)

    fd, out_path = tempfile.mkstemp(dir=WORK_DIR, suffix='.md')
    os.close(fd)
    os.chmod(out_path, 0o600)
    t0 = time.time()
    try:
        cmd = [CODEX_BIN, 'exec',
               '--sandbox', 'read-only',
               '--skip-git-repo-check',
               '--cd', WORK_DIR,
               '--output-last-message', out_path]
        if CODEX_MODEL:
            cmd += ['--model', CODEX_MODEL]
        for p in image_paths:
            cmd += ['--image', p]
        cmd += ['-']    # 프롬프트 = stdin

        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, cwd=WORK_DIR, env=_codex_env(),
                                text=True, encoding='utf-8', start_new_session=True)
        try:
            _, err = proc.communicate(input=prompt, timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            raise CodexError(f'timeout {timeout_sec}s')

        if proc.returncode != 0:
            raise CodexError(f'exit {proc.returncode}: {(err or "")[:200]}')

        try:
            with open(out_path, encoding='utf-8') as f:
                text = f.read().strip()
        except OSError as e:
            raise CodexError(f'출력 파일 읽기 실패: {e}')
        if not text:
            raise CodexError('빈 출력 (exit 0이지만 last-message 없음)')

        return {'text': text, 'resolved_model': CODEX_MODEL or 'codex-default',
                'backend': 'codex', 'elapsed_s': round(time.time() - t0, 1)}
    finally:
        try:
            os.remove(out_path)
        except OSError:
            pass
