"""SQLite — accession_number + ticker + document_type + processing_stage 복합 유니크 키.

Codex BLOCKER #3 대응. processing_stage 별로 행을 두고 stage 진행 상태를 추적해서
중복 알림/Notion 쓰기/Claude 호출 방지.

테이블 구조:
- filings: 1건의 EDGAR/Finnhub 이벤트당 1행 + stage별 처리 시점 컬럼
- transcript_jobs: BMO/AMC 인지 폴링 큐
- prompts: prompt_version 메타 (출력에 태깅하기 위함)
"""
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'earnings.db')


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec='seconds')


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """스키마 생성 + 마이그레이션 (idempotent)."""
    conn = get_conn()
    try:
        # 1) filings — EDGAR 8-K/6-K, NT 10-Q/K, IR Day 등 모든 이벤트
        # 복합 유니크 키: accession_number(또는 source_id) + ticker + document_type + stage
        conn.execute("""
            CREATE TABLE IF NOT EXISTS filings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                cik TEXT,
                accession_number TEXT,
                source_id TEXT,            -- accession_number 없는 외부 소스(IR Day 등)용
                document_type TEXT NOT NULL,  -- '8-K' / '6-K' / 'NT-10-Q' / 'IR_DAY' / 'Form-4'
                form_item TEXT,            -- '2.02' / '7.01' 등 8-K item
                filed_at TEXT,             -- ISO8601 UTC
                amc_or_bmo TEXT,           -- 'AMC' / 'BMO' / 'UNKNOWN' (transcript 윈도우 산출용)
                stage TEXT NOT NULL,       -- 'fetched' / 'analyzed' / 'translated' / 'transcript_appended' / 'published' / 'notified'
                severity TEXT,             -- 'CRITICAL' / 'HIGH' / 'NORMAL' / 'INFO'
                source_url TEXT,
                raw_artifact_path TEXT,    -- 원본 아티팩트 아카이브 경로
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                metadata_json TEXT,        -- prompt_version, schema_version, tokens 등
                UNIQUE(ticker, accession_number, document_type, stage)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_filings_ticker_filed ON filings(ticker, filed_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_filings_stage ON filings(stage)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_filings_accession ON filings(accession_number)")

        # 2) transcript_jobs — BMO/AMC 인지 폴링 큐
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transcript_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filing_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                next_attempt_at TEXT NOT NULL,   -- ISO8601 UTC
                attempt_count INTEGER DEFAULT 0,
                last_status TEXT,                 -- 'pending' / 'success' / 'fail_retry' / 'gave_up'
                source TEXT,                      -- 'motley_fool' / 'marketbeat'
                last_error TEXT,
                FOREIGN KEY(filing_id) REFERENCES filings(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_due ON transcript_jobs(next_attempt_at) WHERE last_status != 'success'")

        # 3) prompts — prompt_version 메타 (각 출력에 태깅)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                version TEXT PRIMARY KEY,
                description TEXT,
                analysis_model TEXT,         -- e.g. 'claude-sonnet-4-6'
                translation_model TEXT,      -- e.g. 'claude-haiku-4-5'
                skill_md_sha256 TEXT,        -- earnings-analysis SKILL.md 변경 추적
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # 4) earnings_calendar — Finnhub 발표 일정 사전 적재 (BMO/AMC lookup용)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS earnings_calendar (
                ticker TEXT NOT NULL,
                event_date TEXT NOT NULL,    -- YYYY-MM-DD (Eastern Time 기준)
                hour TEXT,                    -- 'amc' / 'bmo' / 'dmh' / NULL
                year INTEGER,
                quarter INTEGER,
                eps_estimate REAL,
                revenue_estimate REAL,
                fetched_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (ticker, event_date)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_calendar_date ON earnings_calendar(event_date)")

        conn.commit()
    finally:
        conn.close()


def upsert_filing(
    *,
    ticker: str,
    document_type: str,
    stage: str,
    accession_number: str | None = None,
    source_id: str | None = None,
    cik: str | None = None,
    form_item: str | None = None,
    filed_at: str | None = None,
    amc_or_bmo: str | None = None,
    severity: str | None = None,
    source_url: str | None = None,
    raw_artifact_path: str | None = None,
    metadata_json: str | None = None,
) -> int | None:
    """Idempotent insert. (ticker, accession_number, document_type, stage) 중복 시 None 반환."""
    if not accession_number and not source_id:
        raise ValueError("accession_number 또는 source_id 중 하나는 필수")
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO filings
              (ticker, cik, accession_number, source_id, document_type, form_item,
               filed_at, amc_or_bmo, stage, severity, source_url, raw_artifact_path,
               updated_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ticker, cik, accession_number, source_id, document_type, form_item,
             filed_at, amc_or_bmo, stage, severity, source_url, raw_artifact_path,
             _utcnow(), metadata_json),
        )
        conn.commit()
        return cur.lastrowid if cur.rowcount > 0 else None
    finally:
        conn.close()


def has_processed(ticker: str, document_type: str, stage: str,
                  accession_number: str | None = None,
                  source_id: str | None = None) -> bool:
    """이미 해당 stage까지 처리됐는지 (중복 알림 방지 체크)."""
    if not accession_number and not source_id:
        raise ValueError("accession_number 또는 source_id 중 하나는 필수")
    conn = get_conn()
    try:
        if accession_number:
            row = conn.execute(
                "SELECT 1 FROM filings WHERE ticker=? AND accession_number=? AND document_type=? AND stage=? LIMIT 1",
                (ticker, accession_number, document_type, stage),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM filings WHERE ticker=? AND source_id=? AND document_type=? AND stage=? LIMIT 1",
                (ticker, source_id, document_type, stage),
            ).fetchone()
        return row is not None
    finally:
        conn.close()


def enqueue_transcript_job(filing_id: int, ticker: str, next_attempt_at: str,
                           source: str = "motley_fool") -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO transcript_jobs (filing_id, ticker, next_attempt_at, last_status, source)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (filing_id, ticker, next_attempt_at, source),
        )
        conn.commit()
    finally:
        conn.close()


def upsert_calendar_entry(ticker: str, event_date: str, hour: str | None,
                          year: int | None, quarter: int | None,
                          eps_estimate: float | None, revenue_estimate: float | None) -> None:
    """Finnhub earnings calendar 항목 upsert. (ticker, event_date) 충돌 시 최신값 덮어쓰기."""
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO earnings_calendar
              (ticker, event_date, hour, year, quarter, eps_estimate, revenue_estimate, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(ticker, event_date) DO UPDATE SET
              hour=excluded.hour,
              year=excluded.year,
              quarter=excluded.quarter,
              eps_estimate=excluded.eps_estimate,
              revenue_estimate=excluded.revenue_estimate,
              fetched_at=datetime('now')
            """,
            (ticker, event_date, hour, year, quarter, eps_estimate, revenue_estimate),
        )
        conn.commit()
    finally:
        conn.close()


def lookup_calendar_hour(ticker: str, event_date: str) -> str | None:
    """공시 도착 시 BMO/AMC 추론용. 없으면 None."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT hour FROM earnings_calendar WHERE ticker=? AND event_date=?",
            (ticker, event_date),
        ).fetchone()
        return row['hour'] if row else None
    finally:
        conn.close()


def register_prompt_version(version: str, description: str, analysis_model: str,
                            translation_model: str, skill_md_sha256: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO prompts (version, description, analysis_model, translation_model, skill_md_sha256)
            VALUES (?, ?, ?, ?, ?)
            """,
            (version, description, analysis_model, translation_model, skill_md_sha256),
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"DB initialized at {DB_PATH}")
