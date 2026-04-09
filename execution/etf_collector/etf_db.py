"""ETF 구성종목 DB (SQLite) - 스키마, 연결, 쿼리 헬퍼"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'etf_data.db')


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS etf_daily (
            date TEXT NOT NULL,
            etf_code TEXT NOT NULL,
            etf_name TEXT,
            close_price INTEGER,
            nav REAL,
            volume INTEGER,
            aum INTEGER,
            market_cap INTEGER,
            PRIMARY KEY (date, etf_code)
        );

        CREATE TABLE IF NOT EXISTS etf_constituents (
            date TEXT NOT NULL,
            etf_code TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            weight REAL NOT NULL,
            PRIMARY KEY (date, etf_code, stock_code)
        );

        CREATE TABLE IF NOT EXISTS collection_log (
            date TEXT NOT NULL,
            etf_code TEXT NOT NULL,
            status TEXT NOT NULL,
            error_msg TEXT,
            collected_at TEXT NOT NULL,
            PRIMARY KEY (date, etf_code)
        );

        CREATE INDEX IF NOT EXISTS idx_constituents_stock_date
            ON etf_constituents (stock_code, date);
        CREATE INDEX IF NOT EXISTS idx_constituents_etf_stock
            ON etf_constituents (etf_code, stock_code, date);
        CREATE INDEX IF NOT EXISTS idx_daily_date_aum
            ON etf_daily (date, aum DESC);
        CREATE INDEX IF NOT EXISTS idx_daily_etf_date
            ON etf_daily (etf_code, date);
    """)
    conn.commit()
    conn.close()


def get_collected_codes(conn, date_str):
    """해당 날짜에 이미 수집 완료된 ETF 코드 set"""
    rows = conn.execute(
        "SELECT etf_code FROM collection_log WHERE date=? AND status='ok'",
        (date_str,)
    ).fetchall()
    return set(r['etf_code'] for r in rows)


def insert_etf_daily_batch(conn, rows):
    """etf_daily 일괄 INSERT OR REPLACE"""
    conn.executemany(
        "INSERT OR REPLACE INTO etf_daily (date, etf_code, etf_name, close_price, nav, volume, aum, market_cap) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows
    )


def insert_constituents_batch(conn, rows):
    """etf_constituents 일괄 INSERT OR REPLACE"""
    conn.executemany(
        "INSERT OR REPLACE INTO etf_constituents (date, etf_code, stock_code, stock_name, weight) "
        "VALUES (?, ?, ?, ?, ?)",
        rows
    )


def log_collection(conn, date_str, etf_code, status, error_msg=None):
    """수집 로그 기록"""
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO collection_log (date, etf_code, status, error_msg, collected_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (date_str, etf_code, status, error_msg, now)
    )


# ── 쿼리 헬퍼 ──

def get_etfs_holding_stock(stock_name, date_str=None):
    """특정 종목을 ��유한 ETF 목록 + 비중"""
    conn = get_conn()
    if not date_str:
        date_str = conn.execute("SELECT MAX(date) FROM etf_constituents").fetchone()[0]
    rows = conn.execute("""
        SELECT c.date, c.etf_code, d.etf_name, c.weight, d.aum
        FROM etf_constituents c
        LEFT JOIN etf_daily d ON c.date = d.date AND c.etf_code = d.etf_code
        WHERE c.stock_name LIKE ?
        AND c.date = ?
        ORDER BY c.weight DESC
    """, (f'%{stock_name}%', date_str)).fetchall()
    conn.close()
    return rows


def get_stock_weight_history(stock_name, etf_code=None, limit=90):
    """종목의 ETF별 비중 변화 히스토리"""
    conn = get_conn()
    if etf_code:
        rows = conn.execute("""
            SELECT c.date, c.etf_code, d.etf_name, c.weight
            FROM etf_constituents c
            LEFT JOIN etf_daily d ON c.date = d.date AND c.etf_code = d.etf_code
            WHERE c.stock_name LIKE ? AND c.etf_code = ?
            ORDER BY c.date DESC LIMIT ?
        """, (f'%{stock_name}%', etf_code, limit)).fetchall()
    else:
        rows = conn.execute("""
            SELECT c.date, c.etf_code, d.etf_name, c.weight
            FROM etf_constituents c
            LEFT JOIN etf_daily d ON c.date = d.date AND c.etf_code = d.etf_code
            WHERE c.stock_name LIKE ?
            ORDER BY c.date DESC, c.weight DESC LIMIT ?
        """, (f'%{stock_name}%', limit)).fetchall()
    conn.close()
    return rows


def get_top_etfs_by_aum(date_str=None, limit=30):
    """AUM 기준 상위 ETF"""
    conn = get_conn()
    if not date_str:
        date_str = conn.execute("SELECT MAX(date) FROM etf_daily").fetchone()[0]
    rows = conn.execute("""
        SELECT date, etf_code, etf_name, aum, nav, close_price
        FROM etf_daily
        WHERE date = ?
        ORDER BY aum DESC LIMIT ?
    """, (date_str, limit)).fetchall()
    conn.close()
    return rows
