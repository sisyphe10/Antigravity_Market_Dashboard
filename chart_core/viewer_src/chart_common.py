# -*- coding: utf-8 -*-
"""뷰어 공통 후처리: 상단 내비바(뷰어 간 이동) + 사이즈=세미나 단일(기본 버튼 제거) + 코어 셸 로더."""
import hashlib
import json as _json
import os


def core_js():
    """코어 JS(aoe_chart.js) 로드 — 대시보드 repo(chart_core/dist)에서 읽고 manifest
    sha 를 검증한다. 불일치면 예외 (드리프트 차단, DECISION Q1·Q2)."""
    repo = os.environ.get('DASH_REPO') or os.path.expanduser('~/Antigravity_Market_Dashboard')
    with open(os.path.join(repo, 'chart_core', 'dist', 'aoe_chart.js'), encoding='utf-8') as f:
        core = f.read()
    with open(os.path.join(repo, 'chart_core', 'dist', 'aoe_chart.manifest.json'), encoding='utf-8') as f:
        mani = _json.load(f)
    sha = hashlib.sha256(core.encode('utf-8')).hexdigest()
    if sha != mani['coreSha256']:
        raise RuntimeError(
            f"aoe_chart.js sha 불일치 ({sha[:12]} != {mani['coreSha256'][:12]}) — repo pull 후 chart_core/build_core.py 실행")
    return core


def aoe_tokens_css():
    """표 양식 비색상 규격 토큰(aoe_tokens.css) 로드 — manifest sha 검증 (드리프트 차단)."""
    repo = os.environ.get('DASH_REPO') or os.path.expanduser('~/Antigravity_Market_Dashboard')
    with open(os.path.join(repo, 'chart_core', 'dist', 'aoe_tokens.css'), encoding='utf-8') as f:
        css = f.read()
    with open(os.path.join(repo, 'chart_core', 'dist', 'aoe_chart.manifest.json'), encoding='utf-8') as f:
        mani = _json.load(f)
    sha = hashlib.sha256(css.encode('utf-8')).hexdigest()
    if mani.get('tokensSha256') and sha != mani['tokensSha256']:
        raise RuntimeError(
            f"aoe_tokens.css sha 불일치 ({sha[:12]}) — repo pull 후 chart_core/build_core.py 실행")
    return css


def core_template():
    """P4 코어 임베드 셸(chart_template_core.html) 로드 + 코어 JS 센티널 치환."""
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, 'chart_template_core.html'), encoding='utf-8') as f:
        html = f.read()
    return html.replace('__AOE_CHART_CORE__', core_js())

_LINK = ('font-family:inherit;font-size:12.5px;text-decoration:none;padding:5px 14px;'
         'border-radius:999px;border:1px solid #d0d0d0;color:#111;background:#fff;')
_NAV_ITEMS = [
    ('chart_viewer2.html', '현선물·수급·ETF'),
    ('chart_viewer_construction.html', '건설'),
    ('chart_viewer_etf.html', '레버리지ETF AUM'),
    ('chart_viewer_bop.html', '환율 수급'),
    ('chart_viewer_fcf.html', '빅테크 FCF'),
    ('chart_viewer_pipeline.html', '리가켐 파이프라인'),
    ('chart_viewer_research.html', '리서치 관심축'),
    ('chart_viewer_calendar.html', '이벤트 캘린더'),
    ('mindmap.html', '마인드맵'),
]


def nav_html(current=''):
    links = []
    for href, label in _NAV_ITEMS:
        st = _LINK + ('background:#404040;color:#fff;border-color:#404040;' if href == current else '')
        links.append(f'<a href="{href}" style="{st}">{label}</a>')
    return ('<div style="display:flex;gap:8px;margin:-6px 0 16px;flex-wrap:wrap;">'
            + ''.join(links) + '</div>')


def apply_common(html, current='', nav=True):
    # 1) 상단 내비바 (첫 </h1> 뒤) — iframe 서브차트는 nav=False로 생략
    if nav:
        html = html.replace('</h1>', '</h1>\n  ' + nav_html(current), 1)
    # 2) 사이즈 세그 통째 제거 (세미나로 통일 → 버튼 불필요). Download는 우측 유지용 스페이서
    html = html.replace(
        '        <span class="seg" style="margin-left:auto">\n'
        '          <button class="rng active" data-size="def">기본</button>\n'
        '          <button class="rng" data-size="sem">세미나</button>\n'
        '        </span>',
        '        <span style="margin-left:auto"></span>')
    # 3) 로드 시 세미나(800×450) 사이즈 직접 적용
    #    ★코어 템플릿(P4, chartwrap 고정높이 래퍼)은 래퍼 높이가 대상 — 캔버스에 직접 주면
    #      responsive 부모(래퍼) 높이와 어긋난다 (리사이즈 루프 방지 구조).
    if 'id="chartwrap"' in html:
        html = html.replace(
            'build();\n</script>',
            'build();\n(function(){var w=(800+34)+"px",cb=document.querySelector(".chartbox");'
            'if(cb){cb.style.width=w;document.querySelector(".controls").style.width=w;'
            'document.getElementById("chartwrap").style.height="450px";'
            'if(typeof chart!=="undefined"&&chart)chart.resize();}})();\n</script>')
        return html
    html = html.replace(
        'build();\n</script>',
        'build();\n(function(){var w=(800+34)+"px",cb=document.querySelector(".chartbox");'
        'if(cb){cb.style.width=w;document.querySelector(".controls").style.width=w;'
        'document.getElementById("chart").style.height="450px";'
        'if(typeof chart!=="undefined"&&chart)chart.resize();}})();\n</script>')
    return html
