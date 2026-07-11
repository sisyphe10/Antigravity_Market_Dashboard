# -*- coding: utf-8 -*-
"""덮어쓰기형 레포 산출물 일별 gzip 스냅샷 — 매일 23:50 KST (datalake-snapshot).

레포의 매일 덮어쓰는 데이터 파일들을 ~/datalake/snapshots/YYYY/MM/DD/에 gzip 보존.
누적형(dataset.csv, universe_history.json 등)은 이력이 자체 보존되므로 제외.

사용: python3 datalake/snapshot_archiver.py [--date YYYY-MM-DD]
"""
import argparse
import gzip
import os
import shutil
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dl_common import REPO, SNAP_DIR

# 덮어쓰기형(과거 유실) 산출물 화이트리스트 — 신규 산출물 생기면 여기 추가
TARGETS = [
    "featured_data.json",
    "featured_news.json",
    "kodex_sectors.json",
    "investor_trading.json",
    "kofia_stats.json",
    "portfolio_data.json",
    "contribution_data.json",
    "disclosures.json",
    "landing_highlights.json",
    "index_returns.json",
    "monthly_returns.json",
    "universe.json",
    "seibro_tickers.json",
    "research_headlines.json",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="스냅샷 날짜 라벨 (기본 오늘)")
    args = ap.parse_args()
    d = args.date or date.today().isoformat()
    y, m, dd = d.split("-")
    out_dir = os.path.join(SNAP_DIR, y, m, dd)
    os.makedirs(out_dir, exist_ok=True)

    saved = missing = 0
    for name in TARGETS:
        src = os.path.join(REPO, name)
        if not os.path.exists(src):
            missing += 1
            continue
        dst = os.path.join(out_dir, name + ".gz")
        tmp = dst + ".tmp"
        with open(src, "rb") as fi, gzip.open(tmp, "wb", compresslevel=6) as fo:
            shutil.copyfileobj(fi, fo)
        os.replace(tmp, dst)
        saved += 1

    print(f"스냅샷 {d}: {saved}개 저장, {missing}개 없음 → {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
