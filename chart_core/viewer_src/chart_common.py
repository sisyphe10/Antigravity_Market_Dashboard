# -*- coding: utf-8 -*-
"""뷰어 공통 후처리: 상단 내비바(뷰어 간 이동) + 사이즈=세미나 단일(기본 버튼 제거)."""

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
    html = html.replace(
        'build();\n</script>',
        'build();\n(function(){var w=(800+34)+"px",cb=document.querySelector(".chartbox");'
        'if(cb){cb.style.width=w;document.querySelector(".controls").style.width=w;'
        'document.getElementById("chart").style.height="450px";'
        'if(typeof chart!=="undefined"&&chart)chart.resize();}})();\n</script>')
    return html
