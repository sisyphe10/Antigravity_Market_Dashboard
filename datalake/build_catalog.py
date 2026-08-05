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
from dl_common import CATALOG_DIR, DUCKDB_PATH, MARKET_DIR, NOTES_DIR, REPO

DESCRIPTIONS = {
    "kr_ohlcv": "국내 전 상장종목 일봉 — ★무수정 원시세 (KRX 정본, 액면분할 미반영). 장기 수익률 계산은 kr_ohlcv_adj 사용",
    "kr_ohlcv_adj": "국내 전 상장종목 수정주가 일봉 (야후 adj_close) — ★수익률·차트용. 원시세·거래대금은 kr_ohlcv",
    "kr_marcap": "국내 종목별 시가총액·상장주식수 일별",
    "kr_fundamental": "국내 종목별 주당지표 일별 (BPS/PER/PBR/EPS/DIV/DPS) — ★KRX 기준=연간 확정실적 계단식(TTM 아님). "
                      "현재 밸류 정밀 분석엔 부적합, 장기 PBR/PER 밴드·사이클 분석용 (2026-07-22 뷰 재등록)",
    "kr_foreign": "국내 종목별 외국인 보유비중(레벨) 일별",
    "kr_index_ohlcv": "KRX 지수 일봉 (KOSPI/KOSDAQ/KRX/테마 전 시리즈)",
    "kr_etf_ohlcv": "국내 ETF 일봉 + NAV",
    "kr_investor_value": "시장 단위 투자자별 매매대금 일별 (KOSPI/KOSDAQ)",
    "overseas_ohlcv": "해외 유니버스 종목 일봉 (yahoo, adj_close 포함)",
    "global_markets": "글로벌 벤치마크 일봉 — 지수(S&P500·SOX·VIX 등)·환율·원자재·미 금리·BTC (category 컬럼으로 구분)",
    "kr_macro": "ECOS 한국 매크로 33종+파생 3종 전체 이력 (기준금리·국고채·CPI·M2·BSI·수출 등, series 컬럼)",
    "us_macro": "FRED 미국 매크로 36종 전체 이력 (금리·스프레드·CPI·고용·주택 등, series 컬럼)",
    "kr_flows": "증시 수급 자금 이력 — 투자자예탁금·신용거래융자·미수금 등 (금투협, 억원 단위)",
    "macro_series": "레포 dataset.csv 누적 적재 — ECOS/FRED/KOSIS/SMP/리튬/메모리현물 등 기존 수집기가 매일 쌓는 매크로·산업 시계열 899종(series 컬럼). ★dataset.csv 는 덮어쓰기·소급 재작성이 일어나므로 (date, series) upsert 로 누적한다 — CSV 에서 행이 빠져도 레이크는 계속 보유. 적재기 accumulate_macro_series.py. 장기 이력은 kr_macro/us_macro 우선",
    "kr_short": "종목별 일별 공매도 — 거래량·거래대금·잔고수량·잔고금액 (KRX SRT30001). "
                "거래비중=÷kr_ohlcv.volume, 잔고비중=÷kr_marcap.shares 조인 파생. 잔고는 T+2 공시. "
                "★공매도 전면금지 2023-11-06~2025-03-30, 부분금지 2020-03-16~2021-05-02 구간 빈 값 정상",
    "kr_short_investor": "시장단위 투자자별 공매도 (KOSPI/KOSDAQ, metric=volume|value, 기관/개인/외국인/기타)",
    "kr_futures_ohlcv": "KRX 선물 월물별 일별 시세+미결제약정(oi) — 7상품(K200·미니K200·KOSDAQ150·KRX300·"
                        "국채3y/10y·달러), 스프레드 제외. 상품 단위 합계는 kr_futures_oi_daily 뷰",
    "kr_deriv_investor": "파생상품 투자자별 수급 일별 (KRX [13106] MDCSTAT13103) — 선물 7상품+K200옵션+"
                         "선물/옵션 전체, metric=volume(계약)|value(원), side=ask(매도)|bid(매수)|net(순매수). "
                         "세부 주체 9종(금융투자~외국인), 기관합계=fin_invest+insurance+trust+bank+other_fin+pension",
}

