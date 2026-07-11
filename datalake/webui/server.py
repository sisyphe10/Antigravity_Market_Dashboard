# -*- coding: utf-8 -*-
"""Datalake 문답 웹 UI — FastAPI + Claude API 에이전틱 루프.

질문 → Claude(claude-opus-4-8, adaptive thinking)가 도구 4종으로 데이터를 직접 조회해 답변:
  run_sql       : market.duckdb 읽기전용 SQL
  search_notes  : research_notes/catalog/architecture-wiki md 코퍼스 정규식 검색
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
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dl_common import CATALOG_DIR, DATALAKE_ROOT, DUCKDB_PATH, REPO  # noqa: E402

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(REPO, ".env"))

import anthropic  # noqa: E402
import duckdb  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

MODEL = "claude-opus-4-8"
MAX_LOOP = 12
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
WIKI_DIR = os.path.join(REPO, "architecture", "wiki")
SEARCH_ROOTS = [
    os.path.join(DATALAKE_ROOT, "research_notes"),
    CATALOG_DIR,
    WIKI_DIR,
]

app = FastAPI()
client = anthropic.Anthropic()

SYSTEM = """너는 사용자의 개인 데이터레이크 사서(librarian)다. 아래 자산에서 근거를 찾아 한국어 존댓말로 답한다.

## 데이터 자산
1. market.duckdb 뷰 (run_sql): 카탈로그는 list_datasets로 확인. 국내 전 상장종목 일봉(수정주가)·시총·밸류에이션·외국인 보유·지수·ETF·투자자별 매매대금·해외 유니버스 일봉.
2. 리서치 노트 원문 (search_notes → read_file): research_notes/YYYY/YYYY-MM-DD.md — 텔레그램으로 수집한 증권사 리포트 요지·기사·메모 원문.
3. 시스템 위키 (search_notes): architecture wiki — 이 대시보드 시스템의 봇·잡·페이지 구조.

## 규칙
- 수치 질문은 반드시 run_sql로 실제 조회 후 답한다. 추측 금지, 조회 실패 시 실패했다고 밝힌다.
- 먼저 list_datasets로 스키마를 확인하고 SQL을 작성하면 오류가 적다.
- 리서치/뉴스 맥락 질문은 search_notes로 원문을 찾고, 날짜·출처를 함께 인용한다.
- % 수치는 소수점 첫째 자리, 금액은 억원 단위(조 초과 시 NN조 N,NNN억원).
- 답변은 결론 먼저, 근거(쿼리 결과·노트 인용)는 뒤에. 표가 적합하면 markdown 표 사용.
- 데이터에 없는 내용은 없다고 답한다."""

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
        "description": "md 코퍼스(리서치 노트 원문·카탈로그·시스템 위키)를 정규식으로 검색. 파일경로:줄번호와 매칭 줄을 반환.",
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
        "description": "코퍼스 파일 전체 읽기. search_notes가 반환한 경로를 그대로 전달.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "search_notes 결과의 파일 경로"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        "strict": True,
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


def tool_run_sql(sql):
    if _SQL_FORBIDDEN.search(sql):
        return "ERROR: SELECT만 허용됩니다."
    con = duckdb.connect(DUCKDB_PATH, read_only=True)
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


def tool_read_file(path):
    real = os.path.realpath(path)
    allowed = [os.path.realpath(DATALAKE_ROOT), os.path.realpath(WIKI_DIR)]
    if not any(real == a or real.startswith(a + os.sep) for a in allowed):
        return "ERROR: datalake/위키 외부 경로는 읽을 수 없습니다."
    if not os.path.isfile(real):
        return "ERROR: 파일 없음"
    text = open(real, encoding="utf-8", errors="replace").read()
    return text[:20000] + ("\n...(truncated)" if len(text) > 20000 else "")


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
            return tool_read_file(args["path"]), False
        if name == "list_datasets":
            return tool_list_datasets(), False
        return f"ERROR: 알 수 없는 도구 {name}", True
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}", True


class AskRequest(BaseModel):
    question: str
    history: list = []  # [{"role": "user"|"assistant", "content": "텍스트"}]


@app.post("/ask")
def ask(req: AskRequest):
    messages = [{"role": m["role"], "content": m["content"]}
                for m in req.history[-20:] if m.get("role") in ("user", "assistant") and m.get("content")]
    messages.append({"role": "user", "content": req.question})
    steps = []

    for _ in range(MAX_LOOP):
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=messages,
        )
        if response.stop_reason == "refusal":
            return JSONResponse({"answer": "요청을 처리할 수 없습니다 (안전 정책).", "steps": steps})
        if response.stop_reason != "tool_use":
            answer = "".join(b.text for b in response.content if b.type == "text")
            return JSONResponse({"answer": answer, "steps": steps})

        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "tool_use":
                out, is_err = execute_tool(block.name, block.input)
                steps.append({"tool": block.name,
                              "input": json.dumps(block.input, ensure_ascii=False)[:300]})
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": out, "is_error": is_err})
        messages.append({"role": "user", "content": results})

    return JSONResponse({"answer": "도구 호출 한도를 초과했습니다. 질문을 좁혀 주세요.", "steps": steps})


@app.get("/")
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("DATALAKE_WEBUI_PORT", "8787")))
