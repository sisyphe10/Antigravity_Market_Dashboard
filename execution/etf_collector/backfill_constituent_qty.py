"""etf_constituents qty/px 백필 — 기존 확정 row에 수량/현재가만 보강 UPDATE.

etfcheck는 당일 PDF만 제공하므로, PDF가 아직 대상 날짜 기준일 때(통상 다음날
아침 롤오버 전) 실행해야 한다.

안전장치(정합성 > 커버리지):
- ETF별로 방금 받아온 weight를 저장된 weight와 stock_code 단위로 대조 —
  90% 이상이 ±0.05%p 이내로 일치할 때만 UPDATE. 불일치가 크면 PDF가 이미
  다음 날짜로 롤오버된 것으로 보고 그 ETF는 스킵(잘못된 qty 오염 방지).
- INSERT OR REPLACE가 아니라 표적 UPDATE — 원본 weight/stock_name 불변.
- collection_log 는 건드리지 않는다 (재수집이 아니라 보강).

사용: python3 backfill_constituent_qty.py 2026-07-07
"""
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

WEIGHT_TOL = 0.05    # weight 일치 허용오차(%p)
MATCH_MIN = 0.9      # 일치 비율 하한 — 미만이면 롤오버 판정, 스킵
DELAY = 0.3          # politeness (collect_etf_daily.POLITENESS_DELAY와 동일)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    date_str = sys.argv[1]

    from etf_db import init_db, get_conn
    from etfcheck_client import fetch_constituents

    init_db()  # qty/px 컬럼 마이그레이션 보장
    conn = get_conn()

    codes = [r['etf_code'] for r in conn.execute(
        "SELECT etf_code FROM collection_log WHERE date=? AND status='ok' ORDER BY etf_code",
        (date_str,)).fetchall()]
    logging.info("백필 대상: %s, %d개 ETF", date_str, len(codes))

    updated = skipped = errors = 0
    for i, code in enumerate(codes):
        try:
            stored = {r['stock_code']: r['weight'] for r in conn.execute(
                "SELECT stock_code, weight FROM etf_constituents WHERE date=? AND etf_code=?",
                (date_str, code)).fetchall()}
            if not stored:
                skipped += 1
                continue

            fresh = {c['stock_code']: c for c in fetch_constituents(code)
                     if c['stock_code'] and c['stock_name']}

            # 롤오버 검증: 저장분 대비 weight 일치율
            matched = sum(1 for sc, w in stored.items()
                          if sc in fresh and abs((fresh[sc]['weight'] or 0) - (w or 0)) <= WEIGHT_TOL)
            if matched / len(stored) < MATCH_MIN:
                logging.warning("  %s 스킵 — weight 일치 %d/%d (롤오버 의심)",
                                code, matched, len(stored))
                skipped += 1
                continue

            rows = [(c.get('qty'), c.get('px'), date_str, code, sc)
                    for sc, c in fresh.items() if sc in stored]
            conn.executemany(
                "UPDATE etf_constituents SET qty=?, px=? "
                "WHERE date=? AND etf_code=? AND stock_code=?", rows)
            updated += 1
        except Exception as e:
            logging.error("  %s 실패: %s", code, str(e)[:150])
            errors += 1

        if (i + 1) % 50 == 0:
            conn.commit()
            logging.info("  [%d/%d] updated=%d skipped=%d err=%d",
                         i + 1, len(codes), updated, skipped, errors)
        time.sleep(DELAY)

    conn.commit()
    n_qty = conn.execute(
        "SELECT COUNT(*) FROM etf_constituents WHERE date=? AND qty IS NOT NULL",
        (date_str,)).fetchone()[0]
    conn.close()
    logging.info("=== 백필 완료: updated=%d skipped=%d err=%d | qty NOT NULL rows=%d ===",
                 updated, skipped, errors, n_qty)


if __name__ == '__main__':
    main()
