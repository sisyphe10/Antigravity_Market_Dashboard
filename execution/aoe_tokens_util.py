# -*- coding: utf-8 -*-
"""표 규격 토큰(chart_core/dist/aoe_tokens.css) 공용 로더 + manifest sha 검증.
create_dashboard.py 는 자체 로더(_load_aoe_tokens_css) 사용 — 통합은 후속 정리 항목."""
import hashlib
import json
import os


def aoe_tokens_css():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, 'chart_core', 'dist', 'aoe_tokens.css'), encoding='utf-8') as f:
        css = f.read()
    with open(os.path.join(root, 'chart_core', 'dist', 'aoe_chart.manifest.json'), encoding='utf-8') as f:
        mani = json.load(f)
    sha = hashlib.sha256(css.encode('utf-8')).hexdigest()
    if sha != mani.get('tokensSha256'):
        raise RuntimeError('aoe_tokens.css sha 불일치 — chart_core/build_core.py 재실행')
    return css
