# -*- coding: utf-8 -*-
"""Datalake 문답 웹 UI — FastAPI + Claude API 에이전틱 루프.

질문 → Claude(claude-opus-4-8, adaptive thinking)가 도구 4종으로 데이터를 직접 조회해 답변:
  run_sql       : market.duckdb 읽기전용 SQL
  search_notes  : research_notes/catalog/architecture-wiki/transcripts md 코퍼스 정규식 검색
  read_file     : 코퍼스 파일 읽기 (datalake·wiki 내부만)
  list_datasets : 카탈로그 INDEX

기동 (맥미니):
  bash datalake/webui/run_webui.sh          # 127.0.0.1:8787
  tailscale serve --bg 8787                 # 테일넷 내부 공개 (외부 미노출)

ANTHROPIC_API_KEY는 레포 .env에서 로드.
"""
import json
import os
import re
import sqlite3
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dl_common import CATALOG_DIR, DATALAKE_ROOT, DUCKDB_PATH, MARKET_DIR, REPO  # noqa: E402

sys.path.insert(0, os.path.join(REPO, "execution"))
import nav_style  # noqa: E402  — AoE 상단 네비 정본 (2026-07-26 통일)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(REPO, ".env"))

import anthropic  # noqa: E402
import duckdb  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

MODEL = "claude-sonnet-5"  # 2026-07-22 Opus 4.8 → Sonnet 5 (비용 절감, 사용자 결정)
MAX_LOOP = 20
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
WIKI_DIR = os.path.join(REPO, "architecture", "wiki")
SEARCH_ROOTS = [
    os.path.join(DATALAKE_ROOT, "research_notes"),
    os.path.join(DATALAKE_ROOT, "transcripts"),  # 어닝콜 한국어 번역 전문 (earnings_bot)
    os.path.join(DATALAKE_ROOT, "analyses"),     # 실적 1-page 분석 시트 md (2026-07-22 Notion→md 이전)
    CATALOG_DIR,
    WIKI_DIR,
]

app = FastAPI()
client = anthropic.Anthropic()

SYSTEM = """너는 자산운용사 운용역(사용자)을 지원하는 리서치 애널리스트다.
아래 자산에서 근거를 찾아 한국어 존댓말로 답한다. 답변은 실무 판단에 바로 쓰이므로
근거 없는 서술을 넣지 않는다.

## 데이터 자산
1. market.duckdb 뷰 (run_sql): 카탈로그는 list_datasets로 확인. 국내 전 상장종목 일봉(수정주가)·시총·밸류에이션·외국인 보유·지수·ETF·투자자별 매매대금·해외 유니버스 일봉.
2. 리서치 노트 원문 (search_notes → read_file): research_notes/YYYY/YYYY-MM-DD.md — 텔레그램으로 수집한 증권사 리포트 요지·기사·메모 원문.
3. 시스템 위키 (search_notes): architecture wiki — 이 대시보드 시스템의 봇·잡·페이지 구조.
4. 어닝콜 번역 전문 (search_notes → read_file): transcripts/YYYY/YYYY-MM-DD_티커_*.md — 미국 유니버스 종목 실적 컨퍼런스콜 한국어 번역 전문. 파일이 길면 read_file의 offset으로 이어서 읽는다.
5. 실적 분석 시트 (search_notes → read_file): analyses/YYYY/YYYY-MM-DD_티커_*.md — 분기 실적 1-page 요약.

## 탐색 규칙 (한도 관리 — 중요)
- 도구 호출 한도는 총 20턴이다. **같은 도구를 비슷한 인자로 반복 호출하지 않는다.**
- 검색이 2회 연속 빈 결과면 그 경로를 포기하고 전략을 바꾼다: search_tags → search_notes(정규식) →
  run_sql → 보유 지식. **3번째 유사 검색은 금지**이며, 시스템이 중복 호출을 차단한다.
- 코퍼스에 없을 법한 질문(아직 일어나지 않은 계약의 금액, 일반 산업 상식, 미래 가정)은
  1~2회만 확인하고 즉시 답변 작성으로 넘어간다.
- **"만약 ~하면 얼마냐" 류 가정형 질문**은 코퍼스에서 *비교 가능한 과거 실계약·실적 기준점*을 찾아
  스케일링해서 답한다. 정확히 일치하는 답이 없다는 이유로 침묵하지 않는다.
  (예: 신규 수주 금액 추정 → 유사 규모 과거 수주 계약가를 기준점으로 용량·스코프 비례 조정)
- 남은 호출이 부족해지면 즉시 지금까지 모은 근거만으로 결론을 낸다.

## 답변 형식
1. **결론** — 질문에 대한 직답 한두 문장.
2. **숫자 근거** — 조회 결과를 표로. 기준일·기간을 반드시 명시하고, 계산이 들어가면 계산 기준(분모·기간)을 적는다.
3. **해석·리스크** — 왜 그런지, 무엇이 이 해석을 깰 수 있는지.
4. **확인 필요** — 데이터로 확인하지 못한 가정이 있으면만 적는다(없으면 생략).

짧은 사실 확인 질문에는 1·2만으로 답한다. 형식을 위해 내용을 늘리지 않는다.

## 규칙
- 수치 질문은 반드시 run_sql로 실제 조회 후 답한다. 추측 금지, 조회 실패 시 실패했다고 밝힌다.
- 먼저 list_datasets로 스키마를 확인하고 SQL을 작성하면 오류가 적다.
- **사실과 추정을 구분한다.** 조회 결과·원문 인용은 사실, 그 외 판단은 "추정", "가능성" 으로 명시한다.
- 리서치/뉴스 맥락 질문은 search_notes로 원문을 찾고, 날짜·출처를 함께 인용한다.
- 절대 수치만 내놓지 않는다. 비교 기준(QoQ·YoY, 섹터·지수 대비, 과거 밴드)을 함께 제시한다.
- 매수·매도를 단정하지 않는다. "X가 유지되면 Y" 식 조건부로 서술한다.
- 코퍼스에 근거가 없으면 "코퍼스에 근거 없음"이라고 밝힌 뒤, 일반 지식으로 답할 수 있는 부분은
  **[추정]** 으로 표시해 답한다. 검색이 비었다는 이유로 답변 자체를 거르지 않는다.
- 표기: % 는 소수점 첫째 자리, 금액은 억원(조 초과 시 NN조 N,NNN억원), 분기는 1Q26, 달러 금액은 $B/$M.
- 표가 적합하면 markdown 표를 쓰고, 불필요한 서론·요약 반복은 넣지 않는다."""

