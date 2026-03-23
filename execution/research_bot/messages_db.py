import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'research_notes.db')

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            message_type TEXT NOT NULL,
            text_content TEXT,
            media_path TEXT,
            url TEXT,
            article_content TEXT,
            forward_source TEXT,
            telegram_message_id INTEGER,
            processed INTEGER DEFAULT 0
        )
    """)
    # article_content 컬럼이 없으면 추가 (기존 DB 호환)
    try:
        conn.execute("ALTER TABLE messages ADD COLUMN article_content TEXT")
    except:
        pass
    conn.commit()
    conn.close()

def add_message(timestamp, message_type, text_content=None, media_path=None, url=None, article_content=None, forward_source=None, telegram_message_id=None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (timestamp, message_type, text_content, media_path, url, article_content, forward_source, telegram_message_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (timestamp, message_type, text_content, media_path, url, article_content, forward_source, telegram_message_id)
    )
    conn.commit()
    conn.close()

def get_messages_by_date(date_str):
    """date_str: 'YYYY-MM-DD'"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM messages WHERE timestamp LIKE ? AND processed = 0 ORDER BY timestamp",
        (f"{date_str}%",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_today_count(date_str):
    conn = get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE timestamp LIKE ? AND processed = 0",
        (f"{date_str}%",)
    ).fetchone()[0]
    conn.close()
    return count

def mark_processed(date_str):
    conn = get_conn()
    conn.execute(
        "UPDATE messages SET processed = 1 WHERE timestamp LIKE ? AND processed = 0",
        (f"{date_str}%",)
    )
    conn.commit()
    conn.close()

init_db()
