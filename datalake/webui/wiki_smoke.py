# -*- coding: utf-8 -*-
"""위키 headless 백엔드 계약 검증 (기동 시 + 매일).

왜 필요한가: 답을 만드는 하네스가 **우리 통제 밖**이다. Claude Code CLI 를 올리면
우리 코드를 한 줄도 안 고쳐도 stream-json 스키마·기본 모델·도구 동작이 바뀔 수 있다.
그래서 버전을 못 박는 대신 **바뀐 걸 감지하고, 바뀌었으면 계약이 아직 성립하는지 확인**한다.
(하드 고정은 안 한다 — 사용자가 대화형으로 쓸 때 어차피 갱신되고, 고정하면 조용히 썩는다.)

검사 항목:
  1) CLI 실행 가능 + 버전 (직전 기록과 다르면 표시)
  2) 실제 질문 1건 종단 실행 — MCP 도구 호출과 stream-json 파싱이 살아 있는지
  3) 파싱 결과 계약: answer 비어있지 않음 · steps 최소 1건 · meta.model 존재

실패하면 텔레그램으로 알린다. 성공하면 버전 기록을 갱신한다.
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import headless_backend  # noqa: E402
import wiki_model  # noqa: E402

DATALAKE_ROOT = os.path.expanduser(os.getenv("DATALAKE_ROOT", "~/datalake"))
STATE_PATH = os.path.join(DATALAKE_ROOT, ".wiki_cli_state.json")
CLAUDE_BIN = os.path.expanduser(os.getenv("WIKI_CLAUDE_BIN", "~/.local/bin/claude"))

# 결정적 정답이 있는 질문 — 도구를 반드시 거쳐야 답할 수 있다
PROBE_Q = "search_tags 도구로 삼성전자를 검색해 total 값만 숫자로 답해라. 다른 말은 하지 마라."


def cli_version():
    try:
        p = subprocess.run([CLAUDE_BIN, "--version"], capture_output=True, text=True,
                           timeout=60)
        return (p.stdout or "").strip().split()[0] if p.returncode == 0 else None
    except Exception:
        return None


def _load():
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save(d):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
    except OSError:
        pass


def _notify(text):
    token = os.getenv("TELEGRAM_SISYPHE_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    try:
        import urllib.parse
        import urllib.request
        data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
        urllib.request.urlopen("https://api.telegram.org/bot%s/sendMessage" % token,
                               data=data, timeout=15).read()
    except Exception as e:
        print("[wiki_smoke] 텔레그램 실패: %s" % e, flush=True)


def run(daily=False):
    state = _load()
    prev_ver = state.get("cli_version")
    ver = cli_version()
    problems, notes = [], []

    if not ver:
        problems.append("CLI 실행 불가 (%s)" % CLAUDE_BIN)
    elif prev_ver and ver != prev_ver:
        notes.append("CLI 버전 변경: %s → %s" % (prev_ver, ver))

    model = None
    if not problems:
        if daily:
            model = wiki_model.resolve(force=True)     # 새벽에 탐침 미리 갱신
        else:
            model = wiki_model.resolve()
        t0 = time.time()
        out = headless_backend.run_question(PROBE_Q, timeout_sec=300, max_turns=6)
        elapsed = round(time.time() - t0, 1)
        if not out.get("ok"):
            problems.append("종단 실행 실패: %s" % (out.get("error") or out.get("status")))
        else:
            if not (out.get("answer") or "").strip():
                problems.append("빈 응답")
            if not out.get("steps"):
                problems.append("도구 호출 0건 — MCP 배선 또는 stream-json 파싱 파손 의심")
            if not (out.get("meta") or {}).get("model"):
                problems.append("meta.model 없음 — result 이벤트 스키마 변경 의심")
        notes.append("종단 %s초 · 모델 %s · 도구 %s"
                     % (elapsed, (out.get("meta") or {}).get("model"),
                        [s["tool"] for s in out.get("steps") or []]))

    ok = not problems
    if ok:
        state.update(cli_version=ver, model=model, last_ok=time.time())
        _save(state)
    line = "[wiki_smoke] %s | ver=%s | %s" % ("OK" if ok else "FAIL", ver, " / ".join(notes))
    print(line, flush=True)
    for p in problems:
        print("  ✗ " + p, flush=True)

    if not ok:
        _notify("⚠️ 위키 headless 계약 검증 실패\n\nCLI: %s\n%s\n\n%s"
                % (ver, "\n".join("✗ " + p for p in problems), " / ".join(notes)))
    elif notes and any("버전 변경" in n for n in notes):
        _notify("ℹ️ 위키 headless — CLI 버전이 바뀌었고 계약 검증은 통과했습니다.\n\n%s"
                % " / ".join(notes))
    return ok


if __name__ == "__main__":
    sys.exit(0 if run(daily="--daily" in sys.argv) else 1)
