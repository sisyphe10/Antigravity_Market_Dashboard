#!/usr/bin/env python3
"""create_system_map.py — reference_system_map.md -> system_map.html (AoE terminal dark).

md source = ~/.claude/projects/-Users-sisyphe/memory/reference_system_map.md
output    = repo root system_map.html (published via publish_snapshot whitelist /*.html)

Generic markdown renderer (headings/tables/lists/fences) so weekly map edits
don't require touching this builder. Theme-token sections are rendered live
from nav_style.PALETTE / WRAP_PALETTE — the code source of truth — so palette
changes propagate on rebuild. Reruns: weekly map job hook + manual after map edits.
"""
import datetime
import html
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import nav_style  # noqa: E402

MD = os.path.expanduser('~/.claude/projects/-Users-sisyphe/memory/reference_system_map.md')
OUT = os.path.join(os.path.dirname(BASE), 'system_map.html')
KST = datetime.timezone(datetime.timedelta(hours=9))


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    return s


def parse_sections(text):
    lines = text.splitlines()
    i = 0
    if lines and lines[0].strip() == '---':  # frontmatter
        i = 1
        while i < len(lines) and lines[i].strip() != '---':
            i += 1
        i += 1
    sections = []
    cur = None
    for ln in lines[i:]:
        if ln.startswith('# '):
            continue
        if ln.startswith('## '):
            cur = (ln[3:].strip(), [])
            sections.append(cur)
            continue
        if cur is not None:
            cur[1].append(ln)
    return sections


def render_table(rows):
    parsed = []
    for r in rows:
        if re.match(r'^\|[\s\-|:]+\|$', r.strip()):
            continue
        parsed.append([c.strip() for c in r.strip().strip('|').split('|')])
    if not parsed:
        return ''
    ncol = max(len(r) for r in parsed)
    # long-text columns keep left alignment via INLINE style — the compose
    # dark CSS centers td:not([style*=text-align]) with !important, so a
    # class would be overridden (inline text-align is its only exception).
    lefts = []
    for c in range(ncol):
        w = max((len(r[c]) for r in parsed[1:] if c < len(r)), default=0)
        lefts.append(w > 30)
    out = ['<div class="tbl-wrap"><table>']
    out.append('<tr>' + ''.join('<th>%s</th>' % inline(c) for c in parsed[0]) + '</tr>')
    for r in parsed[1:]:
        tds = []
        for c, cell in enumerate(r):
            st = ' style="text-align:left"' if lefts[c] else ''
            tds.append('<td%s>%s</td>' % (st, inline(cell)))
        out.append('<tr>' + ''.join(tds) + '</tr>')
    out.append('</table></div>')
    return ''.join(out)


def render_blocks(lines):
    out, i, n = [], 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if s.startswith('```'):
            j = i + 1
            buf = []
            while j < n and not lines[j].strip().startswith('```'):
                buf.append(lines[j])
                j += 1
            out.append('<pre>%s</pre>' % html.escape('\n'.join(buf), quote=False))
            i = j + 1
            continue
        if s.startswith('|'):
            j = i
            buf = []
            while j < n and lines[j].strip().startswith('|'):
                buf.append(lines[j])
                j += 1
            out.append(render_table(buf))
            i = j
            continue
        if s.startswith('- '):
            j = i
            items = []
            while j < n and lines[j].strip().startswith('- '):
                items.append('<li>%s</li>' % inline(lines[j].strip()[2:]))
                j += 1
            out.append('<ul>%s</ul>' % ''.join(items))
            i = j
            continue
        out.append('<p>%s</p>' % inline(s))
        i += 1
    return '\n'.join(out)


def _swatch(key, val):
    return ('<div class="sw"><span class="swc" style="background:%s"></span>'
            '<span class="swk">%s</span><code>%s</code></div>' % (val, key, val))


TYPO_ROWS = [  # 정본 표기용 요약 — 수치 정본은 AOE_STYLE_GUIDE.md
    ('카테고리 대제목', '30px'), ('섹션·그룹 타이틀', '20px'), ('표 본문', '17px'),
    ('표 헤더(th)', '15px'), ('메타·보조', '14px'), ('nav 탭', '1rem/600'),
]


