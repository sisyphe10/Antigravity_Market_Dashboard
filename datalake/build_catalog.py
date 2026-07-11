# -*- coding: utf-8 -*-
"""데이터 카탈로그 + DuckDB 뷰 생성기.

~/datalake/market/*/ 의 parquet을 스캔해서
  ① market/market.duckdb 에 데이터셋별 뷰 (재)생성
  ② catalog/<dataset>.md — 스키마·기간·행수·쿼리 예시 (LLM 문답용)
  ③ catalog/INDEX.md — 전체 목록

사용:
  python3 datalake/build_catalog.py           # 뷰+카탈로그 재생성
  python3 datalake/build_catalog.py --check   # 현황 출력만
"""
import argparse
import glob
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dl_common import CATALOG_DIR, DUCKDB_PATH, MARKET_DIR, NOTES_DIR

DESCRIPTIONS = {
    "kr_ohlcv": "국내 전 상장종목 일봉 (수정주가). open/high/low/close/volume/value, ticker·name·market",
    "kr_marcap": "국내 종목별 시가총액·상장주식수 일별",
    "kr_fundamental": "국내 종목별 후행 밸류에이션 일별 (per/pbr/eps/bps/div/dps)",
    "kr_foreign": "국내 종목별 외국인 보유비중(레벨) 일별",
    "kr_index_ohlcv": "KRX 지수 일봉 (KOSPI/KOSDAQ/KRX/테마 전 시리즈)",
    "kr_etf_ohlcv": "국내 ETF 일봉 + NAV",
    "kr_investor_value": "시장 단위 투자자별 매매대금 일별 (KOSPI/KOSDAQ)",
    "overseas_ohlcv": "해외 유니버스 종목 일봉 (yahoo, adj_close 포함)",
}

EXAMPLE_SQL = {
    "kr_ohlcv": "SELECT date, close FROM kr_ohlcv WHERE name='삼성전자' ORDER BY date DESC LIMIT 20;",
    "kr_fundamental": "SELECT date, per, pbr FROM kr_fundamental WHERE name='삼성전자' AND date>='2024-01-01' ORDER BY date;",
    "kr_investor_value": "SELECT date, foreigner, institution, individual FROM kr_investor_value WHERE market='KOSPI' ORDER BY date DESC LIMIT 10;",
    "overseas_ohlcv": "SELECT date, adj_close FROM overseas_ohlcv WHERE symbol='NVDA' ORDER BY date DESC LIMIT 20;",
}


def scan_datasets():
    out = {}
    if not os.path.isdir(MARKET_DIR):
        return out
    for d in sorted(os.listdir(MARKET_DIR)):
        path = os.path.join(MARKET_DIR, d)
        if not os.path.isdir(path):
            continue
        files = sorted(glob.glob(os.path.join(path, "[0-9]" * 4 + ".parquet")))
        if files:
            out[d] = files
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="현황 출력만")
    args = ap.parse_args()

    import duckdb
    datasets = scan_datasets()
    if not datasets:
        print("데이터셋 없음 — 백필 먼저 실행하세요")
        return 0

    con = duckdb.connect(":memory:") if args.check else duckdb.connect(DUCKDB_PATH)
    os.makedirs(CATALOG_DIR, exist_ok=True)
    index_rows = []

    for name, files in datasets.items():
        pattern = os.path.join(MARKET_DIR, name, "*.parquet").replace("\\", "/")
        if not args.check:
            con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{pattern}')")
        stats = con.execute(
            f"SELECT COUNT(*), MIN(date), MAX(date) FROM read_parquet('{pattern}')"
        ).fetchone()
        rows, dmin, dmax = stats
        cols = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{pattern}') LIMIT 0").fetchall()
        col_lines = "\n".join(f"| {c[0]} | {c[1]} |" for c in cols)
        period = f"{str(dmin)[:10]} ~ {str(dmax)[:10]}"
        index_rows.append((name, rows, period))
        print(f"  {name}: {rows:,}행, {period}, 파일 {len(files)}개")

        if not args.check:
            md = (
                f"# {name}\n\n{DESCRIPTIONS.get(name, '')}\n\n"
                f"- 기간: {period}\n- 행수: {rows:,}\n- 파일: `market/{name}/*.parquet` (연도 파티션)\n"
                f"- 조회: `duckdb ~/datalake/market/market.duckdb` 후 뷰 `{name}` 사용\n\n"
                f"## 스키마\n\n| 컬럼 | 타입 |\n|:---:|:---:|\n{col_lines}\n\n"
                f"## 쿼리 예시\n\n```sql\n{EXAMPLE_SQL.get(name, f'SELECT * FROM {name} ORDER BY date DESC LIMIT 20;')}\n```\n"
            )
            with open(os.path.join(CATALOG_DIR, f"{name}.md"), "w", encoding="utf-8", newline="\n") as f:
                f.write(md)

    # research notes 현황
    note_files = glob.glob(os.path.join(NOTES_DIR, "*", "*.md"))
    note_line = f"research_notes: {len(note_files)}일치 md"
    print(f"  {note_line}")

    if not args.check:
        lines = [
            "# Datalake 카탈로그", "",
            f"생성: {datetime.now().strftime('%Y-%m-%d %H:%M')} (build_catalog.py 자동 생성 — 직접 수정 금지)", "",
            "| 데이터셋 | 행수 | 기간 | 설명 |", "|:---:|:---:|:---:|:---|",
        ]
        for name, rows, period in index_rows:
            lines.append(f"| [{name}]({name}.md) | {rows:,} | {period} | {DESCRIPTIONS.get(name, '')} |")
        lines += ["", f"- {note_line} (`research_notes/YYYY/YYYY-MM-DD.md`)",
                  "- 스냅샷: `snapshots/YYYY/MM/DD/*.gz`", ""]
        with open(os.path.join(CATALOG_DIR, "INDEX.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines))
        print(f"카탈로그+뷰 생성 완료 → {CATALOG_DIR}, {DUCKDB_PATH}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
