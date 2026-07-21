#!/usr/bin/env python3
"""정본 etf_data.db의 특정 날짜 etf_daily → 소형 시드 DB 생성 (2026-07-21).

VM-side 수집이 KRX(간헐 장애) 재조회 없이 진행되도록, 이미 확보된 그날의 ETF 목록(etf_daily)을
전송 DB의 초기값으로 심는다. 시드된 전송 DB로 collect_etf_daily.py를 돌리면 목록을 재사용하고
etfcheck 구성종목만 채운다.

usage: make_etf_seed.py <date YYYY-MM-DD> <seed_db_path>
stdout: "SEED <n>" (n=심은 etf_daily 행 수; 0이면 시드 파일 미생성)
"""
import sys
import os
import sqlite3

DAILY_COLS = "date, etf_code, etf_name, close_price, nav, volume, aum, market_cap"


def main():
    if len(sys.argv) < 3:
        print("usage: make_etf_seed.py <date> <seed_db>", file=sys.stderr)
        return 1
    date_str, seed = sys.argv[1], sys.argv[2]
    main_db = os.environ.get('ETF_MAIN_DB') or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'etf_data.db')
    if not os.path.exists(main_db):
        print(f"정본 DB 없음: {main_db}", file=sys.stderr)
        return 1

    m = sqlite3.connect(main_db)
    rows = m.execute(
        f"SELECT {DAILY_COLS} FROM etf_daily WHERE date=?", (date_str,)
    ).fetchall()
    m.close()

    if not rows:
        print("SEED 0")
        return 0

    if os.path.exists(seed):
        os.remove(seed)
    s = sqlite3.connect(seed)
    s.execute("""
        CREATE TABLE etf_daily (
            date TEXT NOT NULL, etf_code TEXT NOT NULL, etf_name TEXT,
            close_price INTEGER, nav REAL, volume INTEGER, aum INTEGER, market_cap INTEGER,
            PRIMARY KEY (date, etf_code)
        )""")
    s.executemany(
        f"INSERT INTO etf_daily ({DAILY_COLS}) VALUES (?,?,?,?,?,?,?,?)", rows)
    s.commit()
    s.close()
    print(f"SEED {len(rows)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
