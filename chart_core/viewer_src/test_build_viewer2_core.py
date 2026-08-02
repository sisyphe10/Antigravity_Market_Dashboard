# -*- coding: utf-8 -*-
"""P4 테스트: viewer2 데이터를 코어 기반 템플릿(chart_template_core.html)으로 빌드.

정식 전환 전 검증용 — 출력은 test_viewer2.html 하나뿐, 기존 페이지는 건드리지 않는다
(build_viewer2 import 부수효과로 chart_viewer2.html 이 같은 데이터·기존 템플릿으로
재생성되지만 이는 데일리 잡과 동일 동작이라 무해).
코어는 대시보드 repo(chart_core/dist)에서 읽고 manifest sha 검증 후 센티널 치환 (DECISION Q1).
"""
import hashlib
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from chart_common import apply_common
from daily_common import REPO

import build_viewer2 as v2   # DATA·CONFIG 재사용

CORE = os.path.join(REPO, 'chart_core', 'dist', 'aoe_chart.js')
MANI = os.path.join(REPO, 'chart_core', 'dist', 'aoe_chart.manifest.json')
with open(CORE, encoding='utf-8') as f:
    core = f.read()
with open(MANI, encoding='utf-8') as f:
    mani = json.load(f)
sha = hashlib.sha256(core.encode('utf-8')).hexdigest()
assert sha == mani['coreSha256'], (
    f"core sha mismatch: {sha[:12]} != {mani['coreSha256'][:12]} — repo pull/build_core.py 후 재실행")

with open(os.path.join(BASE, 'chart_template_core.html'), encoding='utf-8') as f:
    html = f.read()
html = (html
        .replace('__AOE_CHART_CORE__', core)
        .replace('__TITLE__', '[코어 테스트] 삼성전자 · SK하이닉스 — 현선물 격차 / 미결제약정 / 공매도 잔고 / 주가')
        .replace('__NOTE__', '코어(aoe_chart.js v' + mani['coreVersion'] + ') 기반 시험 페이지 — 정식 페이지는 chart_viewer2.html')
        .replace('__DLNAME__', 'samsung_hynix_chart_core_test')
        .replace('__CONFIG__', json.dumps(v2.CONFIG, ensure_ascii=False, separators=(',', ':')))
        .replace('__DATA__', json.dumps(v2.DATA, ensure_ascii=False, separators=(',', ':'))))

out = os.path.join(BASE, 'test_viewer2.html')
with open(out, 'w', encoding='utf-8') as f:
    f.write(apply_common(html, ''))
print('저장:', out, f'{os.path.getsize(out)/1024:.0f}KB')
