# -*- coding: utf-8 -*-
"""위키 문답용 MCP stdio 서버 — headless Claude Code 에 도구 3종을 노출한다.

노출: run_sql / search_notes / search_tags  (정본 구현 = wiki_tools.py)
read_file·list_datasets 는 노출하지 않는다 — Claude Code 네이티브 Read/Glob 사용.

기동은 claude 가 --mcp-config 로 자식 프로세스로 띄운다. 직접 실행할 일은 없다.
★stdout 은 JSON-RPC 전용 — 어떤 코드도 print() 하면 안 된다.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wiki_tools  # noqa: E402

from mcp.server import MCPServer  # noqa: E402  (mcp 2.0: FastMCP→MCPServer 개명)

mcp = MCPServer("wiki")


@mcp.tool()
def run_sql(sql: str) -> str:
    """market.duckdb 에 읽기전용 SELECT 를 실행한다. 결과는 최대 200행(CSV).

    뷰 목록·스키마는 ~/datalake/catalog/INDEX.md 를 Read 로 먼저 확인할 것.
    SELECT 외 구문은 거부된다.
    """
    return wiki_tools.run_sql(sql)


@mcp.tool()
def search_notes(pattern: str, max_results: int = 40) -> str:
    """md 코퍼스를 정규식으로 검색한다. `파일경로:줄번호: 매칭줄` 을 반환.

    대상: 리서치노트 원문·어닝콜 번역 전문·실적 분석시트·Notion 스터디·보고서
          아카이브·데이터셋 카탈로그·시스템 위키.
    반환된 경로는 네이티브 Read 도구로 이어 읽으면 된다.
    """
    return wiki_tools.search_notes(pattern, max_results)


@mcp.tool()
def search_tags(tag: str, limit: int = 20) -> str:
    """태그로 코퍼스를 검색한다(JSON). 종목 티커·종목명·테마·섹터·기관명이 태그다.

    특정 종목/주제의 최근 언급을 훑을 때 search_notes 보다 정확하고 빠르다.
    결과의 rel_path 는 ~/datalake 기준 상대경로 — 네이티브 Read 로 읽을 수 있다.
    """
    out = wiki_tools.tag_search(tag, limit)
    return json.dumps(out, ensure_ascii=False)[:20000]


if __name__ == "__main__":
    mcp.run(transport="stdio")
