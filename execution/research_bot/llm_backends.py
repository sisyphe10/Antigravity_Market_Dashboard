"""리서치노트 일일요약 LLM 백엔드 체인 (2026-08-18 설계 v3, codex 검토 2회 반영).

체인: 1차 headless Claude(구독 0원) → 2차 codex exec(ChatGPT 구독 0원)
      → 3차 유료 API(RESEARCH_ALLOW_PAID_FALLBACK=1일 때만) → ChainExhausted.

스위치:
- RESEARCH_LLM=api          : 체인 전체 우회, v0 유료 API 경로 직행 (롤백)
- RESEARCH_ALLOW_PAID_FALLBACK=1 : 체인 내 3차 유료 폴백 허용 (기본 0 = 크레딧 소비 0 보장)

예산(설계 v3 §0-3): 총 25분 — 1차 min(600s, 잔여) · 2차 min(480s, 잔여) · 3차 잔여.
잔여 60s 미만이면 해당 단계 skip.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import re
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

TOTAL_BUDGET_SEC = int(os.getenv('RESEARCH_SUMMARY_BUDGET', '1500'))
STAGE1_CAP = 600
STAGE2_CAP = 480
MIN_STAGE_SEC = 60
API_MODEL = 'claude-sonnet-4-6'   # v0 경로 그대로 (롤백 무변경 원칙)

SYSTEM_PROMPT = '사용자가 준 지시문을 그대로, 지정된 출력 형식대로 수행한다.'

# 출력 시크릿 스캔 (설계 v3 §0-1) — 검출 시 해당 백엔드 실패 처리
SECRET_RE = re.compile(
    r'(sk-ant-[A-Za-z0-9_\-]{10,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}'
    r'|xox[bap]-[A-Za-z0-9\-]{10,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY)')

REFUSAL_MARKERS = ('죄송하지만', '죄송합니다', "i'm sorry", 'i cannot', 'i can’t')


@dataclass
class BackendResult:
    text: str
    provenance: dict
    warnings: list = field(default_factory=list)
    manifest: list = field(default_factory=list)


class ChainExhausted(RuntimeError):
    """전 백엔드 실패 — str(e)에 단계별 1줄 사유 (알림용, 상세는 로그)."""


class GateFail(RuntimeError):
    pass


def _load_headless():
    """earnings_bot/headless_llm.py를 고유 모듈명으로 로드 (설계 v3 §6 — sys.path 오염 금지)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '..', 'earnings_bot', 'headless_llm.py')
    spec = importlib.util.spec_from_file_location('earnings_headless_llm',
                                                  os.path.abspath(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _quality_gate(text: str, manifest_indices: set, warnings: list) -> str:
    """백엔드 공통 출력 게이트 (설계 v3 §4-4). 실패 시 GateFail → 다음 백엔드로."""
    if len(text) < 500:
        raise GateFail(f'본문 과소 ({len(text)}자)')
    if '## ' not in text:
        raise GateFail('토픽 헤딩(## ) 없음')
    if text.lstrip().lower().startswith(REFUSAL_MARKERS):
        raise GateFail('거절문으로 시작')
    m = SECRET_RE.search(text)
    if m:
        raise GateFail(f'시크릿 패턴 검출({m.group(0)[:12]}…)')
    # [IMG:n] 검증: manifest 밖 번호는 라인 제거 (게시 오염 방지)
    kept, removed = [], []
    for line in text.split('\n'):
        im = re.match(r'^\s*\[IMG:(\d+)\]\s*$', line)
        if im and int(im.group(1)) not in manifest_indices:
            removed.append(im.group(1))
            continue
        kept.append(line)
    if removed:
        warnings.append(f'유효하지 않은 이미지 번호 제거: {", ".join(removed)}')
    return '\n'.join(kept)


def _call_api_v0(all_content: list) -> str:
    """v0 유료 API 경로 그대로 (롤백 충실 — 3회×5분 재시도 유지)."""
    import anthropic
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY not set')
    client = anthropic.Anthropic(api_key=api_key)
    for attempt in range(3):
        try:
            response = client.messages.create(
                model=API_MODEL, max_tokens=16384,
                messages=[{'role': 'user', 'content': all_content}])
            return response.content[0].text
        except Exception as e:
            err_str = str(e).lower()
            if '529' in str(e) or 'overloaded' in err_str or '429' in str(e) or 'rate_limit' in err_str:
                if attempt < 2:
                    time.sleep(300)
                    continue
            raise
    raise RuntimeError('unreachable')


def _call_api_once(all_content: list) -> str:
    """체인 3차용 — 재시도 없이 1회만 (설계 v3 [C#9] 크레딧 소비 통제)."""
    import anthropic
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY not set')
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=API_MODEL, max_tokens=16384,
        messages=[{'role': 'user', 'content': all_content}])
    return response.content[0].text


def _codex_prompt(prompt: str, manifest: list) -> str:
    """codex용 프롬프트 — 이미지는 base64 블록 대신 첨부(-i)이므로 대응표를 명시
    (설계 v3 [2차 #2] — [IMG:n]의 n = 메시지 번호 매핑 보존)."""
    if not manifest:
        return prompt
    lines = ['', '## 첨부 이미지 대응표 (중요 — 이미지 번호는 이 표만 따를 것)']
    for i, m in enumerate(manifest, 1):
        lines.append(f'- 첨부 {i}번째 이미지 = 메시지 [{m["index"]}] → 본문 삽입 표기는 [IMG:{m["index"]}]')
    return prompt + '\n'.join(lines)


def summarize(prompt: str, all_content: list, manifest: list, date_str: str) -> BackendResult:
    """체인 실행. all_content = API user content 블록(텍스트+이미지, v0와 동일 구조).
    성공 시 BackendResult, 전 백엔드 실패 시 ChainExhausted."""
    mode = os.getenv('RESEARCH_LLM', 'headless')
    manifest_indices = {m['index'] for m in manifest}
    warnings: list = []
    attempts: list = []

    if mode == 'api':
        # 롤백 경로 — v0 그대로
        text = _call_api_v0(all_content)
        text = _quality_gate(text, manifest_indices, warnings)
        return BackendResult(text=text, warnings=warnings, manifest=manifest,
                             provenance={'backend': 'api(rollback)', 'model': API_MODEL,
                                         'attempts': ['api(rollback)=ok']})

    deadline = time.monotonic() + TOTAL_BUDGET_SEC

    def remaining() -> int:
        return int(deadline - time.monotonic())

    # ---- 1차: headless Claude ----
    if remaining() >= MIN_STAGE_SEC:
        try:
            hl = _load_headless()
            budget = min(STAGE1_CAP, remaining())
            try:
                r = hl.call_multimodal(SYSTEM_PROMPT, all_content, timeout_sec=budget)
                text = _quality_gate(r['text'], manifest_indices, warnings)
                attempts.append('headless=ok')
                return BackendResult(text=text, warnings=warnings, manifest=manifest,
                                     provenance={'backend': 'headless', 'model': r['resolved_model'],
                                                 'elapsed_s': r['elapsed_s'], 'attempts': attempts})
            except hl.HeadlessAuthError as e:
                warnings.append('⚠️ H7: headless OAuth 만료 — ssh -t macmini → claude → /login 필요')
                attempts.append(f'headless=AuthError:{str(e)[:60]}')
            except hl.HeadlessQuotaError as e:
                attempts.append(f'headless=QuotaError:{str(e)[:60]}')
            except Exception as e:
                attempts.append(f'headless={type(e).__name__}:{str(e)[:60]}')
        except Exception as e:   # 코어 로드 실패 등
            attempts.append(f'headless=LoadError:{str(e)[:60]}')
        logger.warning(f'[llm_backends] 1차 headless 실패: {attempts[-1]}')
    else:
        attempts.append('headless=skipped(예산 부족)')

    # ---- 2차: codex exec ----
    try:
        import codex_llm
        ok, why = codex_llm.available()
        if not ok:
            attempts.append(f'codex=skipped({why})')
        elif remaining() < MIN_STAGE_SEC:
            attempts.append('codex=skipped(예산 부족)')
        else:
            try:
                budget = min(STAGE2_CAP, remaining())
                image_paths = [m['path'] for m in manifest]
                r = codex_llm.call(_codex_prompt(prompt, manifest), image_paths,
                                   timeout_sec=budget)
                text = _quality_gate(r['text'], manifest_indices, warnings)
                attempts.append('codex=ok')
                warnings.append('ℹ️ 1차 headless 실패 → codex 폴백으로 처리됨')
                return BackendResult(text=text, warnings=warnings, manifest=manifest,
                                     provenance={'backend': 'codex', 'model': r['resolved_model'],
                                                 'elapsed_s': r['elapsed_s'], 'attempts': attempts})
            except Exception as e:
                attempts.append(f'codex={type(e).__name__}:{str(e)[:60]}')
                logger.warning(f'[llm_backends] 2차 codex 실패: {attempts[-1]}')
    except Exception as e:
        attempts.append(f'codex=ImportError:{str(e)[:60]}')

    # ---- 3차: 유료 API (opt-in) ----
    allow_paid = os.getenv('RESEARCH_ALLOW_PAID_FALLBACK', '0') == '1'
    if not allow_paid:
        attempts.append('api=잠김(RESEARCH_ALLOW_PAID_FALLBACK=0)')
    elif remaining() < MIN_STAGE_SEC:
        attempts.append('api=skipped(예산 부족)')
    else:
        warnings.append('⚠️ 유료 API 폴백 진입 — 크레딧 소비 발생')
        try:
            text = _call_api_once(all_content)
            text = _quality_gate(text, manifest_indices, warnings)
            attempts.append('api=ok')
            return BackendResult(text=text, warnings=warnings, manifest=manifest,
                                 provenance={'backend': 'api', 'model': API_MODEL,
                                             'attempts': attempts})
        except Exception as e:
            attempts.append(f'api={type(e).__name__}:{str(e)[:60]}')
            logger.warning(f'[llm_backends] 3차 API 실패: {attempts[-1]}')

    raise ChainExhausted(' / '.join(attempts))
