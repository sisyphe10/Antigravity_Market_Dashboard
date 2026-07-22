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
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dl_common import CATALOG_DIR, DATALAKE_ROOT, DUCKDB_PATH, MARKET_DIR, REPO  # noqa: E402

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
    os.path.join(DATALAKE_ROOT, "transcripts"),  # 어닝콜 한국어 번역 전문 (earnings_bot)
    os.path.join(DATALAKE_ROOT, "analyses"),     # 실적 1-page 분석 시트 md (2026-07-22 Notion→md 이전)
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
4. 어닝콜 번역 전문 (search_notes → read_file): transcripts/YYYY/YYYY-MM-DD_티커_*.md — 미국 유니버스 종목 실적 컨퍼런스콜 한국어 번역 전문. 파일이 길면 read_file의 offset으로 이어서 읽는다.

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
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{background:#0a0a0a;color:#d9dde2;font-family:'Pretendard Variable',Pretendard,system-ui,sans-serif;height:100vh;display:flex;flex-direction:column;}
header{padding:14px 20px 10px;border-bottom:1px solid #27282b;display:flex;align-items:center;gap:14px;flex-wrap:wrap;}
header h1{font-size:18px;color:#fb8b1e;font-weight:700;}
.tabs{display:flex;gap:6px;}
.tab{font-size:13px;font-weight:600;padding:5px 14px;border:1.5px solid #3a3b3e;border-radius:2px;background:#141517;color:#fff;cursor:pointer;}
.tab.on{background:#fb8b1e;border-color:#fb8b1e;color:#0a0a0a;}
.searchwrap{margin-left:auto;position:relative;display:flex;align-items:center;}
.searchwrap svg{position:absolute;left:9px;pointer-events:none;}
#q{background:#141517;border:1px solid #fff;border-radius:2px;color:#d9dde2;font-family:inherit;font-size:13px;padding:6px 10px 6px 30px;width:210px;}
#q:focus{outline:1px solid #fb8b1e;}
main{flex:1;display:flex;min-height:0;}
#list{width:320px;min-width:240px;border-right:1px solid #27282b;overflow-y:auto;}
.item{padding:9px 14px;border-bottom:1px solid #1a1b1e;cursor:pointer;}
.item:hover{background:#14171b;}
.item.on{background:#241a3d;}
.item .t{font-size:16px;font-weight:600;color:#c9ced4;display:flex;gap:8px;align-items:baseline;}
.item.on .t{color:#b9a1fc;}
.item .t .tk{color:#fb8b1e;}
.item .m{font-size:13px;color:#8a919a;margin-top:2px;}
.badge{font-size:11px;font-weight:700;border-radius:2px;padding:1px 6px;vertical-align:1px;}
.badge.transcript{background:#0a3038;color:#67e0f4;}
.badge.analysis{background:#10301c;color:#4ade80;}
#doc{flex:1;overflow-y:auto;padding:26px 34px 60px;line-height:1.75;caret-color:#fb8b1e;color:#fff;}
#doc:focus{outline:none;}
#doc .empty{color:#8a919a;font-size:16px;margin-top:40px;text-align:center;}
#doc h1{font-size:28px;color:#fb8b1e;margin:18px 0 10px;}
#doc h2{font-size:22px;color:#fb8b1e;margin:22px 0 8px;border-bottom:1px solid #27282b;padding-bottom:4px;}
#doc h3{font-size:20px;color:#fb8b1e;margin:16px 0 6px;}
#doc p{font-size:16px;margin:8px 0;}
#doc ul,#doc ol{margin:8px 0 8px 22px;font-size:16px;}
#doc li{margin:3px 0;}
#doc table{border-collapse:collapse;margin:12px 0;font-size:15px;}
#doc th{background:#1a1b1e;color:#fb8b1e;font-size:12px;padding:6px 12px;border:1px solid #27282b;}
#doc td{padding:6px 12px;border:1px solid #27282b;color:#fff;}
#doc blockquote{border-left:3px solid #fb8b1e;padding:4px 14px;color:#fff;background:#111214;margin:10px 0;}
#doc code{background:#1a1b1e;border-radius:2px;padding:1px 5px;font-size:14px;}
#doc hr{border:none;border-top:1px solid #27282b;margin:16px 0;}
#doc .fm{background:#111214;border:1px solid #27282b;border-radius:2px;padding:10px 14px;font-size:13px;color:#8a919a;margin-top:26px;}
#doc .fm b{color:#ffb45e;font-weight:600;}
#doc mark.hl{border-radius:2px;}
#doc mark.hl.c1{background:#241a3d;color:#b9a1fc;}
#doc mark.hl.c2{background:#0a3038;color:#67e0f4;}
#doc mark.hl.c3{background:#10301c;color:#4ade80;}
#hlPop{position:fixed;display:none;z-index:10;gap:8px;padding:7px 10px;background:#141517;border:1px solid #3a3b3e;border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,.5);}
#hlPop .dot{width:18px;height:18px;border-radius:50%;border:1.5px solid #0a0a0a;cursor:pointer;padding:0;}
#hlPop .d1{background:#b9a1fc;}#hlPop .d2{background:#67e0f4;}#hlPop .d3{background:#4ade80;}
@media(max-width:760px){#list{width:44%;}#doc{padding:16px;}}
</style></head><body>
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
        html+='<tr>'+cells.map(function(c){return '<'+tag+'>'+inline(c.trim())+'</'+tag+'>';}).join('')+'</tr>';
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
function ns(x){return typeof x==='string'?{s:x,c:1}:x;}
function markString(s,c){var doc=document.getElementById('doc'),map=textMap(doc),idx=map.text.indexOf(s);
  if(idx<0)return false;
  var st=locate(map,idx),en=locate(map,idx+s.length);if(!st||!en)return false;
  var r=document.createRange();
  try{r.setStart(st.node,st.offset);r.setEnd(en.node,en.offset);
    var m=document.createElement('mark');m.className='hl c'+(c||1);
    m.appendChild(r.extractContents());r.insertNode(m);}catch(e){return false;}
  return true;}
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
  HL[CUR]=(HL[CUR]||[]).concat([{s:s,c:c}]);saveHL();
  if(!skipUndo)UNDO.push({t:'add',s:s,c:c,rel:CUR});
  if(markString(s,c))bindMarks();}
function bindMarks(){Array.prototype.forEach.call(document.querySelectorAll('#doc mark.hl'),function(m){
  m.title='Ctrl+Shift+H로 해제';});}
// ── 읽기 전용 contenteditable (노션식 캐럿 이동·Shift+화살표 선택, 수정은 차단) ──
var docEl=document.getElementById('doc');
['beforeinput','paste','cut','drop'].forEach(function(ev){
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
  if(m){removeMark(m);return;}
  var s=sel.toString().trim();
  if(s.length<2||s.length>2000)return;
  addHL(s,LASTC);
  sel.removeAllRanges();hlPop.style.display='none';});
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


@app.get("/")
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    # 기본=로컬 전용. 테일넷 공개는 DATALAKE_WEBUI_HOST에 테일스케일 IP 지정
    # (테일넷 밖에서는 접근 불가 — tailscale serve 미사용 시의 대안)
    uvicorn.run(app, host=os.getenv("DATALAKE_WEBUI_HOST", "127.0.0.1"),
                port=int(os.getenv("DATALAKE_WEBUI_PORT", "8787")))