EXAMPLE_SQL = {
    "kr_ohlcv": "SELECT date, close, value FROM kr_ohlcv WHERE name='삼성전자' ORDER BY date DESC LIMIT 20;",
    "kr_ohlcv_adj": "SELECT date, adj_close FROM kr_ohlcv_adj WHERE name='삼성전자' AND date>='2015-01-01' ORDER BY date;",
    "kr_investor_value": "SELECT date, foreigner, institution, individual FROM kr_investor_value WHERE market='KOSPI' ORDER BY date DESC LIMIT 10;",
    "overseas_ohlcv": "SELECT date, adj_close FROM overseas_ohlcv WHERE symbol='NVDA' ORDER BY date DESC LIMIT 20;",
    "global_markets": "SELECT date, close FROM global_markets WHERE name='필라델피아 반도체지수' ORDER BY date DESC LIMIT 20;",
    "kr_macro": "SELECT date, value FROM kr_macro WHERE series='국고채 10년' AND date>='2020-01-01' ORDER BY date;",
    "us_macro": "SELECT date, value FROM us_macro WHERE series='미 CPI 전년동월비' ORDER BY date DESC LIMIT 12;",
    "kr_flows": "SELECT date, value FROM kr_flows WHERE series='투자자예탁금' ORDER BY date DESC LIMIT 20;",
    "macro_series": "SELECT DISTINCT dtype FROM macro_series;\n"
                    "SELECT date, value FROM macro_series WHERE series='SMP' ORDER BY date DESC LIMIT 10;",
    "kr_short": "SELECT s.date, s.short_volume, s.short_volume/o.volume AS short_ratio, s.balance_qty\n"
                "FROM kr_short s JOIN kr_ohlcv o USING(date, ticker)\n"
                "WHERE s.name='삼성전자' ORDER BY s.date DESC LIMIT 20;",
    "kr_short_investor": "SELECT date, foreigner, institution FROM kr_short_investor "
                         "WHERE market='KOSPI' AND metric='value' ORDER BY date DESC LIMIT 20;",
    "kr_futures_ohlcv": "SELECT date, name, close, oi FROM kr_futures_ohlcv "
                        "WHERE prod='KRDRVFUK2I' ORDER BY date DESC, oi DESC LIMIT 20;",
    "kr_deriv_investor": "SELECT date_trunc('week', date) wk, sum(foreigner_total) frn_net\n"
                         "FROM kr_deriv_investor WHERE prod='KR___FUK2I' AND metric='volume' AND side='net'\n"
                         "GROUP BY 1 ORDER BY 1 DESC LIMIT 10;",
}


