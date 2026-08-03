#!/usr/bin/env python3
"""create_system_map.py — reference_system_map.md -> system_map.html (AoE terminal dark).

md source = ~/.claude/projects/-Users-sisyphe/memory/reference_system_map.md
output    = repo root system_map.html (published via publish_snapshot whitelist /*.html)

Generic markdown renderer (headings/tables/lists/fences) so weekly map edits
don't require touching this builder. Rerun after the Sunday 22:10 map update.
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
)


def main():
    text = open(MD, encoding='utf-8').read()
    secs = parse_sections(text)
    if not secs:
        sys.exit('FAIL: no sections parsed from %s' % MD)
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(MD), KST)
    body = ''.join(
        '<section class="sec"><h2>%s</h2>%s</section>' % (inline(t), render_blocks(ls))
        for t, ls in secs)
    # sub-strip: static preview until NAV_ITEMS grows architecture children
    # (then compose ROOT_ACTIVE replacement takes over this block).
    aside = ('<aside class="sidebar">'
             '<a href="/architecture.html" class="sidebar-link">Architecture</a>'
             '<a href="/system_map.html" class="sidebar-link active">System Map</a>'
             '</aside>')
    doc = (
        '<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<title>System Map — AGE OF EMERGENCE</title>\n'
        + nav_style.PRETENDARD_LINK_LOCAL + '\n'
        '<style>' + nav_style.NAV_CSS + nav_style.SIDEBAR_CSS + PAGE_CSS + '</style>\n'
        '</head>\n<body>\n'
        + nav_style.nav_html('architecture') + aside
        + '<div class="updated-line">Updated: %s KST</div>' % mtime.strftime('%Y-%m-%d %H:%M')
        + '<main class="smap">' + body + '</main>\n</body>\n</html>\n')
    open(OUT, 'w', encoding='utf-8').write(doc)
    print('wrote %s (%d sections, md mtime %s)' % (OUT, len(secs), mtime.strftime('%Y-%m-%d %H:%M')))


if __name__ == '__main__':
    main()
