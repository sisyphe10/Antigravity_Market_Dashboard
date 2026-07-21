# -*- coding: utf-8 -*-
"""일일 매크로·수급 증분 — 매일 20:50 KST launchd (datalake-macro-update).

백필만 되고 데일리가 없던 3개 데이터셋을 최신화한다 (2026-07-22 신설):
- kr_macro (ECOS 33종): backfill_ecos.py 전체 이력 재조회 → upsert(멱등).
  yoy 변환이 전년동월 베이스(전체 이력)를 요구하므로 윈도우 증분보다
  전체 재실행이 안전하고, 실행도 수 분이면 끝난다.
- us_macro (FRED 36종): backfill_fred.py 동일 (관측창 제한 없음 — 주간
  시리즈 5년창 함정 회피는 전체 조회가 정답).
- kr_flows (금투협 예탁금·신용잔고): 최신일 내림차순 페이지네이션이라
  --pages 1 (오퍼레이션당 최신 500행 ≈ 2년치)로 증분.

마지막에 build_catalog.py 재생성. 스텝 실패는 기록 후 계속 진행하되
하나라도 실패하면 rc=1 (wrapper가 notify → 자가진단).

사용: python3 datalake/daily_macro_update.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

STEPS = [
    ("backfill_ecos.py", []),
    ("backfill_fred.py", []),
    ("backfill_kofia.py", ["--pages", "1"]),
]


def main():
    failed = []
    for script, extra in STEPS:
        rc = subprocess.run([sys.executable, os.path.join(HERE, script)] + extra,
                            check=False).returncode
        print(f"[macro-update] {script} rc={rc}", flush=True)
        if rc != 0:
            failed.append(script)

    # 카탈로그·뷰 갱신 — 실패를 성공으로 삼키지 않는다 (wrapper가 notify)
    rc = subprocess.run([sys.executable, os.path.join(HERE, "build_catalog.py")],
                        check=False).returncode
    if rc != 0:
        print(f"! build_catalog 실패 rc={rc}", flush=True)
        return 1
    if failed:
        print(f"! 실패 스텝: {', '.join(failed)}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
