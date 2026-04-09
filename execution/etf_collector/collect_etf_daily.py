#!/usr/bin/env python3
"""ETF 구성종목 일별 수집 스크립트
매일 장 마감 후 실행: 전체 ETF 목록 + 구성종목/비중 수집 → SQLite 저장
"""
import sys
import os
import fcntl
import logging
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

KST = timezone(timedelta(hours=9))
KRX_API_KEY = 'E9E8B0A915D74BC59CFA41D5534CF19EF4B24C9E'
BATCH_SIZE = 50
POLITENESS_DELAY = 0.3

# 파일 락
_lock_file = open('/tmp/etf_collector.lock', 'w')
try:
    fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    _lock_file.write(str(os.getpid()))
    _lock_file.flush()
except IOError:
    print("ERROR: etf_collector is already running. Exiting.")
    sys.exit(1)


def fetch_etf_list(date_str):
    """KRX OpenAPI에서 전체 ETF 목록 + 일별 시세 조회"""
    from pykrx_openapi import KRXOpenAPI
    import pandas as pd

    api = KRXOpenAPI(KRX_API_KEY)
    result = api.get_etf_daily_trade(date_str.replace('-', ''))
    df = pd.DataFrame(result['OutBlock_1'])

    etfs = []
    for _, row in df.iterrows():
        try:
            etfs.append({
                'etf_code': str(row.get('ISU_CD', '')),
                'etf_name': str(row.get('ISU_NM', '')),
                'close_price': int(float(row.get('TDD_CLSPRC', 0) or 0)),
                'nav': float(row.get('NAV', 0) or 0),
                'volume': int(float(row.get('ACC_TRDVOL', 0) or 0)),
                'aum': int(float(row.get('INVSTASST_NETASST_TOTAMT', 0) or 0)),
                'market_cap': int(float(row.get('MKTCAP', 0) or 0)),
            })
        except (ValueError, TypeError):
            continue
    return etfs


def collect_constituents(conn, date_str, etf_list, already_done):
    """etfcheck API로 구성종목 수집"""
    from etfcheck_client import fetch_constituents

    pending = [e for e in etf_list if e['etf_code'] not in already_done]
    logging.info(f"Constituent collection: {len(pending)} ETFs pending ({len(already_done)} already done)")

    success = 0
    errors = 0
    empty = 0

    for i, etf in enumerate(pending):
        code = etf['etf_code']
        try:
            constituents = fetch_constituents(code)

            if constituents:
                from etf_db import insert_constituents_batch, log_collection
                rows = [(date_str, code, c['stock_code'], c['stock_name'], c['weight'])
                        for c in constituents if c['stock_name']]
                insert_constituents_batch(conn, rows)
                log_collection(conn, date_str, code, 'ok')
                success += 1
            else:
                from etf_db import log_collection
                log_collection(conn, date_str, code, 'empty')
                empty += 1

        except Exception as e:
            from etf_db import log_collection
            log_collection(conn, date_str, code, 'error', str(e)[:200])
            errors += 1

        # 배치 커밋 + 진행 로그
        if (i + 1) % BATCH_SIZE == 0:
            conn.commit()
            logging.info(f"  [{i+1}/{len(pending)}] ok={success} err={errors} empty={empty}")

        time.sleep(POLITENESS_DELAY)

    conn.commit()
    return success, errors, empty


def retry_failed(conn, date_str, etf_list):
    """실패한 ETF 1회 재시도"""
    failed = conn.execute(
        "SELECT etf_code FROM collection_log WHERE date=? AND status='error'",
        (date_str,)
    ).fetchall()
    failed_codes = set(r['etf_code'] for r in failed)

    if not failed_codes:
        return 0, 0, 0

    logging.info(f"Retrying {len(failed_codes)} failed ETFs...")
    # 실패 로그 삭제 (재시도 위해)
    conn.execute("DELETE FROM collection_log WHERE date=? AND status='error'", (date_str,))
    conn.commit()

    retry_list = [e for e in etf_list if e['etf_code'] in failed_codes]
    return collect_constituents(conn, date_str, retry_list, set())


def main():
    from etf_db import init_db, get_conn, get_collected_codes, insert_etf_daily_batch

    # 날짜 인자: python collect_etf_daily.py 2026-04-08
    if len(sys.argv) > 1:
        date_str = sys.argv[1]
    else:
        now = datetime.now(KST)
        date_str = now.strftime('%Y-%m-%d')
        if now.weekday() >= 5:
            logging.info(f"Weekend ({now.strftime('%A')}), skipping.")
            return

    logging.info(f"=== ETF Collection Start: {date_str} ===")

    init_db()
    conn = get_conn()

    # 이미 수집 완료 체크
    already_done = get_collected_codes(conn, date_str)
    if len(already_done) >= 1000:
        logging.info(f"Already collected {len(already_done)} ETFs today. Skipping.")
        conn.close()
        return

    # Step 1: KRX OpenAPI → ETF 목록 + 일별 시세
    logging.info("Step 1: Fetching ETF list from KRX OpenAPI...")
    try:
        etf_list = fetch_etf_list(date_str)
        logging.info(f"  {len(etf_list)} ETFs fetched")
    except Exception as e:
        logging.error(f"KRX API failed: {e}")
        conn.close()
        sys.exit(1)

    # etf_daily INSERT
    daily_rows = [(date_str, e['etf_code'], e['etf_name'], e['close_price'],
                    e['nav'], e['volume'], e['aum'], e['market_cap'])
                   for e in etf_list]
    insert_etf_daily_batch(conn, daily_rows)
    conn.commit()
    logging.info(f"  etf_daily: {len(daily_rows)} rows inserted")

    # Step 2: etfcheck → 구성종목/비중
    logging.info("Step 2: Fetching constituents from etfcheck...")
    s, e, emp = collect_constituents(conn, date_str, etf_list, already_done)
    logging.info(f"  First pass: ok={s} err={e} empty={emp}")

    # Step 3: 실패 재시도
    rs, re, remp = retry_failed(conn, date_str, etf_list)
    if rs or re:
        logging.info(f"  Retry: ok={rs} err={re} empty={remp}")

    # 최종 통계
    total_ok = conn.execute(
        "SELECT COUNT(*) FROM collection_log WHERE date=? AND status='ok'",
        (date_str,)
    ).fetchone()[0]
    total_const = conn.execute(
        "SELECT COUNT(*) FROM etf_constituents WHERE date=?",
        (date_str,)
    ).fetchone()[0]

    conn.close()
    logging.info(f"=== Done: {total_ok} ETFs, {total_const} constituent rows ===")


if __name__ == '__main__':
    main()