TOOLS = [
    {
        "name": "run_sql",
        "description": "market.duckdb에 읽기전용 SQL(SELECT) 실행. 뷰 이름은 list_datasets로 확인. 결과는 최대 200행.",
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "실행할 SELECT 문"}},
            "required": ["sql"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "search_notes",
        "description": "md 코퍼스(리서치 노트 원문·카탈로그·시스템 위키·어닝콜 번역 전문)를 정규식으로 검색. 파일경로:줄번호와 매칭 줄을 반환.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "검색 정규식 (예: 삼성전자|하이닉스)"},
                "max_results": {"type": "integer", "description": "최대 결과 수 (기본 40)"},
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_file",
        "description": "코퍼스 파일 읽기 (1회 최대 20000자). search_notes가 반환한 경로를 그대로 전달. 응답 끝에 '(truncated ...)'가 붙으면 offset을 늘려 이어서 읽는다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "search_notes 결과의 파일 경로"},
                "offset": {"type": "integer", "description": "읽기 시작 문자 위치 (기본 0). 긴 파일 이어읽기용."},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_tags",
        "description": ("태그로 리서치노트·어닝콜 전문·실적 분석을 한번에 검색. 종목 티커(KLAC, 005930), "
                        "종목명, 테마(메모리/HBM), 섹터, 기관명이 태그다. 특정 종목·주제의 최근 언급을 "
                        "훑을 때 search_notes 보다 정확하고 빠르다. 결과의 rel_path 는 read_file 로 읽을 수 있다."),
        "input_schema": {
            "type": "object",
            "properties": {
                "tag": {"type": "string", "description": "태그 (예: KLAC, 삼성전자, 메모리/HBM)"},
                "limit": {"type": "integer", "description": "최대 결과 수 (기본 20)"},
            },
            "required": ["tag"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_datasets",
        "description": "데이터셋 카탈로그(INDEX.md + 각 데이터셋 스키마·기간·쿼리 예시)를 반환.",
        "input_schema": {"type": "object", "properties": {}, "required": [],
                         "additionalProperties": False},
        "strict": True,
    },
]

_SQL_FORBIDDEN = re.compile(r"\b(ATTACH|COPY|EXPORT|INSTALL|LOAD|CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|PRAGMA|SET)\b", re.I)

def _sandboxed_connect():
    """읽기전용 + 파일시스템 샌드박스 연결.

    _SQL_FORBIDDEN 키워드 필터만으로는 read_text('/…/.env') 같은 SELECT 파일함수를
    못 막는다 (프롬프트 인젝션 경유 유출 채널). connect config로는 옵션 적용 순서
    제약에 걸리므로(실측 2026-07-11) 런타임 SET으로: allowed 지정 → 잠금.
    잠금 후에는 세션 내 재활성화 불가(DuckDB 보장 — 실측 검증).
    """
    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    con.execute(f"SET allowed_directories=['{MARKET_DIR}']")
    con.execute("SET autoinstall_known_extensions=false")
    con.execute("SET autoload_known_extensions=false")
    con.execute("SET enable_external_access=false")
    return con


def tool_run_sql(sql):
    if _SQL_FORBIDDEN.search(sql):
        return "ERROR: SELECT만 허용됩니다."
    try:
        con = _sandboxed_connect()
    except duckdb.Error as e:
        return f"ERROR: DB 연결 실패(카탈로그 갱신 중일 수 있음, 잠시 후 재시도): {e}"
    try:
        df = con.execute(sql).fetchdf()
    finally:
        con.close()
    if len(df) > 200:
        return df.head(200).to_csv(index=False) + f"\n... (총 {len(df)}행 중 200행 표시)"
    return df.to_csv(index=False) if not df.empty else "(0행)"


def tool_search_notes(pattern, max_results=40):
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"ERROR: 잘못된 정규식 — {e}"
    hits = []
    for root in SEARCH_ROOTS:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for fn in sorted(files):
                if not fn.endswith(".md"):
                    continue
                fp = os.path.join(dirpath, fn)
                try:
                    for i, line in enumerate(open(fp, encoding="utf-8", errors="replace"), 1):
                        if rx.search(line):
                            hits.append(f"{fp}:{i}: {line.strip()[:200]}")
                            if len(hits) >= max_results:
                                return "\n".join(hits)
                except OSError:
                    continue
    return "\n".join(hits) if hits else "(매칭 없음)"


def tool_read_file(path, offset=0):
    real = os.path.realpath(path)
    allowed = [os.path.realpath(DATALAKE_ROOT), os.path.realpath(WIKI_DIR)]
    if not any(real == a or real.startswith(a + os.sep) for a in allowed):
        return "ERROR: datalake/위키 외부 경로는 읽을 수 없습니다."
    if not os.path.isfile(real):
        return "ERROR: 파일 없음"
    text = open(real, encoding="utf-8", errors="replace").read()
    offset = max(0, int(offset or 0))
    chunk = text[offset:offset + 20000]
    remain = len(text) - (offset + len(chunk))
    suffix = f"\n...(truncated — 남은 {remain}자, offset={offset + len(chunk)} 로 이어읽기)" if remain > 0 else ""
    return chunk + suffix


def tool_list_datasets():
    idx = os.path.join(CATALOG_DIR, "INDEX.md")
    if not os.path.exists(idx):
        return "카탈로그 없음 — build_catalog.py를 먼저 실행하세요."
    parts = [open(idx, encoding="utf-8").read()]
    for fn in sorted(os.listdir(CATALOG_DIR)):
        if fn.endswith(".md") and fn != "INDEX.md":
            parts.append(open(os.path.join(CATALOG_DIR, fn), encoding="utf-8").read())
    return "\n\n---\n\n".join(parts)[:30000]


def execute_tool(name, args):
    try:
        if name == "run_sql":
            return tool_run_sql(args["sql"]), False
        if name == "search_notes":
            return tool_search_notes(args["pattern"], args.get("max_results") or 40), False
        if name == "read_file":
            return tool_read_file(args["path"], args.get("offset") or 0), False
        if name == "search_tags":
            return json.dumps(_tag_search(args["tag"], args.get("limit") or 20),
                              ensure_ascii=False)[:20000], False
        if name == "list_datasets":
            return tool_list_datasets(), False
        return f"ERROR: 알 수 없는 도구 {name}", True
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}", True