# 컬럼 단위 (2026-08-05) — 카탈로그에 단위가 없어 LLM 문답이 원/억원/조원을 오해했다(실사고).
# 전부 실측으로 확인한 것만 적는다. 미확인 데이터셋은 넣지 않는다
# (틀린 단위를 적는 것이 없는 것보다 나쁘다).
UNITS = {
    "kr_ohlcv": "가격(open/high/low/close) **원** · volume **주** · value(거래대금) **원** · change_pct **%**",
    "kr_ohlcv_adj": "가격(adj_close 등) **원** (야후 수정주가) · volume **주**",
    "kr_marcap": "marcap(시가총액) **원** · shares(상장주식수) **주** · volume **주** · value **원**",
    "kr_foreign": "shares·held(보유주식수)·limit_qty **주** · ratio(보유비중)·exhaustion(소진율) **%** (51.03 = 51.03%)",
    "kr_short": "short_volume·balance_qty **주** · short_value·balance_value **원**",
    "kr_index_ohlcv": "가격(open/high/low/close) **지수 포인트** · volume **주** · value **원** · marcap **원**",
    "kr_etf_ohlcv": "nav·가격 **원** · volume **주** · value **원** · index_value **지수 포인트**",
    "kr_investor_value": "전 주체 컬럼(institution·individual·foreigner·pension 등) **원** 단위 순매수 금액. "
                         "조원 환산 = 1e12 로 나눔, 억원 환산 = 1e8 로 나눔. "
                         "시장 전체는 제로섬 — institution+other_corp+individual+foreigner+other_foreign = 0",
    "kr_deriv_investor": "metric 컬럼으로 구분 — metric=value 면 **원**, metric=volume 면 **계약수**",
    "overseas_ohlcv": "가격 **상장 통화 기준** (예: 0700.HK→HKD, AAPL→USD) · volume **주**",
    "global_markets": "category 별 상이 — index **지수 포인트**, fx **환율**, rate **%**, commodity 각 상품 표준 단위",
    "kr_flows": "series 별 상이 — KOFIA 원자료 단위를 그대로 유지",
    "kr_macro": "series 별 상이 — ECOS 원자료 단위(%·지수·억원 등). 개별 series 확인 필요",
    "us_macro": "series 별 상이 — FRED 원자료 단위. 개별 series 확인 필요",
    "macro_series": "series 별 상이 — dataset.csv 원자료 단위. 개별 series 확인 필요",
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

    import time

    import duckdb
    datasets = scan_datasets()
    if not datasets:
        print("데이터셋 없음 — 백필 먼저 실행하세요")
        return 0

    if args.check:
        con = duckdb.connect(":memory:")
    else:
        # DuckDB는 단일 writer — 웹 UI의 read_only 연결과 겹치면 잠시 실패할 수 있어 재시도
        for attempt in range(5):
            try:
                con = duckdb.connect(DUCKDB_PATH)
                break
            except duckdb.Error as e:
                if attempt == 4:
                    print(f"! market.duckdb 쓰기 연결 실패(웹 UI 사용 중?): {e}")
                    return 1
                time.sleep(3)
    os.makedirs(CATALOG_DIR, exist_ok=True)
    index_rows = []

    for name, files in datasets.items():
        pattern = os.path.join(MARKET_DIR, name, "*.parquet").replace("\\", "/")
        # union_by_name: 연도 파일 간 컬럼 구성이 달라도(과거분 스키마 진화) 뷰가 깨지지 않게
        src = f"read_parquet('{pattern}', union_by_name=true)"
        if not args.check:
            con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM {src}")
        stats = con.execute(f"SELECT COUNT(*), MIN(date), MAX(date) FROM {src}").fetchone()
        rows, dmin, dmax = stats
        cols = con.execute(f"DESCRIBE SELECT * FROM {src} LIMIT 0").fetchall()
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
                + (f"## 단위\n\n{UNITS[name]}\n\n" if name in UNITS else "")
                + f"## 쿼리 예시\n\n```sql\n{EXAMPLE_SQL.get(name, f'SELECT * FROM {name} ORDER BY date DESC LIMIT 20;')}\n```\n"
            )
            with open(os.path.join(CATALOG_DIR, f"{name}.md"), "w", encoding="utf-8", newline="\n") as f:
                f.write(md)

    # 선물 상품 단위 미결제약정 합산 뷰 (월물 합계)
    if "kr_futures_ohlcv" in datasets and not args.check:
        con.execute(
            """CREATE OR REPLACE VIEW kr_futures_oi_daily AS
               SELECT date, prod, prod_name, SUM(oi) AS oi,
                      SUM(volume) AS volume, SUM(value) AS value
               FROM kr_futures_ohlcv GROUP BY date, prod, prod_name""")
        md = (
            "# kr_futures_oi_daily\n\nkr_futures_ohlcv의 상품 단위 일별 합산 뷰 — "
            "월물 합계 미결제약정(oi)·거래량·거래대금.\n\n"
            "## 쿼리 예시\n\n```sql\nSELECT date, oi FROM kr_futures_oi_daily "
            "WHERE prod_name='KOSPI200 선물' ORDER BY date DESC LIMIT 20;\n```\n"
        )
        with open(os.path.join(CATALOG_DIR, "kr_futures_oi_daily.md"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(md)

    # ★macro_series 특수처리 제거 (2026-07-30) — 종전엔 dataset.csv 를 market/ 안으로
    #   shutil.copy2 복사하고 그 CSV 를 read_csv 하는 뷰였다. 즉 '미러'라서 dataset.csv 에서
    #   행이 사라지면 레이크에서도 사라졌고, 데이터레이크의 목적(과거 유실 방지)을 이 900여
    #   시리즈에 대해선 달성하지 못했다. 이제 accumulate_macro_series.py 가 연도 parquet 로
    #   upsert 누적하므로, 위 일반 등록 루프가 다른 데이터셋과 똑같이 뷰를 만든다.

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
