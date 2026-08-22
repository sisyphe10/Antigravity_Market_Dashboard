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
    # 2026-08-18: 새벽 LLM 배치와 08:00 러너의 짧은 write 겹침 시 즉시 'database is locked'
    # 로 죽지 않게 5초 대기 (WAL은 writer 직렬화를 막지 않는다 — codex 검토 C5)
    conn.execute("PRAGMA busy_timeout=5000")
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

        # 4) transcripts — Phase 2 v2 (Codex 권고: filings.metadata_json에서 분리)
        # filing 1건당 다중 source 가능 (예: motley_fool 시도 후 fallback marketbeat success)
        # normalized_url + content_hash로 dedup
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filing_id INTEGER NOT NULL,
                source TEXT NOT NULL,             -- 'motley_fool' / 'marketbeat' / 'manual_override'
                source_url TEXT NOT NULL,
                normalized_url TEXT NOT NULL,
                content_hash TEXT NOT NULL,       -- raw 본문 sha256
                prepared_remarks TEXT,
                qa TEXT,
                parser_version TEXT NOT NULL,
                match_confidence REAL NOT NULL,   -- 0.0 ~ 1.0
                fetched_at TEXT DEFAULT (datetime('now')),
                UNIQUE(filing_id, normalized_url, content_hash),
                FOREIGN KEY(filing_id) REFERENCES filings(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_filing ON transcripts(filing_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_confidence ON transcripts(match_confidence)")

        # Phase 6: 한국어 번역 + Notion append 추적 컬럼 (idempotent ALTER)
        for ddl in (
            "ALTER TABLE transcripts ADD COLUMN translated_kr TEXT",
            "ALTER TABLE transcripts ADD COLUMN prompt_version_translation TEXT",
            "ALTER TABLE transcripts ADD COLUMN translation_model TEXT",
            "ALTER TABLE transcripts ADD COLUMN translation_input_tokens INTEGER",
            "ALTER TABLE transcripts ADD COLUMN translation_output_tokens INTEGER",
            "ALTER TABLE transcripts ADD COLUMN translated_at TEXT",
            "ALTER TABLE transcripts ADD COLUMN notion_appended_at TEXT",
            "ALTER TABLE transcripts ADD COLUMN notion_page_id TEXT",
            # 2026-07-21: Notion append → datalake md 저장 전환 (transcript_store.py)
            "ALTER TABLE transcripts ADD COLUMN md_path TEXT",
            "ALTER TABLE transcripts ADD COLUMN md_saved_at TEXT",
        ):
            try:
                conn.execute(ddl)
            except Exception:
                pass  # 이미 컬럼 있음

        # 5) filing_analyses — Sonnet 분석 결과 별도 테이블 (Codex 권고: metadata_json 분리)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS filing_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filing_id INTEGER NOT NULL,
                analysis_kr TEXT NOT NULL,            -- 한국어 1-page sheet
                yoy_md TEXT,                           -- 기계 산출 YoY 표
                insider_md TEXT,                       -- insider 부록
                prompt_version TEXT NOT NULL,
                analysis_model TEXT NOT NULL,
                input_tokens INTEGER,
                output_tokens INTEGER,
                cache_read_tokens INTEGER,
                cache_creation_tokens INTEGER,
                fiscal_year INTEGER,
                fiscal_quarter INTEGER,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(filing_id) REFERENCES filings(id),
                UNIQUE(filing_id, prompt_version)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_analyses_filing ON filing_analyses(filing_id)")

        # 6) earnings_calendar — Finnhub 발표 일정 사전 적재 (BMO/AMC lookup용)
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
                           source: str = "motley_fool") -> int:
    """transcript 잡 enqueue. filing_id 기반 idempotent (이미 있으면 새로 만들지 않음)."""
    conn = get_conn()
    try:
        # 기존 잡이 있으면 그대로 두고 ID 반환
        existing = conn.execute(
            "SELECT id FROM transcript_jobs WHERE filing_id=? LIMIT 1",
            (filing_id,),
        ).fetchone()
        if existing:
            return existing['id']
        cur = conn.execute(
            """
            INSERT INTO transcript_jobs (filing_id, ticker, next_attempt_at, last_status, source)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (filing_id, ticker, next_attempt_at, source),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_due_transcript_jobs(now_iso: str, limit: int = 20) -> list[dict]:
    """다음 시도 시각이 지난 미완료 잡들. stale_pending은 cleanup_stale → gave_up
    또는 수동 override 전까지 재선택하지 않는다 (next_attempt_at 미갱신으로 무한 재실행 방지)."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT j.*, f.cik, f.accession_number, f.document_type, f.filed_at, f.amc_or_bmo
            FROM transcript_jobs j
            JOIN filings f ON j.filing_id = f.id
            WHERE j.next_attempt_at <= ?
              AND j.last_status NOT IN ('success', 'gave_up', 'needs_review', 'stale_pending')
              -- 'gate_blocked' 는 일부러 제외하지 않는다: 게이트 차단은 완료가 아니라
              -- 실패이므로 다음 주기에 진짜 전문을 다시 찾아야 한다 (2026-07-31)
            ORDER BY j.next_attempt_at ASC
            LIMIT ?
            """,
            (now_iso, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_transcript_job(job_id: int, *, last_status: str, next_attempt_at: str | None = None,
                          attempt_count_delta: int = 1, last_error: str | None = None,
                          source: str | None = None) -> None:
    conn = get_conn()
    try:
        sets = ["last_status=?", "attempt_count = attempt_count + ?"]
        params: list = [last_status, attempt_count_delta]
        if next_attempt_at is not None:
            sets.append("next_attempt_at=?")
            params.append(next_attempt_at)
        if last_error is not None:
            sets.append("last_error=?")
            params.append(last_error)
        if source is not None:
            sets.append("source=?")
            params.append(source)
        params.append(job_id)
        conn.execute(f"UPDATE transcript_jobs SET {', '.join(sets)} WHERE id=?", params)
        conn.commit()
    finally:
        conn.close()


def get_filing_by_id(filing_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM filings WHERE id=?", (filing_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def insert_analysis(*, filing_id: int, analysis_kr: str, yoy_md: str | None,
                    insider_md: str | None, prompt_version: str, analysis_model: str,
                    input_tokens: int | None, output_tokens: int | None,
                    cache_read_tokens: int | None, cache_creation_tokens: int | None,
                    fiscal_year: int | None, fiscal_quarter: int | None) -> int | None:
    """filing_analyses 테이블 INSERT OR IGNORE. (filing_id, prompt_version) 중복 시 None."""
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO filing_analyses
              (filing_id, analysis_kr, yoy_md, insider_md, prompt_version, analysis_model,
               input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
               fiscal_year, fiscal_quarter)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (filing_id, analysis_kr, yoy_md, insider_md, prompt_version, analysis_model,
             input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
             fiscal_year, fiscal_quarter),
        )
        conn.commit()
        return cur.lastrowid if cur.rowcount > 0 else None
    finally:
        conn.close()


def get_latest_analysis(filing_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM filing_analyses WHERE filing_id=? ORDER BY created_at DESC LIMIT 1",
            (filing_id,),
        ).fetchone()
        return dict(row) if row else None
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


def insert_transcript(*, filing_id: int, source: str, source_url: str, normalized_url: str,
                      content_hash: str, prepared_remarks: str | None, qa: str | None,
                      parser_version: str, match_confidence: float) -> int | None:
    """transcripts 테이블 INSERT OR IGNORE. 동일 filing+url+hash 중복 시 None."""
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO transcripts
              (filing_id, source, source_url, normalized_url, content_hash,
               prepared_remarks, qa, parser_version, match_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (filing_id, source, source_url, normalized_url, content_hash,
             prepared_remarks, qa, parser_version, match_confidence),
        )
        conn.commit()
        return cur.lastrowid if cur.rowcount > 0 else None
    finally:
        conn.close()


def get_transcript_for_filing(filing_id: int, *, min_confidence: float = 0.7) -> dict | None:
    """filing의 가장 높은 신뢰도 transcript 1건. 없으면 None."""
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT * FROM transcripts
            WHERE filing_id=? AND match_confidence >= ?
            ORDER BY match_confidence DESC, fetched_at DESC LIMIT 1
            """,
            (filing_id, min_confidence),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ─── Phase 6: transcript 한국어 번역 헬퍼 ───
def update_transcript_translation(transcript_id: int, *, translated_kr: str,
                                   prompt_version_translation: str,
                                   translation_model: str,
                                   translation_input_tokens: int | None,
                                   translation_output_tokens: int | None) -> None:
    """transcript 한국어 번역 결과 in-place 업데이트.

    2026-08-18: md_saved_at/md_path 를 무효화한다 — 재번역 시 stale md 가
    라이브에 남는 사고 차단 (codex C5). save_pending 이 다음 사이클에 재저장.
    """
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE transcripts SET
              translated_kr = ?,
              prompt_version_translation = ?,
              translation_model = ?,
              translation_input_tokens = ?,
              translation_output_tokens = ?,
              translated_at = datetime('now'),
              md_saved_at = NULL,
              md_path = NULL
            WHERE id = ?
            """,
            (translated_kr, prompt_version_translation, translation_model,
             translation_input_tokens, translation_output_tokens, transcript_id),
        )
        conn.commit()
    finally:
        conn.close()


def requeue_gate_blocked_job(filing_id: int, next_attempt_at: str) -> None:
    """게이트가 오염을 차단했을 때, 해당 filing 의 잡을 재수집 대상으로 되돌린다.

    2026-07-31: 차단만 하고 잡을 success 로 두면 진짜 전문이 나중에 올라와도
    영영 수집하지 않는다. 차단 = 실패이지 완료가 아니다.
    """
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE transcript_jobs
               SET last_status = 'gate_blocked',
                   next_attempt_at = ?,
                   last_error = 'gate reject — 재수집 대기'
             WHERE filing_id = ?
            """,
            (next_attempt_at, filing_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_translation_skipped(transcript_id: int, value: int = 1) -> None:
    """번역 부적격 마킹 — 1=게이트 격리 / 2=superseded (2026-08-03 의미론).

    2026-08-22: 번역 진입부의 결정적 게이트 거부를 영구 격리하기 위해 신설 —
    마킹 없이 반환만 하면 다음 배치가 같은 행을 다시 뽑아 슬롯을 소모한다.
    """
    conn = get_conn()
    try:
        conn.execute("UPDATE transcripts SET translation_skipped = ? WHERE id = ?",
                     (value, transcript_id))
        conn.commit()
    finally:
        conn.close()


def filing_has_translated_transcript(filing_id: int) -> bool:
    """해당 filing 에 정상 번역본이 하나라도 있는가 (격리 시 재수집 필요 판단용)."""
    conn = get_conn()
    try:
        r = conn.execute(
            "SELECT 1 FROM transcripts WHERE filing_id = ? AND translated_kr IS NOT NULL LIMIT 1",
            (filing_id,)).fetchone()
        return bool(r)
    finally:
        conn.close()


def _load_starred_tickers() -> set | None:
    """관심종목 별표(universe_stars_v1). 읽기 실패 시 None(필터 미적용)."""
    import json
    p = os.path.join(os.path.dirname(__file__), '..', '..', 'quoteboard', 'prefs.json')
    try:
        t = json.load(open(p, encoding='utf-8')).get('universe_stars_v1', {}).get('tickers')
        return {x.upper() for x in t} if t else None
    except Exception:
        return None


def get_pending_translation_transcripts(limit: int = 5, oldest_first: bool = False,
                                        exclude_ids: set[int] | None = None) -> list[dict]:
    """번역 안 된 transcripts. 기본 최신순 / oldest_first=True 는 새벽 백로그용 오래된 순.

    2026-07-31 사용자 정책: 수집은 전 종목, **번역은 별표 종목만**.
    (백로그 62건이 하루 3건 처리량을 3주치 넘겨 적체됐던 문제의 근본 해법)
    2026-08-18: oldest_first 는 SQL LIMIT 없이 전량 조회 후 별표 필터 —
    limit*10 창 밖의 오래된 별표 pending 을 놓치는 기아를 차단 (codex C9).
    2026-08-22: exclude_ids = 같은 실행에서 이미 실패한 transcript 재선택 제외
    (night_llm 독약 루프 차단). ★DESC(최신순) 경로는 SQL LIMIT 창 안에서만
    걸러지므로 exclude_ids 는 oldest_first(전량 조회) 경로에서만 쓸 것.
    """
    stars = _load_starred_tickers()
    conn = get_conn()
    try:
        order = 'ASC' if oldest_first else 'DESC'
        sql = f"""
            SELECT t.*, f.ticker AS _tk FROM transcripts t
            JOIN filings f ON f.id = t.filing_id
            WHERE t.translated_kr IS NULL
              AND t.match_confidence >= 0.7
              AND t.prepared_remarks IS NOT NULL
              AND COALESCE(t.translation_skipped, 0) = 0
            ORDER BY t.fetched_at {order}
            """
        if oldest_first:
            rows = conn.execute(sql).fetchall()
        else:
            rows = conn.execute(sql + ' LIMIT ?',
                                (limit * 10 if stars else limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            tk = d.pop('_tk', '')
            if exclude_ids and d['id'] in exclude_ids:
                continue
            if stars is not None and tk.upper() not in stars:
                continue
            out.append(d)
            if len(out) >= limit:
                break
        return out
    finally:
        conn.close()


def get_pending_notion_append_transcripts(limit: int = 5) -> list[dict]:
    """번역 완료 + Notion append 미실행 transcripts."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT t.*, f.ticker, f.accession_number
            FROM transcripts t
            JOIN filings f ON t.filing_id = f.id
            WHERE t.translated_kr IS NOT NULL
              AND t.notion_appended_at IS NULL
            ORDER BY t.translated_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_pending_md_save_transcripts(limit: int = 10) -> list[dict]:
    """번역 완료 + datalake md 미저장 transcripts (transcript_store 러너 단계용)."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT t.*, f.ticker, f.accession_number, f.filed_at
            FROM transcripts t
            JOIN filings f ON t.filing_id = f.id
            WHERE t.translated_kr IS NOT NULL
              AND t.md_saved_at IS NULL
            ORDER BY t.translated_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_transcript_md_saved(transcript_id: int, md_path: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE transcripts SET
              md_saved_at = datetime('now'),
              md_path = ?
            WHERE id = ?
            """,
            (md_path, transcript_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_transcript_appended(transcript_id: int, notion_page_id: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE transcripts SET
              notion_appended_at = datetime('now'),
              notion_page_id = ?
            WHERE id = ?
            """,
            (notion_page_id, transcript_id),
        )
        conn.commit()
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
