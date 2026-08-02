# -*- coding: utf-8 -*-
"""기존 산출 HTML의 내비바 div만 chart_common.nav_html로 재생성 (탭 추가 시 재빌드 없이 반영).

빌더를 다시 돌리면 수집 데이터가 최신이 아닌 환경에서 페이지가 퇴행할 수 있으므로,
탭 추가 같은 내비 변경은 이 스크립트로 nav div만 교체한다. 멱등."""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chart_common import nav_html, _NAV_ITEMS  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
PAT = re.compile(r'<div style="display:flex;gap:8px;margin:-6px 0 16px;flex-wrap:wrap;">.*?</div>', re.S)

for href, label in _NAV_ITEMS:
    p = os.path.join(BASE, href)
    if not os.path.exists(p):
        print(f"  SKIP {href} (없음)")
        continue
    h = io.open(p, encoding='utf-8').read()
    hits = PAT.findall(h)
    if len(hits) != 1:
        print(f"  SKIP {href} (nav div {len(hits)}개 — 수동 확인 필요)")
        continue
    new = nav_html(href)
    if hits[0] == new:
        print(f"  OK   {href} (변경 없음)")
        continue
    io.open(p, 'w', encoding='utf-8').write(PAT.sub(lambda m: new, h, count=1))
    print(f"   →   {href} nav 갱신 ({len(_NAV_ITEMS)}탭)")
print("done")