def _report(usage, question):
    """usage 요약을 로그에 남기고 응답용 dict 반환."""
    out = dict(usage)
    out["cost_usd"] = _cost_usd(usage)
    total_in = (usage.get("input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0))
    out["cache_hit_pct"] = (round(usage.get("cache_read_input_tokens", 0) * 100.0 / total_in, 1)
                            if total_in else 0.0)
    print("[ask][usage] in=%d cache_w=%d cache_r=%d(%.1f%%) out=%d $%.4f | %s" % (
        usage.get("input_tokens", 0), usage.get("cache_creation_input_tokens", 0),
        usage.get("cache_read_input_tokens", 0), out["cache_hit_pct"],
        usage.get("output_tokens", 0), out["cost_usd"], question[:60]), flush=True)
    return out


def _apply_cache_breakpoints(messages, keep=2):
    """대화 히스토리에 롤링 캐시 breakpoint를 keep개 유지.

    종전엔 시스템 프롬프트(1개)에만 cache_control이 있어, 매 턴 재전송되는
    대화 본문(read_file 결과 등)이 전부 정가로 재과금됐다. 직전 프리픽스를
    캐시 읽기(입력가의 0.1배)로 처리시켜 입력 비용을 크게 줄인다.
    ★assistant content는 SDK 객체라 손대지 않고 dict 블록에만 표시한다.
    ★breakpoint 상한은 요청당 4개 — system 1 + keep 2 = 3개로 여유를 남긴다.
    """
    candidates = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        last = None
        for block in content:
            if isinstance(block, dict):
                block.pop("cache_control", None)  # 옛 breakpoint 회수
                last = block
        if last is not None:
            candidates.append(last)
    for block in candidates[-keep:]:
        block["cache_control"] = {"type": "ephemeral"}


def _tally(usage, resp):
    """턴별 usage 누적 (비용 실측용)."""
    u = getattr(resp, "usage", None)
    if u is None:
        return
    for k in ("input_tokens", "output_tokens",
              "cache_creation_input_tokens", "cache_read_input_tokens"):
        usage[k] = usage.get(k, 0) + (getattr(u, k, 0) or 0)


def _cost_usd(usage):
    """Sonnet 5 도입가($2/$10 per MTok) 기준 추정 비용. 캐시 쓰기 1.25배·읽기 0.1배."""
    IN, OUT = 2.0 / 1_000_000, 10.0 / 1_000_000
    return round(
        usage.get("input_tokens", 0) * IN
        + usage.get("cache_creation_input_tokens", 0) * IN * 1.25
        + usage.get("cache_read_input_tokens", 0) * IN * 0.1
        + usage.get("output_tokens", 0) * OUT, 4)


def _is_empty_result(out):
    """search_notes / search_tags 응답이 사실상 빈 결과인지."""
    s = (out or "").strip()
    if not s or s in ("[]", "{}"):
        return True
    low = s[:200]
    return ("결과 없음" in low) or ("매칭 없음" in low) or ('"hits": []' in s) or ('"results": []' in s)


class AskRequest(BaseModel):
    question: str
    history: list = []  # [{"role": "user"|"assistant", "content": "텍스트"}]


@app.post("/ask")
def ask(req: AskRequest):
    messages = [{"role": m["role"], "content": m["content"]}
                for m in req.history[-20:] if m.get("role") in ("user", "assistant") and m.get("content")]
    messages.append({"role": "user", "content": req.question})
    steps = []

    seen_calls = {}   # 동일 (도구, 인자) 반복 차단
    empty_streak = 0  # 연속 빈 검색 결과
    usage = {}        # 턴별 토큰 누적 (비용 실측)

    for turn in range(MAX_LOOP):
        _apply_cache_breakpoints(messages)
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=messages,
        )
        _tally(usage, response)
        if response.stop_reason == "refusal":
            return JSONResponse({"answer": "요청을 처리할 수 없습니다 (안전 정책).",
                                 "steps": steps, "usage": _report(usage, req.question)})
        if response.stop_reason != "tool_use":
            answer = "".join(b.text for b in response.content if b.type == "text")
            return JSONResponse({"answer": answer, "steps": steps,
                                 "usage": _report(usage, req.question)})

        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            sig = block.name + "|" + json.dumps(block.input, ensure_ascii=False, sort_keys=True)
            if sig in seen_calls:
                out, is_err = (
                    "ERROR: 이미 동일한 호출을 했고 결과는 위에 있다. 같은 검색을 반복하지 말고 "
                    "다른 전략(태그↔정규식↔SQL)으로 바꾸거나, 지금까지 모은 근거만으로 답을 작성하라.",
                    True,
                )
            else:
                seen_calls[sig] = True
                out, is_err = execute_tool(block.name, block.input)
                if block.name in ("search_notes", "search_tags") and _is_empty_result(out):
                    empty_streak += 1
                    if empty_streak >= 2:
                        out += ("\n\n[시스템] 검색이 연속으로 비었다. 이 경로를 포기하고 전략을 바꾸거나, "
                                "코퍼스에 근거가 없음을 밝힌 뒤 보유 지식으로 [추정]을 제시하며 답을 작성하라.")
                else:
                    empty_streak = 0
            steps.append({"tool": block.name,
                          "input": json.dumps(block.input, ensure_ascii=False)[:300]})
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": out, "is_error": is_err})

        remaining = MAX_LOOP - turn - 1
        if 0 < remaining <= 3:
            results.append({"type": "text",
                            "text": "[시스템] 남은 도구 호출은 %d턴이다. 추가 조회를 멈추고 "
                                    "지금까지 모은 근거로 최종 답변을 작성하라." % remaining})
        messages.append({"role": "user", "content": results})

    # ── 한도 소진: 모은 근거를 버리지 않고 도구 없이 강제 종결
    messages.append({"role": "user", "content":
                     "[시스템] 도구 호출 한도에 도달했다. 더 이상 조회할 수 없다. "
                     "지금까지의 조회 결과만으로 최종 답변을 작성하라. 확인하지 못한 부분은 "
                     "'미확인'으로 명시하고, 일반 지식으로 보완한 부분은 [추정]으로 표시하라. "
                     "답변을 거르지 말 것."})
    try:
        _apply_cache_breakpoints(messages)
        final = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            tool_choice={"type": "none"},
            messages=messages,
        )
        _tally(usage, final)
        answer = "".join(b.text for b in final.content if b.type == "text").strip()
        if answer:
            return JSONResponse({"answer": answer, "steps": steps, "truncated": True,
                                 "usage": _report(usage, req.question)})
    except Exception as e:
        print("[ask] 강제 종결 실패: %s: %s" % (type(e).__name__, e), flush=True)

    return JSONResponse({"answer": "도구 호출 한도를 초과했고 최종 답변 생성도 실패했습니다. "
                                   "질문을 좁혀 다시 시도해 주세요.",
                         "steps": steps, "usage": _report(usage, req.question)})


# ── Earnings Library — 어닝 md 열람 (transcripts + analyses) ──────────
from fastapi.responses import HTMLResponse  # noqa: E402

LIBRARY_ROOTS = {
    "transcript": os.path.join(DATALAKE_ROOT, "transcripts"),
    "analysis": os.path.join(DATALAKE_ROOT, "analyses"),
}


def _frontmatter(path, limit=2048):
    """md 선두 frontmatter(--- ... ---)를 dict로. 없으면 {}."""
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(limit)
    except OSError:
        return {}
    if not head.startswith("---"):
        return {}
    end = head.find("\n---", 3)
    if end < 0:
        return {}
    meta = {}
    for line in head[3:end].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta


@app.get("/library/list")
def library_list():
    items = []
    for kind, root_dir in LIBRARY_ROOTS.items():
        if not os.path.isdir(root_dir):
            continue
        for base, _dirs, files in os.walk(root_dir):
            for fn in files:
                if not fn.endswith(".md"):
                    continue
                p = os.path.join(base, fn)
                meta = _frontmatter(p)
                items.append({
                    "kind": kind,
                    "rel": os.path.relpath(p, DATALAKE_ROOT).replace(os.sep, "/"),
                    "date": (meta.get("date") or fn[:10]),
                    "ticker": meta.get("ticker") or (fn.split("_")[1] if fn.count("_") >= 1 else ""),
                    "title": meta.get("title", ""),
                    "size": os.path.getsize(p),
                })
    items.sort(key=lambda x: (x["date"], x["rel"]), reverse=True)
    return JSONResponse({"items": items})


