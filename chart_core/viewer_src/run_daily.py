# -*- coding: utf-8 -*-
"""뷰어 데일리 파이프라인 — 매일 23:50 KST launchd (viewer-daily).

수집 8종 → 빌드 3종 순차 실행. 수집이 실패해도 빌더는 진행한다
(수집기 저장이 원자적이라 실패 시 CSV/JSON은 최악의 경우 전일본 유지) —
단 하나라도 실패하면 rc=1 로 종료해 wrapper 가 notify 를 태운다.

construction 계열(수주잔고=DART 분기 집계)은 데일리 대상이 아님 — 분기 수동.

사용: python3 run_daily.py [--skip-collect]
"""
import argparse
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

COLLECT = ["collect.py", "collect_mktcap.py", "collect_index.py", "collect_etf.py",
           "collect_vkospi.py", "collect_fx.py", "collect_us30y.py", "collect_earnings.py",
           "collect_bop.py", "collect_monthly.py"]
BUILD = ["build_viewer.py", "build_viewer2.py", "build_viewer_etf.py", "build_viewer_bop.py"]


def run(script):
    rc = subprocess.run([sys.executable, os.path.join(BASE, script)],
                        cwd=BASE, check=False).returncode
    print(f"[viewer-daily] {script} rc={rc}", flush=True)
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-collect", action="store_true", help="빌드만 재실행")
    args = ap.parse_args()

    failed = []
    if not args.skip_collect:
        failed += [s for s in COLLECT if run(s) != 0]
    failed += [s for s in BUILD if run(s) != 0]
    if failed:
        print(f"! 실패: {', '.join(failed)}", flush=True)
        return 1
    print("[viewer-daily] 완료", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
