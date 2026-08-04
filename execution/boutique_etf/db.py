# -*- coding: utf-8 -*-
"""boutique_etf.db — 부티크 액티브 ETF 팔로업 전용 독립 DB (etf_data.db 불가침)."""
import os
import sqlite3

DB_PATH = os.environ.get('BOUTIQUE_ETF_DB') or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'boutique_etf.db')


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS etf_registry (
            etf_code TEXT PRIMARY KEY,
            manager  TEXT NOT NULL,
            name     TEXT NOT NULL,
            adapter  TEXT NOT NULL,
            param    TEXT DEFAULT '',
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS etf_daily (
            date TEXT NOT NULL, etf_code TEXT NOT NULL,
            name TEXT, manager TEXT,
            close REAL, nav REAL, nav_prdy_ctrt REAL,
            lstn_stcn INTEGER, aum REAL,
            PRIMARY KEY (date, etf_code)
        );
        CREATE TABLE IF NOT EXISTS etf_constituents (
            date TEXT NOT NULL, etf_code TEXT NOT NULL, stock_code TEXT NOT NULL,
            raw_code TEXT, stock_name TEXT,
            weight REAL, qty_cu REAL, eval_cu REAL, px REAL,
            mcap_krw REAL, invest_amt REAL,
            trade_amt REAL, drift INTEGER DEFAULT 0,
            source TEXT,
            PRIMARY KEY (date, etf_code, stock_code)
        );
        CREATE TABLE IF NOT EXISTS collection_log (
            date TEXT NOT NULL, etf_code TEXT NOT NULL,
            status TEXT NOT NULL, source TEXT,
            truncated INTEGER DEFAULT 0,
            error_msg TEXT, collected_at TEXT,
            PRIMARY KEY (date, etf_code)
        );
        CREATE TABLE IF NOT EXISTS etf_changes (
            date TEXT NOT NULL, etf_code TEXT NOT NULL, stock_code TEXT NOT NULL,
            kind TEXT NOT NULL,
            stock_name TEXT, w_prev REAL, w_cur REAL,
            trade_amt REAL, drift INTEGER DEFAULT 0,
            PRIMARY KEY (date, etf_code, stock_code, kind)
        );
        CREATE TABLE IF NOT EXISTS mcap_cache (
            date TEXT NOT NULL, stock_code TEXT NOT NULL,
            mcap_krw REAL, provider TEXT,
            PRIMARY KEY (date, stock_code)
        );
        CREATE TABLE IF NOT EXISTS excd_map (ticker TEXT PRIMARY KEY, excd TEXT);
    """)
    conn.commit()
    return conn