@app.get("/library/doc")
def library_doc(rel: str):
    p = os.path.realpath(os.path.join(DATALAKE_ROOT, rel))
    ok = any(p.startswith(os.path.realpath(r) + os.sep) for r in LIBRARY_ROOTS.values())
    if not ok or not p.endswith(".md") or not os.path.isfile(p):
        return JSONResponse({"error": "잘못된 경로"}, status_code=400)
    with open(p, encoding="utf-8") as f:
        content = f.read()
    return JSONResponse({"rel": rel, "content": content})


HIGHLIGHT_PATH = os.path.join(DATALAKE_ROOT, "library", "highlights.json")


@app.get("/library/highlights")
def library_highlights():
    import json as _j
    try:
        with open(HIGHLIGHT_PATH, encoding="utf-8") as f:
            return JSONResponse(_j.load(f))
    except (OSError, ValueError):
        return JSONResponse({})


class HighlightReq(BaseModel):
    rel: str
    items: list


@app.post("/library/highlights")
def library_highlights_save(req: HighlightReq):
    import json as _j
    try:
        with open(HIGHLIGHT_PATH, encoding="utf-8") as f:
            data = _j.load(f)
    except (OSError, ValueError):
        data = {}
    items = []
    for it in req.items:
        if isinstance(it, str) and it.strip():
            items.append({"s": it, "c": 1})  # 구버전(문자열) 호환
        elif isinstance(it, dict) and str(it.get("s", "")).strip():
            c = it.get("c", 1)
            items.append({"s": str(it["s"]), "c": c if c in (1, 2, 3) else 1})
    if items:
        data[req.rel] = items
    else:
        data.pop(req.rel, None)
    os.makedirs(os.path.dirname(HIGHLIGHT_PATH), exist_ok=True)
    tmp = HIGHLIGHT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        _j.dump(data, f, ensure_ascii=False)
    os.replace(tmp, HIGHLIGHT_PATH)
    return JSONResponse({"ok": True, "count": len(items)})


@app.get("/library")
def library_page():
    return HTMLResponse(_LIBRARY_HTML)


