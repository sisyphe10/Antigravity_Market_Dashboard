# -*- coding: utf-8 -*-
"""Opus 계열 최신 모델 자동 해석 — 하드코딩 없이 상위 버전을 따라간다.

왜 필요한가 (2026-08-05):
  CLI의 `--model opus` 별칭은 "최신"이라고 문서화돼 있지만 실측상 뒤처진다
  (CLI 2.1.209에서 opus → claude-opus-4-8, 실제 최신은 claude-opus-5).
  그래서 별칭만 믿지 않고 **상위 메이저를 직접 탐침**해 더 새 쪽을 고른다.
  CLI가 나중에 별칭을 고치면 별칭 쪽이 자동으로 최신이 되므로 양쪽 다 본다.

★Fable/Mythos 는 의도적으로 후보에서 제외한다(사용자 지시 — Opus 계열만).
★탐침 결과는 24시간 캐시. 하루 한 번, 실패 탐침 2~3회(회당 ~5초)만 든다.
"""
import json
import os
import re
import subprocess
import time

DATALAKE_ROOT = os.path.expanduser(os.getenv("DATALAKE_ROOT", "~/datalake"))
CACHE_PATH = os.path.join(DATALAKE_ROOT, ".wiki_model_cache.json")
CACHE_TTL = int(os.getenv("WIKI_MODEL_CACHE_TTL", "86400"))
CLAUDE_BIN = os.path.expanduser(os.getenv("WIKI_CLAUDE_BIN", "~/.local/bin/claude"))
FLOOR = "claude-opus-5"          # 실측 확인된 하한 (이보다 낮게는 절대 안 내려감)
PROBE_AHEAD = 3                  # 현재 메이저 위로 몇 개까지 찔러볼지


def _version_key(model):
    """'claude-opus-4-8' → (4,8) / 'claude-opus-5' → (5,). 튜플 비교로 신구 판정."""
    nums = re.findall(r"\d+", model or "")
    return tuple(int(n) for n in nums) or (0,)


def _run_probe(model):
    """해당 모델로 1턴 세션을 띄워본다. → (성공여부, 실제 해석된 모델명)"""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    try:
        p = subprocess.run(
            [CLAUDE_BIN, "-p", "OK", "--model", model, "--max-turns", "1",
             "--output-format", "stream-json", "--verbose"],
            capture_output=True, text=True, timeout=120, env=env)
    except Exception:
        return False, None
    init, ok = None, False
    for line in (p.stdout or "").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            init = ev.get("model")
        elif ev.get("type") == "result":
            ok = not ev.get("is_error") and bool(ev.get("modelUsage"))
    return ok, init


def _read_cache():
    try:
        with open(CACHE_PATH, encoding="utf-8") as fh:
            c = json.load(fh)
        if time.time() - c.get("at", 0) < CACHE_TTL and c.get("model"):
            return c["model"]
    except Exception:
        pass
    return None


def _write_cache(model, probed):
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump({"model": model, "at": time.time(), "probed": probed}, fh,
                      ensure_ascii=False)
    except OSError:
        pass


def resolve(force=False):
    """사용할 Opus 모델명을 돌려준다. env > 캐시 > 탐침 > FLOOR 순."""
    override = os.getenv("WIKI_CLAUDE_MODEL")
    if override:
        return override
    if not force:
        cached = _read_cache()
        if cached:
            return cached

    best, probed = FLOOR, []

    # ① 별칭이 가리키는 곳 (CLI가 별칭을 고치면 여기가 자동으로 최신이 된다)
    ok, init = _run_probe("opus")
    probed.append({"cand": "opus", "ok": ok, "resolved": init})
    if ok and init and _version_key(init) > _version_key(best):
        best = init

    # ② 현재 메이저 위쪽 메이저를 내림차순 탐침 (첫 성공에서 중단)
    top = _version_key(best)[0]
    for n in range(top + PROBE_AHEAD, top, -1):
        cand = "claude-opus-%d" % n
        ok, init = _run_probe(cand)
        probed.append({"cand": cand, "ok": ok, "resolved": init})
        if ok:
            if _version_key(init or cand) > _version_key(best):
                best = init or cand
            break
    else:
        # 위쪽이 전부 실패 → 하한(FLOOR)이 아직 유효한지 한 번 확인.
        # FLOOR 가 어느 날 은퇴하면 여기서 걸러내고 별칭이 준 모델로 후퇴한다.
        if best == FLOOR:
            ok, init = _run_probe(FLOOR)
            probed.append({'cand': FLOOR, 'ok': ok, 'resolved': init})
            if not ok:
                alias = next((x['resolved'] for x in probed
                              if x['cand'] == 'opus' and x['ok']), None)
                best = alias or 'opus'

    _write_cache(best, probed)
    return best


if __name__ == "__main__":
    import sys
    m = resolve(force="--force" in sys.argv)
    print(m)
    try:
        with open(CACHE_PATH, encoding="utf-8") as fh:
            print(json.dumps(json.load(fh), ensure_ascii=False, indent=1))
    except OSError:
        pass