def theme_sections():
    out = []
    # ---- AoE 터미널 다크 (PALETTE 라이브 렌더) ----
    out.append('<section class="sec"><h2>테마 토큰 — AoE 터미널 다크</h2>')
    out.append('<p class="meta">정본: <code>execution/nav_style.py</code> PALETTE '
               '(CSS 변수 <code>--aoe-*</code>) · 스펙 상세: <code>AOE_STYLE_GUIDE.md</code> '
               '· 이 스와치는 빌드 시 코드에서 직접 읽음</p>')
    plain = [(k, v) for k, v in nav_style.PALETTE.items() if not k.startswith('hl')]
    out.append('<div class="swgrid">%s</div>' % ''.join(_swatch(k, v) for k, v in plain))
    pairs = []
    for k, v in nav_style.PALETTE.items():
        if k.startswith('hl') and k.endswith('-bg'):
            base = k[:-3]
            fg = nav_style.PALETTE.get(base + '-fg', '#fff')
            pairs.append('<span class="swpair" style="background:%s;color:%s">%s '
                         '%s / %s</span>' % (v, fg, base, v, fg))
    out.append('<p class="meta">선택 하이라이트 (hl-amber=상시 액센트, 순환=hl1→hl2→hl3)</p>')
    out.append('<div class="swrow">%s</div>' % ''.join(pairs))
    out.append('<div class="tbl-wrap"><table><tr><th>타이포 계층</th><th>크기</th></tr>%s</table></div>'
               % ''.join('<tr><td>%s</td><td>%s</td></tr>' % rc for rc in TYPO_ROWS))
    out.append('</section>')
    # ---- Life WRAP 라이트 (WRAP_PALETTE 라이브 렌더) ----
    out.append('<section class="sec"><h2>테마 토큰 — Life WRAP 라이트 (팀 전용 예외)</h2>')
    out.append('<p class="meta">정본: <code>execution/nav_style.py</code> WRAP_PALETTE '
               '(CSS 변수 <code>--wrap-*</code>) · 소비: create_dashboard WRAP 구간 '
               '· gh-pages 라이트 유지 — AoE 다크 미적용 · 타이포 스케일은 AoE와 공통</p>')
    out.append('<div class="swgrid">%s</div>'
               % ''.join(_swatch(k, v) for k, v in nav_style.WRAP_PALETTE.items()))
    out.append('</section>')
    return ''.join(out)


# amber/th/code colors carry !important so they survive the compose dark
# injection (h2{color:#fff!important} etc.) — specificity wins among equals.
PAGE_CSS = (
    'body{margin:0;background:#0a0a0a;color:#d9dde2;font-family:' + nav_style.PRETENDARD_STACK +
    ';font-size:17px;line-height:1.55}'
    '.updated-line{max-width:1240px;margin:0 auto;text-align:right;font-size:14px;'
    'font-style:italic;color:#8a919a;padding:6px 28px 14px;box-sizing:border-box}'
    '.smap{max-width:1240px;margin:0 auto;padding:0 24px 64px}'
    '.sec{background:#111214;border:1px solid #27282b;border-radius:8px;'
    'padding:20px 24px;margin:0 0 18px}'
    '.sec>h2{margin:0 0 14px;font-size:20px;font-weight:700;color:#fb8b1e!important}'
    '.sec p{margin:8px 0}'
    '.sec p.meta{font-size:14px;color:#8a919a}'
    '.sec ul{margin:4px 0;padding-left:22px}'
    '.sec li{margin:6px 0}'
    '.smap table{width:100%;border-collapse:collapse;font-size:17px}'
    '.smap th{background:#1a1b1e!important;color:#fb8b1e!important;font-size:15px;'
    'font-weight:700;padding:8px 12px;border:1px solid #27282b}'
    '.smap td{padding:8px 12px;border:1px solid #27282b;color:#fff;vertical-align:top}'
    '.tbl-wrap{overflow-x:auto;margin:10px 0}'
    '.smap code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.88em;'
    'background:#14171b;border:1px solid #27282b;border-radius:4px;padding:1px 6px;'
    'color:#ffb45e!important}'
    '.smap pre{background:#0d0f12;border:1px solid #27282b;border-radius:8px;'
    'padding:16px 20px;overflow-x:auto;font-size:14px;line-height:1.75;color:#d9dde2;margin:10px 0}'
    '.smap b{color:#fff}'
    '.swgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));'
    'gap:8px;margin:6px 0}'
    '.sw{display:flex;align-items:center;gap:8px;background:#0d0f12;'
    'border:1px solid #27282b;border-radius:6px;padding:6px 10px}'
    '.swc{width:22px;height:22px;border-radius:4px;border:1px solid #3a3b3e;flex:0 0 22px}'
    '.swk{font-size:14px;color:#d9dde2;flex:1;text-align:left}'
    '.sw code{font-size:13px}'
    '.swrow{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}'
    '.swpair{display:inline-flex;align-items:center;padding:6px 12px;border-radius:6px;'
    'font-size:14px;font-weight:600;border:1px solid #27282b}'
)


def main():
    text = open(MD, encoding='utf-8').read()
    secs = parse_sections(text)
    if not secs:
        sys.exit('FAIL: no sections parsed from %s' % MD)
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(MD), KST)
    body = ''.join(
        '<section class="sec"><h2>%s</h2>%s</section>' % (inline(t), render_blocks(ls))
        for t, ls in secs) + theme_sections()
    doc = (
        '<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<title>System Map — AGE OF EMERGENCE</title>\n'
        + nav_style.PRETENDARD_LINK_LOCAL + '\n'
        '<style>' + nav_style.NAV_CSS + nav_style.SIDEBAR_CSS + PAGE_CSS + '</style>\n'
        '</head>\n<body>\n'
        + nav_style.nav_html('architecture', 'system_map')
        + nav_style.sidebar_html('system_map')
        + '<div class="updated-line">Updated: %s KST</div>' % mtime.strftime('%Y-%m-%d %H:%M')
        + '<main class="smap">' + body + '</main>\n</body>\n</html>\n')
    open(OUT, 'w', encoding='utf-8').write(doc)
    print('wrote %s (%d sections, md mtime %s)' % (OUT, len(secs), mtime.strftime('%Y-%m-%d %H:%M')))


if __name__ == '__main__':
    main()