_LIBRARY_HTML = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Earnings Library</title>
<link rel="stylesheet" href="/assets/vendor/pretendard/pretendardvariable.min.css">
<style>
/*__AOE_PALETTE__*/
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--aoe-bg);color:var(--aoe-text);font-family:'Pretendard Variable',Pretendard,system-ui,sans-serif;height:100vh;display:flex;flex-direction:column;}
/* ── AoE 공통 상단 내비 — 기동 시 nav_style.NAV_CSS 로 치환 (정본, 직접 수정 금지) ── */
/*__AOE_NAV_CSS__*/
header{padding:14px 20px 10px;border-bottom:1px solid var(--aoe-border);display:flex;align-items:center;gap:14px;flex-wrap:wrap;}
header h1{font-size:22px;color:var(--aoe-amber);font-weight:700;}
.tabs{display:flex;gap:6px;}
.tab{font-size:16px;font-weight:600;padding:5px 14px;border:1.5px solid var(--aoe-input-border);border-radius:2px;background:var(--aoe-input-bg);color:#fff;cursor:pointer;}
.tab.on{background:var(--aoe-amber);border-color:var(--aoe-amber);color:var(--aoe-bg);}
.searchwrap{margin-left:auto;position:relative;display:flex;align-items:center;}
.searchwrap svg{position:absolute;left:9px;pointer-events:none;}
#q{background:var(--aoe-input-bg);border:1px solid #fff;border-radius:2px;color:var(--aoe-text);font-family:inherit;font-size:16px;padding:6px 10px 6px 30px;width:210px;}
#q:focus{outline:1px solid var(--aoe-amber);}
main{flex:1;display:flex;min-height:0;}
#list{width:320px;min-width:240px;border-right:1px solid var(--aoe-border);overflow-y:auto;}
.item{padding:9px 14px;border-bottom:1px solid var(--aoe-th-bg);cursor:pointer;}
.item:hover{background:var(--aoe-card2);}
.item.on{background:var(--aoe-hl1-bg);}
.item .t{font-size:20px;font-weight:600;color:#c9ced4;display:flex;gap:8px;align-items:baseline;}
.item.on .t{color:var(--aoe-hl1-fg);}
.item .t .tk{color:var(--aoe-amber);}
.item .m{font-size:16px;color:var(--aoe-muted);margin-top:2px;}
.badge{font-size:15px;font-weight:700;border-radius:2px;padding:1px 6px;vertical-align:1px;}
.badge.transcript{background:var(--aoe-hl2-bg);color:var(--aoe-hl2-fg);}
.badge.analysis{background:var(--aoe-hl3-bg);color:var(--aoe-hl3-fg);}
#doc{flex:1;overflow-y:auto;padding:26px max(34px,calc((100% - 1300px)/2)) 60px;line-height:1.75;caret-color:var(--aoe-amber);color:#fff;user-select:text;}
#doc:focus{outline:none;}
#doc *{-webkit-user-drag:none;}
#doc .empty{color:var(--aoe-muted);font-size:20px;margin-top:40px;text-align:center;}
#doc h1{font-size:32px;color:var(--aoe-amber);margin:18px 0 10px;}
#doc h2{font-size:26px;color:var(--aoe-amber);margin:22px 0 8px;border-bottom:1px solid var(--aoe-border);padding-bottom:4px;}
#doc h3{font-size:24px;color:var(--aoe-amber);margin:16px 0 6px;}
#doc p{font-size:20px;margin:8px 0;}
#doc ul,#doc ol{margin:8px 0 8px 22px;font-size:20px;}
#doc li{margin:3px 0;}
#doc table{border-collapse:collapse;margin:12px 0;font-size:19px;}
#doc th{background:var(--aoe-th-bg);color:var(--aoe-amber);font-size:15px;padding:6px 12px;border:1px solid var(--aoe-border);}
#doc td{padding:6px 12px;border:1px solid var(--aoe-border);color:#fff;text-align:center;}
#doc blockquote{border-left:3px solid var(--aoe-amber);padding:4px 14px;color:#fff;background:var(--aoe-card);margin:10px 0;}
#doc code{background:var(--aoe-th-bg);border-radius:2px;padding:1px 5px;font-size:18px;}
#doc hr{border:none;border-top:1px solid var(--aoe-border);margin:16px 0;}
#doc .fm{background:var(--aoe-card);border:1px solid var(--aoe-border);border-radius:2px;padding:10px 14px;font-size:16px;color:var(--aoe-muted);margin-top:26px;}
#doc .fm b{color:var(--aoe-amber-bright);font-weight:600;}
#doc mark.hl{border-radius:2px;}
#doc mark.hl.c1{background:var(--aoe-hl1-bg);color:var(--aoe-hl1-fg);}
#doc mark.hl.c2{background:var(--aoe-hl2-bg);color:var(--aoe-hl2-fg);}
#doc mark.hl.c3{background:var(--aoe-hl3-bg);color:var(--aoe-hl3-fg);}
#hlPop{position:fixed;display:none;z-index:10;gap:8px;padding:7px 10px;background:var(--aoe-input-bg);border:1px solid var(--aoe-input-border);border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,.5);}
#hlPop .dot{width:20px;height:20px;border-radius:50%;border:1.5px solid var(--aoe-bg);cursor:pointer;padding:0;}
#hlPop .d1{background:var(--aoe-hl1-fg);}#hlPop .d2{background:var(--aoe-hl2-fg);}#hlPop .d3{background:var(--aoe-hl3-fg);}
@media(max-width:760px){#list{width:44%;}#doc{padding:16px;}}
</style></head><body>
<!--__AOE_NAV__-->
<header>
  <h1>Earnings Library</h1>
  <div class="tabs">
    <button class="tab on" data-k="all">전체</button>
    <button class="tab" data-k="analysis">분석</button>
    <button class="tab" data-k="transcript">콜 전문</button>
  </div>
  <span class="searchwrap">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.4" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="7"/><line x1="16" y1="16" x2="21.5" y2="21.5"/></svg>
    <input id="q">
  </span>
</header>
<main>
  <div id="list"></div>
  <div id="doc" contenteditable="true" spellcheck="false"><div class="empty">좌측에서 문서를 선택하세요</div></div>
</main>
<div id="hlPop"><button class="dot d1" data-c="1" title="바이올렛"></button><button class="dot d2" data-c="2" title="시안"></button><button class="dot d3" data-c="3" title="에메랄드"></button></div>
<script>
var ALL=[], KIND='all', Q='', HL={}, CUR=null;
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function inline(s){
  s=esc(s);
  s=s.replace(/\\*\\*([^*]+)\\*\\*/g,'<b>$1</b>').replace(/`([^`]+)`/g,'<code>$1</code>');
  return s;
}
function mdRender(md){
  // frontmatter 분리
  var fm='';
  if(md.slice(0,3)==='---'){var e=md.indexOf('\\n---',3);if(e>0){
    var meta=md.slice(3,e).trim().split('\\n').map(function(l){var i=l.indexOf(':');
      return i>0?'<b>'+esc(l.slice(0,i).trim())+'</b> '+esc(l.slice(i+1).trim()):esc(l);}).join(' · ');
    fm='<div class="fm">'+meta+'</div>'; md=md.slice(e+4);}}
  var lines=md.split('\\n'), out=[], i=0, listOpen=null;
  function closeList(){if(listOpen){out.push('</'+listOpen+'>');listOpen=null;}}
  while(i<lines.length){
    var l=lines[i];
    if(/^\\s*\\|/.test(l)){ // 표
      closeList(); var rows=[];
      while(i<lines.length && /^\\s*\\|/.test(lines[i])){rows.push(lines[i]);i++;}
      var html='<table>';
      rows.forEach(function(r,ri){
        if(/^\\s*\\|[\\s:|-]+\\|\\s*$/.test(r)) return; // 구분선
        var cells=r.trim().replace(/^\\||\\|$/g,'').split('|');
        var tag=(ri===0)?'th':'td';
        // 가운데 정렬 기본, 긴 서술형 셀(>25자)만 왼쪽
        html+='<tr>'+cells.map(function(c){var t=c.trim();var st=t.length>25?' style="text-align:left"':'';
          return '<'+tag+st+'>'+inline(t)+'</'+tag+'>';}).join('')+'</tr>';
      });
      out.push(html+'</table>'); continue;
    }
    if(/^###\\s/.test(l)){closeList();out.push('<h3>'+inline(l.slice(4))+'</h3>');}
    else if(/^##\\s/.test(l)){closeList();out.push('<h2>'+inline(l.slice(3))+'</h2>');}
    else if(/^#\\s/.test(l)){closeList();out.push('<h1>'+inline(l.slice(2))+'</h1>');}
    else if(/^\\s*[-*]\\s/.test(l)){if(listOpen!=='ul'){closeList();out.push('<ul>');listOpen='ul';}out.push('<li>'+inline(l.replace(/^\\s*[-*]\\s/,''))+'</li>');}
    else if(/^\\s*\\d+\\.\\s/.test(l)){if(listOpen!=='ol'){closeList();out.push('<ol>');listOpen='ol';}out.push('<li>'+inline(l.replace(/^\\s*\\d+\\.\\s/,''))+'</li>');}
    else if(/^>\\s?/.test(l)){closeList();out.push('<blockquote>'+inline(l.replace(/^>\\s?/,''))+'</blockquote>');}
    else if(/^(---|\\*\\*\\*)\\s*$/.test(l)){closeList();out.push('<hr>');}
    else if(l.trim()===''){closeList();}
    else{closeList();out.push('<p>'+inline(l)+'</p>');}
    i++;
  }
  closeList();
  out.push(fm);  // 메타 정보는 본문 맨 아래 (2026-07-22 사용자 요청)
  return out.join('');
}
// ── 하이라이트 (선택 → 저장, 클릭 → 해제; library/highlights.json 영속) ──
function textMap(root){var w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),ns=[],tx='',n;
  while((n=w.nextNode())){ns.push({node:n,start:tx.length});tx+=n.nodeValue;}return {nodes:ns,text:tx};}
function locate(map,idx){for(var i=map.nodes.length-1;i>=0;i--){if(map.nodes[i].start<=idx)return {node:map.nodes[i].node,offset:idx-map.nodes[i].start};}return null;}
// 끝 경계는 이전 노드의 '끝'을 선택 — 다음 블록 시작(offset 0)으로 넘어가면
// range가 문단 경계를 넘어 추출 시 빈 줄이 생긴다 (2026-07-22 실측 버그)
function locateEnd(map,idx){for(var i=map.nodes.length-1;i>=0;i--){var n=map.nodes[i];
  if(n.start<idx||(i===0&&n.start<=idx))return {node:n.node,offset:idx-n.start};}return null;}
function ns(x){return typeof x==='string'?{s:x,c:1}:x;}
function markString(s,c){var doc=document.getElementById('doc'),map=textMap(doc),idx=map.text.indexOf(s);
  if(idx<0)return false;
  var st=locate(map,idx),en=locateEnd(map,idx+s.length);if(!st||!en)return false;
  var r=document.createRange();
  try{r.setStart(st.node,st.offset);r.setEnd(en.node,en.offset);
    var m=document.createElement('mark');m.className='hl c'+(c||1);
    m.appendChild(r.extractContents());r.insertNode(m);}catch(e){return null;}
  return m;}
function applyHL(){(HL[CUR]||[]).forEach(function(x){var it=ns(x);markString(it.s,it.c);});bindMarks();}
function saveHL(){fetch('library/highlights',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({rel:CUR,items:HL[CUR]||[]})});}
var UNDO=[],LASTC=1;  // 하이라이트 자체 undo 스택 (Ctrl+Z) + 마지막 사용 색
function removeMark(m,skipUndo){var t=m.textContent;
  var hit=(HL[CUR]||[]).map(ns).filter(function(x){return x.s===t;})[0];
  HL[CUR]=(HL[CUR]||[]).filter(function(x){return ns(x).s!==t;});saveHL();
  if(!skipUndo)UNDO.push({t:'remove',s:t,c:hit?hit.c:1,rel:CUR});
  var p=m.parentNode;while(m.firstChild)p.insertBefore(m.firstChild,m);p.removeChild(m);p.normalize();}
function addHL(s,c,skipUndo){c=c||1;LASTC=c;
  // 여러 줄 선택은 줄 단위 분리 (본문 텍스트맵엔 블록 간 개행이 없어 통짜 매칭 불가)
  var segs=String(s).split(/\\n+/).map(function(x){return x.trim();}).filter(function(x){return x.length>=2;});
  if(!segs.length)return null;
  var lastM=null;
  segs.forEach(function(seg){
    HL[CUR]=(HL[CUR]||[]).concat([{s:seg,c:c}]);
    if(!skipUndo)UNDO.push({t:'add',s:seg,c:c,rel:CUR});
    var m=markString(seg,c);if(m)lastM=m;});
  saveHL();bindMarks();return lastM;}
function bindMarks(){Array.prototype.forEach.call(document.querySelectorAll('#doc mark.hl'),function(m){
  m.title='Ctrl+Shift+H로 해제';});}
// ── 읽기 전용 contenteditable (노션식 캐럿 이동·Shift+화살표 선택, 수정은 차단) ──
var docEl=document.getElementById('doc');
['beforeinput','paste','cut','drop','dragstart'].forEach(function(ev){
  docEl.addEventListener(ev,function(e){e.preventDefault();});});
function markAt(node){while(node&&node!==docEl){
  if(node.nodeType===1&&node.classList&&node.classList.contains('hl'))return node;
  node=node.parentNode;}return null;}
// Ctrl+Shift+H = 하이라이트 토글 (선택 → 적용, 하이라이트 안/캐럿 → 해제)
document.addEventListener('keydown',function(e){
  if(!(e.ctrlKey&&e.shiftKey&&(e.key==='H'||e.key==='h')))return;
  e.preventDefault();
  if(!CUR)return;
  var sel=window.getSelection();
  if(!sel||!sel.rangeCount)return;
  var m=markAt(sel.anchorNode)||markAt(sel.focusNode);
  function caretAfter(node){try{var r=document.createRange();
    if(node&&node.nodeType===3){r.setStart(node,node.nodeValue.length);}else if(node){r.setStartAfter(node);}else{return;}
    r.collapse(true);sel.removeAllRanges();sel.addRange(r);}catch(_){}}
  if(m){var prev=m.previousSibling,par=m.parentNode;removeMark(m);
    caretAfter(prev&&prev.nodeType===3?prev:par.firstChild);return;}
  var s=sel.toString().trim();
  if(s.length<2||s.length>2000)return;
  var nm=addHL(s,LASTC);
  if(nm){caretAfter(nm);}else{sel.removeAllRanges();}
  hlPop.style.display='none';});
// Ctrl+Z = 마지막 하이라이트 동작 되돌리기 (브라우저 기본 undo는 차단 — contenteditable DOM 오염 방지)
document.addEventListener('keydown',function(e){
  if(!(e.ctrlKey&&!e.shiftKey&&(e.key==='z'||e.key==='Z')))return;
  var inDoc=docEl.contains(document.activeElement)||docEl===document.activeElement;
  var sel=window.getSelection();
  if(sel&&sel.anchorNode&&docEl.contains(sel.anchorNode))inDoc=true;
  if(inDoc)e.preventDefault();
  var a=UNDO.pop();
  if(!a||a.rel!==CUR){if(a)UNDO.push(a);return;}
  if(a.t==='add'){
    var ms=document.querySelectorAll('#doc mark.hl');
    for(var i=ms.length-1;i>=0;i--){if(ms[i].textContent===a.s){removeMark(ms[i],true);break;}}
  }else{addHL(a.s,a.c,true);}});
var hlPop=document.getElementById('hlPop');
document.getElementById('doc').addEventListener('mouseup',function(){
  setTimeout(function(){var sel=window.getSelection(),s=sel?sel.toString().trim():'';
    if(!CUR||s.length<2||s.length>2000){hlPop.style.display='none';return;}
    var rect=sel.getRangeAt(0).getBoundingClientRect();
    hlPop.style.left=Math.max(8,rect.left+rect.width/2-45)+'px';
    hlPop.style.top=Math.max(8,rect.top-44)+'px';
    hlPop.style.display='flex';hlPop.dataset.sel=s;},10);});
Array.prototype.forEach.call(hlPop.querySelectorAll('.dot'),function(d){
  d.addEventListener('mousedown',function(ev){ev.preventDefault();ev.stopPropagation();
    var s=hlPop.dataset.sel;if(!s||!CUR)return;
    addHL(s,parseInt(d.dataset.c,10));
    window.getSelection().removeAllRanges();hlPop.style.display='none';});});
document.addEventListener('mousedown',function(e){if(!hlPop.contains(e.target))hlPop.style.display='none';});
function draw(){
  var q=Q.toLowerCase();
  var items=ALL.filter(function(x){
    if(KIND!=='all'&&x.kind!==KIND)return false;
    if(!q)return true;
    return (x.ticker+' '+x.date+' '+x.rel+' '+x.title).toLowerCase().indexOf(q)>=0;
  });
  document.getElementById('list').innerHTML=items.map(function(x,i){
    return '<div class="item" data-rel="'+esc(x.rel)+'">'
      +'<div class="t"><span class="tk">'+esc(x.ticker||'—')+'</span><span class="badge '+x.kind+'">'+(x.kind==='transcript'?'전문':'분석')+'</span></div>'
      +'<div class="m"><span style="color:#fff;">'+esc(x.date)+'</span></div></div>';
  }).join('');
  Array.prototype.forEach.call(document.querySelectorAll('.item'),function(el){
    el.addEventListener('click',function(){
      Array.prototype.forEach.call(document.querySelectorAll('.item.on'),function(o){o.classList.remove('on');});
      el.classList.add('on');
      fetch('library/doc?rel='+encodeURIComponent(el.dataset.rel)).then(function(r){return r.json();}).then(function(j){
        CUR=el.dataset.rel;
        document.getElementById('doc').innerHTML=j.error?('<div class="empty">'+esc(j.error)+'</div>'):mdRender(j.content);
        document.getElementById('doc').scrollTop=0;
        if(!j.error)applyHL();
      });
    });
  });
}
Array.prototype.forEach.call(document.querySelectorAll('.tab'),function(b){
  b.addEventListener('click',function(){
    Array.prototype.forEach.call(document.querySelectorAll('.tab'),function(t){t.classList.remove('on');});
    b.classList.add('on'); KIND=b.dataset.k; draw();
  });
});
document.getElementById('q').addEventListener('input',function(e){Q=e.target.value;draw();});
fetch('library/list').then(function(r){return r.json();}).then(function(j){ALL=j.items;draw();});
fetch('library/highlights').then(function(r){return r.json();}).then(function(j){HL=j||{};});
</script></body></html>"""

# 네비 정본 치환 (기동 시 1회) — 토큰 미존재 시 기동 실패로 곧장 드러난다
assert '/*__AOE_NAV_CSS__*/' in _LIBRARY_HTML and '<!--__AOE_NAV__-->' in _LIBRARY_HTML
assert '/*__AOE_PALETTE__*/' in _LIBRARY_HTML
_LIBRARY_HTML = (_LIBRARY_HTML
                 .replace('/*__AOE_PALETTE__*/', nav_style.PALETTE_CSS_VARS)
                 .replace('/*__AOE_NAV_CSS__*/', nav_style.NAV_CSS)
                 .replace('<!--__AOE_NAV__-->', nav_style.nav_html('earnings')))


def _load_wiki_index():
    """static/index.html 을 읽어 네비 마커 블록을 정본으로 치환 후 메모리 캐시 (기동 시 1회).

    마커 미발견 시 원본을 그대로 서빙 (경고 로그) — 기동 실패로 Wiki 를 죽이지 않는다.
    """
    raw = open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8").read()
    out, ok = nav_style.materialize(raw, active="wiki")
    if not ok:
        sys.stderr.write("[webui] WARN: static/index.html 네비 마커 미발견 — 원본 서빙\n")
        return raw
    return out


_WIKI_INDEX_HTML = _load_wiki_index()


# ── 대화 기록 (2026-07-29) ────────────────────────────────────────────────
# 새로고침·기기 변경에도 남도록 서버에 보관. 단일 uvicorn 프로세스라 sqlite 로 충분.
CHAT_DB_PATH = os.path.join(DATALAKE_ROOT, "webui_chats.sqlite")
CHAT_MAX_MESSAGES = 400
_CHAT_ID_RE = re.compile(r"[0-9a-zA-Z_-]{4,64}\Z")


def _chat_db():
    con = sqlite3.connect(CHAT_DB_PATH, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE IF NOT EXISTS chats ("
                "id TEXT PRIMARY KEY, title TEXT NOT NULL, "
                "updated_at TEXT NOT NULL, messages TEXT NOT NULL)")
    return con


@app.get("/chats")
def chats_list():
    con = _chat_db()
    try:
        rows = con.execute("SELECT id, title, updated_at FROM chats "
                           "ORDER BY updated_at DESC LIMIT 300").fetchall()
    finally:
        con.close()
    return JSONResponse([{"id": r[0], "title": r[1], "updated_at": r[2]} for r in rows])


@app.get("/chats/{cid}")
def chat_get(cid: str):
    con = _chat_db()
    try:
        row = con.execute("SELECT id, title, updated_at, messages FROM chats WHERE id=?",
                          (cid,)).fetchone()
    finally:
        con.close()
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)
    try:
        msgs = json.loads(row[3])
    except ValueError:
        msgs = []
    return JSONResponse({"id": row[0], "title": row[1], "updated_at": row[2], "messages": msgs})


class ChatSaveRequest(BaseModel):
    id: str = ""
    title: str = ""
    messages: list = []


@app.post("/chats")
def chat_save(req: ChatSaveRequest):
    msgs = [{"role": m.get("role"), "content": str(m.get("content") or ""),
             "steps": m.get("steps") or []}
            for m in req.messages
            if isinstance(m, dict) and m.get("role") in ("user", "assistant")
            and str(m.get("content") or "").strip()][-CHAT_MAX_MESSAGES:]
    if not msgs:
        return JSONResponse({"ok": False, "error": "empty"}, status_code=400)
    cid = (req.id or "").strip() or uuid.uuid4().hex[:12]
    if not _CHAT_ID_RE.match(cid):
        return JSONResponse({"ok": False, "error": "bad id"}, status_code=400)
    title = ((req.title or "").strip() or msgs[0]["content"].strip().split("\n")[0])[:60] or "새 대화"
    now = time.strftime("%Y-%m-%d %H:%M")
    con = _chat_db()
    try:
        con.execute("INSERT INTO chats (id, title, updated_at, messages) VALUES (?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET title=excluded.title, "
                    "updated_at=excluded.updated_at, messages=excluded.messages",
                    (cid, title, now, json.dumps(msgs, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()
    return JSONResponse({"ok": True, "id": cid, "title": title, "updated_at": now})


@app.delete("/chats/{cid}")
def chat_delete(cid: str):
    con = _chat_db()
    try:
        con.execute("DELETE FROM chats WHERE id=?", (cid,))
        con.commit()
    finally:
        con.close()
    return JSONResponse({"ok": True})


# ── 태그 검색 (2026-07-29) ────────────────────────────────────────────────
# build_tag_index.py 가 만든 조회 전용 인덱스. LLM 을 부르지 않으므로 즉시·무료다.
TAG_INDEX_PATH = os.path.join(DATALAKE_ROOT, "tag_index.sqlite")
TAG_CORPUS_ROOTS = ("research_notes/", "transcripts/", "analyses/", "reports/", "notion_study/")


def _tag_conn():
    if not os.path.exists(TAG_INDEX_PATH):
        return None
    con = sqlite3.connect("file:%s?mode=ro" % TAG_INDEX_PATH, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _tag_norm(q):
    return re.sub(r"\s+", "", (q or "").strip().lstrip("#")).lower()


def _resolve_tags(con, q, limit=12):
    """질의 → 실제 태그 키 목록. 정확히 일치하면 그것만, 아니면 부분 일치."""
    key = _tag_norm(q)
    if not key:
        return []
    row = con.execute("SELECT tag FROM labels WHERE tag=?", (key,)).fetchone()
    if row:
        return [row["tag"]]
    like = "%" + key + "%"
    return [r["tag"] for r in con.execute(
        "SELECT tag FROM labels WHERE tag LIKE ? ORDER BY freq DESC LIMIT ?", (like, limit))]


def _tag_search(q, limit=20):
    con = _tag_conn()
    if con is None:
        return {"error": "태그 인덱스가 아직 생성되지 않았습니다", "matched": [], "results": []}
    try:
        keys = _resolve_tags(con, q)
        if not keys:
            return {"matched": [], "results": [], "total": 0}
        ph = ",".join("?" * len(keys))
        matched = [dict(r) for r in con.execute(
            "SELECT tag, label, kind, freq FROM labels WHERE tag IN (%s)"
            " ORDER BY freq DESC" % ph, keys)]
        total = con.execute(
            "SELECT count(*) FROM (SELECT 1 FROM hits WHERE tag IN (%s)"
            " GROUP BY rel_path, anchor)" % ph, keys).fetchone()[0]
        rows = con.execute(
            "SELECT corpus, doc_date, rel_path, anchor, title, snippet FROM hits"
            " WHERE tag IN (%s) GROUP BY rel_path, anchor"
            " ORDER BY doc_date DESC, rel_path LIMIT ?" % ph,
            keys + [max(1, min(int(limit), 100))]).fetchall()
        return {"matched": matched, "total": total, "results": [dict(r) for r in rows]}
    finally:
        con.close()


@app.get("/tags/suggest")
def tags_suggest(q: str = "", limit: int = 10):
    con = _tag_conn()
    if con is None:
        return JSONResponse([])
    try:
        key = _tag_norm(q)
        like = "%" + key + "%"
        rows = con.execute(
            "SELECT tag, label, kind, freq FROM labels WHERE tag LIKE ?"
            " ORDER BY (tag = ?) DESC, freq DESC LIMIT ?",
            (like, key, max(1, min(int(limit), 30)))).fetchall()
        return JSONResponse([dict(r) for r in rows])
    finally:
        con.close()


@app.get("/tags/search")
def tags_search(q: str = "", limit: int = 20):
    return JSONResponse(_tag_search(q, limit))


@app.get("/tags/doc")
def tags_doc(rel: str, anchor: str = ""):
    """검색 결과 카드의 본문 펼치기 — 태그 코퍼스 내부로만 제한 (research_notes/transcripts/analyses/reports)."""
    rel = (rel or "").replace("\\", "/")
    if ".." in rel or not rel.startswith(TAG_CORPUS_ROOTS):
        return JSONResponse({"error": "허용되지 않은 경로"}, status_code=400)
    path = os.path.realpath(os.path.join(DATALAKE_ROOT, rel))
    if not path.startswith(os.path.realpath(DATALAKE_ROOT) + os.sep) or not os.path.exists(path):
        return JSONResponse({"error": "파일 없음"}, status_code=404)
    raw = open(path, encoding="utf-8").read()
    if anchor.startswith("rn-id"):
        mid = anchor.split(":", 1)[-1].strip()
        marker = "<!-- rn-id: %s -->" % mid
        i = raw.find(marker)
        if i < 0:
            return JSONResponse({"text": raw[:8000]})
        j = raw.find("<!-- rn-id:", i + len(marker))
        return JSONResponse({"text": raw[i + len(marker):(j if j > 0 else len(raw))][:8000]})
    if anchor.startswith("chunk"):
        try:
            no = int(anchor.split()[-1])
        except ValueError:
            no = 0
        sys.path.insert(0, os.path.join(REPO, "datalake", "tagging"))
        import tag_docs  # noqa: PLC0415
        _fm, body = tag_docs.parse_md(raw)
        chunks = tag_docs.split_chunks(body)
        return JSONResponse({"text": chunks[no] if no < len(chunks) else raw[:8000]})
    return JSONResponse({"text": raw[:8000]})


@app.get("/")
def root():
    return HTMLResponse(_WIKI_INDEX_HTML)


# ══════════════════════════════════════════════════════════════════
# headless 백엔드 테스트 경로 (2026-08-05) — nav 미배선, A/B 비교 전용.
# 기존 /ask(API 경로)는 손대지 않는다. 승인 후 라이브 전환 예정.
# ══════════════════════════════════════════════════════════════════
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class HeadlessAskRequest(BaseModel):
    question: str
    history: list = []
    chat_id: str = ""
    request_id: str = ""


@app.post("/test/headless/ask")
def test_headless_ask(req: HeadlessAskRequest):
    """비동기 제출 — 즉시 job_id 반환(202). 결과는 폴링으로 받는다."""
    import wiki_jobs
    if not (req.question or "").strip():
        return JSONResponse({"error": "질문이 비어 있습니다"}, status_code=400)
    hist = [{"role": m["role"], "content": m["content"]}
            for m in (req.history or [])[-6:]
            if m.get("role") in ("user", "assistant") and m.get("content")]
    job = wiki_jobs.submit(req.question.strip(), history=hist,
                           chat_id=req.chat_id or None,
                           request_id=req.request_id or None)
    return JSONResponse({"job_id": job["id"], "status": job["status"],
                         "queue_depth": wiki_jobs.queue_depth()}, status_code=202)


@app.get("/test/headless/jobs/{job_id}")
def test_headless_job(job_id: str):
    import wiki_jobs
    job = wiki_jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "없는 잡"}, status_code=404)
    elapsed = None
    if job.get("started_at"):
        elapsed = round((job.get("finished_at") or time.time()) - job["started_at"], 1)
    return JSONResponse({
        "job_id": job["id"], "status": job["status"],
        "answer": job.get("answer") or "", "steps": job.get("steps") or [],
        "error": job.get("error"), "elapsed_sec": elapsed,
        "meta": job.get("meta") or {},
    })


_HEADLESS_UI = """<!doctype html><meta charset="utf-8">
<title>위키 headless A/B 테스트</title>
<style>
 body{background:#12100e;color:#e8e3d9;font:15px/1.6 -apple-system,'Pretendard',sans-serif;
      max-width:900px;margin:0 auto;padding:24px}
 h1{font-size:17px;color:#e0a960;font-weight:600}
 #q{width:100%;padding:10px;background:#1c1916;color:#e8e3d9;border:1px solid #3a342c;
    border-radius:6px;font-size:15px}
 button{margin-top:8px;padding:8px 18px;background:#e0a960;color:#12100e;border:0;
        border-radius:6px;font-weight:600;cursor:pointer}
 .meta{font-size:12px;color:#8d8578;margin:10px 0}
 .steps{font-size:12px;color:#8d8578;margin-top:8px}
 .ans{white-space:pre-wrap;background:#1c1916;border:1px solid #3a342c;border-radius:8px;
      padding:16px;margin-top:12px}
 .err{border-color:#a4553a;color:#e08b6f}
</style>
<h1>위키 headless 백엔드 — A/B 테스트 (nav 미배선)</h1>
<div class="meta">구독 쿼터로 실행됩니다. 호출당 API 과금 0원. 기존 /wiki 는 그대로입니다.</div>
<input id="q" placeholder="질문을 입력하고 Enter">
<button onclick="go()">제출</button>
<div id="out"></div>
<script>
const out = document.getElementById('out'), q = document.getElementById('q');
q.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
async function go() {
  const question = q.value.trim(); if (!question) return;
  out.innerHTML = '<div class="meta">제출 중...</div>';
  const r = await fetch('ask', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({question, request_id: 'ui-' + Date.now()})});
  const j = await r.json();
  if (!j.job_id) { out.innerHTML = '<div class="ans err">'+JSON.stringify(j)+'</div>'; return; }
  const t0 = Date.now();
  const timer = setInterval(async () => {
    const s = await (await fetch('jobs/' + j.job_id)).json();
    const secs = ((Date.now() - t0)/1000).toFixed(0);
    if (s.status === 'queued' || s.status === 'running') {
      out.innerHTML = '<div class="meta">' + s.status + ' · ' + secs + '초 경과' +
        (s.steps && s.steps.length ? '<div class="steps">🔧 ' +
          s.steps.map(x=>x.tool).join(' · ') + '</div>' : '') + '</div>';
      return;
    }
    clearInterval(timer);
    const ok = s.status === 'succeeded';
    out.innerHTML = '<div class="meta">' + s.status + ' · ' + (s.elapsed_sec ?? secs) +
      '초 · ' + (s.meta.num_turns ?? '?') + '턴</div>' +
      '<div class="ans' + (ok ? '' : ' err') + '">' +
      (ok ? s.answer : ('실패: ' + (s.error||''))) + '</div>' +
      (s.steps && s.steps.length ? '<div class="steps">🔧 ' +
        s.steps.map(x=>x.tool).join(' · ') + '</div>' : '') +
      (ok ? '' : '<button onclick="go()">재시도</button>');
  }, 2000);
}
</script>"""


@app.get("/test/headless/ui")
def test_headless_ui():
    from fastapi.responses import HTMLResponse as _HR
    return _HR(_HEADLESS_UI)


if __name__ == "__main__":
    import uvicorn
    # 기본=로컬 전용. 테일넷 공개는 DATALAKE_WEBUI_HOST에 테일스케일 IP 지정
    # (테일넷 밖에서는 접근 불가 — tailscale serve 미사용 시의 대안)
    uvicorn.run(app, host=os.getenv("DATALAKE_WEBUI_HOST", "127.0.0.1"),
                port=int(os.getenv("DATALAKE_WEBUI_PORT", "8787")))
