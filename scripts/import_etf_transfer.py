#!/usr/bin/env python3
"""VM-side 수집 전송 DB → 맥미니 정본 etf_data.db 병합기 (2026-07-21).

VM(깨끗한 망)에서 당일분만 수집한 소형 전송 DB를 받아, 정본 DB의 해당 날짜 행을
원자적으로 교체한다. 부분/실패 수집이 정본을 오염시키지 않도록 임포트 전에 완결성을 검증한다.

usage: import_etf_transfer.py <transfer_db> <date YYYY-MM-DD> [--min-ok N]
exit 0=임포트 성공, 2=검증 실패(임포트 안 함), 1=오류
"""
import sys
import os
import sqlite3

TABLES = ('etf_daily', 'etf_constituents', 'collection_log')


def main():
    if len(sys.argv) < 3:
        print("usage: import_etf_transfer.py <transfer_db> <date> [--min-ok N]", file=sys.stderr)
        return 1
    transfer = sys.argv[1]
    date_str = sys.argv[2]
    min_ok = 1000
    if '--min-ok' in sys.argv:
        min_ok = int(sys.argv[sys.argv.index('--min-ok') + 1])

    if not os.path.exists(transfer):
        print(f"[import] FAIL 전송 DB 없음: {transfer}", file=sys.stderr)
        return 1

    main_db = os.environ.get('ETF_MAIN_DB') or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'etf_data.db')
    if not os.path.exists(main_db):
        print(f"[import] FAIL 정본 DB 없음: {main_db}", file=sys.stderr)
        return 1

    # ── 완결성 검증 (전송 DB) ──
    t = sqlite3.connect(transfer)
    ok = t.execute("SELECT COUNT(*) FROM collection_log WHERE date=? AND status='ok'",
                   (date_str,)).fetchone()[0]
    const = t.execute("SELECT COUNT(*) FROM etf_constituents WHERE date=?",
                      (date_str,)).fetchone()[0]
    daily = t.execute("SELECT COUNT(*) FROM etf_daily WHERE date=?",
                      (date_str,)).fetchone()[0]
    t.close()
    print(f"[import] 전송 DB 검증: date={date_str} ok={ok} const={const} daily={daily} (min_ok={min_ok})")
    if ok < min_ok:
        print(f"[import] ABORT 완결성 미달(ok={ok} < {min_ok}) — 정본 미변경", file=sys.stderr)
        return 2

    # ── 원자적 교체 (정본 DB, 단일 트랜잭션) ──
    m = sqlite3.connect(main_db, timeout=60)
    m.execute("PRAGMA journal_mode=WAL")
    m.execute("PRAGMA busy_timeout=60000")
    try:
        m.execute("ATTACH DATABASE ? AS xfer", (transfer,))
        m.execute("BEGIN IMMEDIATE")
        for tbl in TABLES:
            m.execute(f"DELETE FROM {tbl} WHERE date=?", (date_str,))
            cols = [r[1] for r in m.execute(f"PRAGMA main.table_info({tbl})").fetchall()]
            xcols = [r[1] for r in m.execute(f"PRAGMA xfer.table_info({tbl})").fetchall()]
            use = [c for c in cols if c in xcols]  # 스키마 교집합(구 전송 DB에 qty/px 없을 수 있음)
            collist = ', '.join(use)
            m.execute(
                f"INSERT INTO {tbl} ({collist}) SELECT {collist} FROM xfer.{tbl} WHERE date=?",
                (date_str,))
        m.execute("COMMIT")
    except Exception as e:
        m.execute("ROLLBACK")
        print(f"[import] FAIL 병합 중 오류, 롤백: {e}", file=sys.stderr)
        m.close()
        return 1
    finally:
        try:
            m.execute("DETACH DATABASE xfer")
        except Exception:
            pass

    # ── 사후 확인 ──
    n_ok = m.execute("SELECT COUNT(*) FROM collection_log WHERE date=? AND status='ok'",
                     (date_str,)).fetchone()[0]
    n_const = m.execute("SELECT COUNT(*) FROM etf_constituents WHERE date=?",
                        (date_str,)).fetchone()[0]
    m.close()
    print(f"[import] OK 정본 반영 완료: date={date_str} ok={n_ok} const={n_const}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
