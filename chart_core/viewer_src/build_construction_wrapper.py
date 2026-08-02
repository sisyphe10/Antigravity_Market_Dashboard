# -*- coding: utf-8 -*-
"""건설 탭 래퍼 — 상단 내비 + 두 차트(수주잔고÷시총 / PBR·PER)를 위아래로 스택 배치(iframe).
서브차트=con_soojoo.html·con_pbrper.html(nav 없이 빌드)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chart_common import nav_html
BASE = os.path.dirname(os.path.abspath(__file__))

TPL = '''<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<title>건설 3사 밸류에이션</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
<style>
  * { box-sizing: border-box; }
  body { font-family: 'Pretendard Variable', Pretendard, system-ui, sans-serif; margin: 0; background: #fff; color: #111; }
  .wrap { max-width: 1500px; margin: 0 auto; padding: 24px 28px; }
  h1 { font-size: 20px; font-weight: 700; margin: 0 0 16px; }
  iframe { width: 100%; height: 740px; border: none; display: block; }
  .gap { height: 18px; }
</style></head>
<body><div class="wrap">
  <h1>건설 3사 밸류에이션</h1>
  __NAV__
  <iframe src="con_soojoo.html" title="수주잔고÷시가총액"></iframe>
  <div class="gap"></div>
  <iframe src="con_pbrper.html" title="PBR·PER"></iframe>
</div>
</body></html>'''

html = TPL.replace('__NAV__', nav_html('chart_viewer_construction.html'))
open(os.path.join(BASE, 'chart_viewer_construction.html'), 'w', encoding='utf-8').write(html)
print("WROTE chart_viewer_construction.html (건설 래퍼: 수주잔고÷시총 / PBR·PER 위아래 스택)")
